"""REST endpoints: search, queue management, player control and TV info."""
import asyncio
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from config import MELODY_FILE, qr_svg_data_uri, remote_url
from core import cache_manager, settings
from core.queue_manager import queue
from core.worker import worker
from services import search as smart_search
from services import search_filter, search_memory, sources
from services.song_names import song_key

router = APIRouter(prefix="/api")


class QueueRequest(BaseModel):
    song_id: str = Field(min_length=11, max_length=20)   # YouTube id or "sc_<digits>"
    singer: str = Field(min_length=1, max_length=32)
    title: str = Field(default="Unknown title", max_length=200)
    channel: str = Field(default="", max_length=120)
    duration: int | None = Field(default=None, ge=0)
    mirrors: list[str] = Field(default_factory=list, max_length=10)   # backups from the search result


class MoveRequest(BaseModel):
    direction: Literal["up", "down", "top"]   # top = sing next


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


# ── Queue ────────────────────────────────────────────────────────────────────
@router.get("/queue")
async def get_queue():
    return queue.snapshot()


@router.post("/queue", status_code=201)
async def add_to_queue(req: QueueRequest):
    singer = req.singer.strip()
    if not singer:
        raise HTTPException(422, "Singer name is required")
    if not sources.is_valid_id(req.song_id) or not all(map(sources.is_valid_id, req.mirrors)):
        raise HTTPException(400, "Invalid song id")
    cached = cache_manager.is_ready(req.song_id)   # already processed: no cost, length doesn't matter
    if not cached and (problem := search_filter.duration_problem(req.duration)):
        raise HTTPException(400, problem)
    if len(queue.entries) >= settings.get("max_queue"):
        raise HTTPException(429, "The queue is full — try again later")

    search_memory.add_mirrors(req.song_id, req.mirrors, title=req.title, channel=req.channel,
                              duration=req.duration, key=song_key(req.title, req.channel))
    hint = search_memory.hint(req.song_id) or {}
    entry = await queue.add(req.song_id, req.title.strip(), req.channel.strip(),
                            req.duration, singer, hint.get("thumbnail"))
    await worker.submit(req.song_id)
    if cache_manager.is_ready(req.song_id) and not cache_manager.song_file(req.song_id, MELODY_FILE).is_file():
        await worker.submit_melody(req.song_id)  # cached before the singing game existed
    return entry


@router.delete("/queue/{uid}")
async def remove_from_queue(uid: str):
    if not await queue.remove(uid):
        raise HTTPException(404, "Queue entry not found")
    return {"ok": True}


@router.post("/queue/{uid}/move")
async def move_in_queue(uid: str, req: MoveRequest):
    offset = {"up": -1, "down": 1, "top": -len(queue.entries)}[req.direction]
    if not await queue.move(uid, offset):
        raise HTTPException(404, "Queue entry not found")
    return {"ok": True}


# ── Player ───────────────────────────────────────────────────────────────────
@router.post("/player/next")
async def play_next():
    return {"now_playing": await queue.next()}


@router.post("/player/control")
async def player_control(req: ControlRequest):
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
