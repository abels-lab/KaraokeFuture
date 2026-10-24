"""REST endpoints: search, player control and TV info. The queue lives in routers/queue.py.

Player control is for the host; a guest may also pause / play / restart / seek / skip their
OWN song while it plays (core/auth.py), never someone else's.
"""
import asyncio
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from config import PORT, qr_svg_data_uri, remote_url
from core import auth, settings
from core.queue_manager import queue
from core.worker import worker
from services import search as smart_search, tailscale

router = APIRouter(prefix="/api")


class ControlRequest(BaseModel):
    action: Literal["play", "pause", "restart", "skip", "seek", "seek_by"]
    value: float | None = Field(default=None, ge=-3600, le=3600)   # seek: seconds, seek_by: ±seconds


# ── Search ───────────────────────────────────────────────────────────────────
@router.get("/search")
async def search(q: str = Query(min_length=1, max_length=120)):
    """Filtered, de-duplicated and checked results only (services/search.py)."""
    if not q.strip():
        return {"results": [], "stats": {}}
    try:
        results, stats = await asyncio.to_thread(smart_search.run, q.strip())
    except Exception as exc:
        raise HTTPException(502, f"Search failed: {exc}") from exc
    return {"results": results, "stats": stats}


# ── Player ───────────────────────────────────────────────────────────────────
@router.post("/player/next", dependencies=[Depends(auth.require_admin)])
async def play_next():
    return {"now_playing": await queue.next()}


@router.post("/player/control")
async def player_control(req: ControlRequest, request: Request):
    who = auth.identify(request)
    if not auth.may_manage(who, queue.current):
        raise HTTPException(403, "Only the host or the person singing can control this song")
    if req.action.startswith("seek") and not who.admin and not settings.get("guest_scrubbing"):
        raise HTTPException(403, "Timeline scrubbing is reserved for the host")
    if req.action == "skip":
        return {"now_playing": await queue.next()}
    await queue.control(req.action, req.value)
    return {"ok": True}


# ── TV info ──────────────────────────────────────────────────────────────────
@router.get("/info")
async def info():
    """The QR code links to the Tailscale Funnel address when there is one (works on mobile
    data, HTTPS), else to this laptop on the home Wi-Fi; the `qr_link` setting can force either."""
    lan, public = remote_url(), await asyncio.to_thread(tailscale.funnel_url, PORT)
    public = public and f"{public}/remote"
    url = public if public and settings.get("qr_link") != "lan" else lan
    return {
        "remote_url": url, "lan_url": lan, "public_url": public,
        "qr": qr_svg_data_uri(url),
        "processing": worker.current_song,   # guest songs only; warm-ups are silent
        "backlog": worker.backlog(),
    }
