"""FastAPI entry point: wires routers, static files, cached media and the worker.

Run (single process — queue state lives in memory):
    python main.py
    # or: uvicorn main:app --host 0.0.0.0 --port 8000
"""
import asyncio
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from config import CACHE_DIR, HOST, PORT, STATIC_DIR, get_local_ip, setup_logging
from core import cache_manager
from core.warmer import warmer
from core.worker import worker
from routers import api, auth, battle, library, queue, settings, ws
from services import tailscale

setup_logging()
log = logging.getLogger("karaoke")


class _IgnoreClientResets(logging.Filter):
    """Windows' Proactor loop logs an ERROR traceback whenever a browser drops a connection,
    e.g. each video seek cancels the old range request. Harmless; keep the log readable."""
    def filter(self, record: logging.LogRecord) -> bool:
        return not (record.exc_info and isinstance(record.exc_info[1], ConnectionResetError))


logging.getLogger("asyncio").addFilter(_IgnoreClientResets())


@asynccontextmanager
async def lifespan(_: FastAPI):
    removed = cache_manager.purge_incomplete()
    if removed:
        log.info("Removed %d half-processed song folder(s)", len(removed))
    worker.start()
    warmer.start()   # popular songs, in the background, after a short delay
    ip = get_local_ip()
    log.info("Control panel: http://localhost:%d/tv", PORT)
    log.info("Projector:     http://%s:%d/screen", ip, PORT)
    log.info("Guests:        http://%s:%d/remote", ip, PORT)
    public = await asyncio.to_thread(tailscale.funnel_url, PORT)
    log.info("Guests online: %s", f"{public}/remote (Tailscale Funnel)" if public else "no Tailscale Funnel to this port")
    yield
    await warmer.stop()
    await worker.stop()


app = FastAPI(title="AI Karaoke", lifespan=lifespan)
app.include_router(api.router)
app.include_router(queue.router)
app.include_router(battle.router)
app.include_router(auth.router)
app.include_router(library.router)
app.include_router(settings.router)
app.include_router(ws.router)

PAGES = {"tv": "tv.html", "screen": "screen.html", "remote": "remote.html", "library": "library.html",
         "settings": "settings.html"}


@app.middleware("http")
async def revalidate_app_files(request, call_next):
    """Pages, scripts and lyrics change between updates/pastes: make browsers revalidate
    (cheap ETag check) instead of silently reusing stale copies. Audio stays cached."""
    response = await call_next(request)
    path = request.url.path
    if path.strip("/") in PAGES or path.startswith("/static/") or path.endswith(".json"):
        response.headers["Cache-Control"] = "no-cache"
    return response


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/media", StaticFiles(directory=CACHE_DIR), name="media")


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse("/tv")


@app.get("/{page}", include_in_schema=False)
async def page(page: str):
    """/tv (host screen), /remote (guest phones), /library (song & lyrics manager)."""
    if page not in PAGES:
        raise HTTPException(404)
    return FileResponse(STATIC_DIR / PAGES[page])


if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT, workers=1, log_level="info")
