"""REST endpoints: search, player control and TV info. The queue lives in routers/queue.py.

Player control is for the host; a guest may also pause / play / restart / seek / skip their
OWN song while it plays (core/auth.py), never someone else's.
"""
import asyncio
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from config import qr_svg_data_uri, remote_url
from core import auth
from core.queue_manager import queue
from core.worker import worker
from services import search as smart_search

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
    if not auth.may_manage(auth.identify(request), queue.current):
        raise HTTPException(403, "Only the host or the person singing can control this song")
    if req.action == "skip":
        return {"now_playing": await queue.next()}
    await queue.control(req.action, req.value)
    return {"ok": True}


# ── TV info ──────────────────────────────────────────────────────────────────
@router.get("/info")
async def info():
    url = remote_url()
    return {
        "remote_url": url,
        "qr": qr_svg_data_uri(url),
        "processing": worker.current_song,   # guest songs only; warm-ups are silent
        "backlog": worker.backlog(),
    }
