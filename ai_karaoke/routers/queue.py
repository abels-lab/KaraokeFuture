"""Queue endpoints with permissions (core/auth.py): who may add, remove, reorder and tune.

- Adding needs a guest login (the singer name is the login name) or the host (who may
  queue for any name, e.g. from the library on the laptop).
- Removing / changing guide volume or mode: the host, or the guest who queued the entry.
- Reordering: the host moves anything anywhere; a guest only swaps among their own slots
  (core/queue_personal.py), so nobody cuts ahead of other people.
"""
import asyncio
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from config import MELODY_FILE
from core import auth, cache_manager, settings, surprise
from core.queue_manager import queue
from core.worker import worker
from services import search_filter, search_memory, sources
from services.song_names import song_key

router = APIRouter(prefix="/api/queue")
Mode = Literal["party", "score", "battle"]


class QueueRequest(BaseModel):
    song_id: str = Field(min_length=11, max_length=20)   # YouTube id or "sc_<digits>"
    singer: str = Field(default="", max_length=32)        # host only; guests sing as themselves
    title: str = Field(default="Unknown title", max_length=200)
    channel: str = Field(default="", max_length=120)
    duration: int | None = Field(default=None, ge=0)
    mirrors: list[str] = Field(default_factory=list, max_length=10)   # backups from the search result
    guide: int | None = Field(default=None, ge=0, le=100)
    mode: Mode | None = None


class MoveRequest(BaseModel):
    direction: Literal["up", "down", "top"] | None = None   # top = sing next (guests: their first slot)
    to_index: int | None = Field(default=None, ge=0)        # host: drag and drop to any position
    scope: Literal["all", "mine"] = "all"                   # the host may also move just among their own


class PrefsRequest(BaseModel):
    guide: int | None = Field(default=None, ge=0, le=100)   # None = the control panel's slider
    mode: Mode | None = None                                # None = the control panel's picker


def _singer(who: auth.Who, wanted: str) -> tuple[str, int | None]:
    """(singer name, owner guest id) for a new entry."""
    wanted = " ".join(wanted.split())
    if who.admin and wanted and (who.name is None or wanted.casefold() != who.name.casefold()):
        return wanted, None   # the host queues for someone without a login
    if who.guest_id is not None:
        return who.name, who.guest_id
    if who.admin:
        raise HTTPException(422, "Singer name is required")
    raise HTTPException(401, "Log in with your name on the remote page first")


async def _enqueue(song_id: str, title: str, channel: str, duration, singer: str, owner: int | None,
                   guide: int | None = None, mode: str | None = None, thumbnail: str | None = None) -> dict:
    if len(queue.entries) >= settings.get("max_queue"):
        raise HTTPException(429, "The queue is full — try again later")
    entry = await queue.add(song_id, title, channel, duration, singer, thumbnail, owner, guide, mode)
    await worker.submit(song_id)
    if cache_manager.is_ready(song_id) and not cache_manager.song_file(song_id, MELODY_FILE).is_file():
        await worker.submit_melody(song_id)  # cached before the singing game existed
    return entry


def _entry_for(request: Request, uid: str) -> tuple[auth.Who, dict]:
    who, entry = auth.identify(request), queue.find_any(uid)
    if entry is None:
        raise HTTPException(404, "Queue entry not found")
    if not auth.may_manage(who, entry):
        raise HTTPException(403, "That's someone else's song — only they or the host can change it")
    return who, entry


@router.get("")
async def get_queue():
    return queue.snapshot()


@router.post("", status_code=201)
async def add_to_queue(req: QueueRequest, request: Request):
    singer, owner = _singer(auth.identify(request), req.singer)
    if not sources.is_valid_id(req.song_id) or not all(map(sources.is_valid_id, req.mirrors)):
        raise HTTPException(400, "Invalid song id")
    cached = cache_manager.is_ready(req.song_id)   # already processed: no cost, length doesn't matter
    if not cached and (problem := search_filter.duration_problem(req.duration)):
        raise HTTPException(400, problem)
    search_memory.add_mirrors(req.song_id, req.mirrors, title=req.title, channel=req.channel,
                              duration=req.duration, key=song_key(req.title, req.channel))
    hint = search_memory.hint(req.song_id) or {}
    return await _enqueue(req.song_id, req.title.strip(), req.channel.strip(), req.duration, singer, owner,
                          req.guide, req.mode, hint.get("thumbnail"))


@router.post("/surprise", status_code=201)
async def surprise_me(request: Request):
    """'I don't know what to sing': queue a random ready song for this guest, instantly."""
    singer, owner = _singer(auth.identify(request), "")
    meta = await asyncio.to_thread(surprise.pick, queue.protected_ids())
    if meta is None:
        raise HTTPException(404, "No ready song is free right now — search for one instead")
    return await _enqueue(meta["id"], meta.get("title") or meta["id"], meta.get("channel", ""),
                          meta.get("duration"), singer, owner, thumbnail=meta.get("thumbnail"))


@router.post("/previous")
async def play_previous(request: Request):
    """Navigate backwards to the previous played song."""
    who = auth.identify(request)
    if not who.admin:
        raise HTTPException(403, "Only the host can navigate to previous songs")
    prev_song = await queue.previous()
    if not prev_song:
        raise HTTPException(404, "No previous song in history")
    return {"now_playing": prev_song}


@router.delete("/{uid}")
async def remove_from_queue(uid: str, request: Request):
    _entry_for(request, uid)
    await queue.remove(uid)   # your own song while it plays: removing it ends it
    return {"ok": True}


@router.post("/{uid}/move")
async def move_in_queue(uid: str, req: MoveRequest, request: Request):
    who, entry = _entry_for(request, uid)
    if who.admin and req.to_index is not None:
        moved = await queue.move_to(uid, req.to_index)
    elif who.admin and req.scope == "all" and req.direction:
        offset = {"up": -1, "down": 1, "top": -len(queue.entries)}[req.direction]
        moved = await queue.move(uid, offset)
    elif req.direction:
        moved = entry.get("owner") is not None and await queue.move_own(uid, entry["owner"], req.direction)
    else:
        moved = False
    if not moved:
        raise HTTPException(409, "Only waiting songs can be moved")
    return {"ok": True}


@router.post("/{uid}/play")
async def play_specific(uid: str, request: Request):
    """Host selects a specific song from played history or queue to play right now."""
    who = auth.identify(request)
    if not who.admin:
        raise HTTPException(403, "Only the host can select a song to play now")
    if queue.find_played(uid):
        res = await queue.play_played(uid)
    elif entry := queue.find(uid):
        queue.entries.remove(entry)
        if queue.current:
            queue.played.append(queue.current)
        queue.current = entry
        await queue.broadcast_state()
        res = entry
    else:
        res = None
    if not res:
        raise HTTPException(404, "Song not found")
    return {"now_playing": res}


@router.post("/{uid}/requeue")
async def requeue_song(uid: str, request: Request):
    """Return a previously played song back into the queue."""
    who, entry = _entry_for(request, uid)
    requeued = await queue.requeue(uid)
    if not requeued:
        raise HTTPException(404, "Song not found in played history")
    return {"ok": True, "entry": requeued}


@router.patch("/{uid}")
async def set_preferences(uid: str, req: PrefsRequest, request: Request):
    """Per-song guide-vocal volume and singing mode; the control panel applies them."""
    who, entry = _entry_for(request, uid)
    if queue.current and entry.get("uid") == queue.current.get("uid") and not who.admin:
        raise HTTPException(403, "Once a song starts playing, only the host can adjust vocals")
    return await queue.set_prefs(uid, guide=req.guide, mode=req.mode)
