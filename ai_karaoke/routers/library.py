"""Song library: browse cached songs, view/edit lyrics, regenerate, delete.

Everyone may browse and read lyrics; changing anything (lyrics, re-sync, rebuild, video,
delete) is for the host only (core/auth.py), checked here, not just hidden in the page.
"""
import asyncio
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core import auth, cache_manager, eviction, settings
from core.queue_manager import queue
from core.worker import worker
from services import downloader, lyrics_source, sources

router = APIRouter(prefix="/api")
HOST = [Depends(auth.require_admin)]


class LyricsRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20000)


class RegenerateRequest(BaseModel):
    target: Literal["lyrics", "all", "video"]   # re-sync lyrics | rebuild everything | fetch video
    reset: bool = False                # lyrics only: forget pasted text, detect automatically


def _check(song_id: str) -> None:
    if not sources.is_valid_id(song_id):
        raise HTTPException(400, "Invalid song id")


def _summary(meta: dict) -> dict:
    song_id = meta["id"]
    return {
        "id": song_id, "title": meta.get("title") or song_id, "channel": meta.get("channel", ""),
        "duration": meta.get("duration"), "thumbnail": meta.get("thumbnail"),
        "size": meta["size"], "ready": meta["ready"], "last_accessed": meta.get("last_accessed"),
        "lyrics_source": meta.get("lyrics_source"), "lyric_lines": meta.get("lyric_lines"),
        "has_user_lyrics": lyrics_source.load_user(song_id) is not None,
        "has_video": downloader.find_video(song_id) is not None,
        "unmatched_vocals": meta.get("unmatched_vocals") or [],   # sung parts the lyrics miss
        "timing_poor": bool((meta.get("timing") or {}).get("poor")),  # alignment lost its place
        "stage": worker.stages.get(song_id),
        "source": meta.get("source") or sources.source_of(song_id), "fallback_used": bool(meta.get("fallback_used")),
        "warmed": eviction.is_warm(meta), "rotation": meta.get("rotation"),
        "in_queue": queue.has_song(song_id), "playing": queue.is_playing(song_id),
    }


@router.get("/library")
async def library():
    songs = [_summary(m) for m in await asyncio.to_thread(cache_manager.list_songs)]
    return {"songs": songs, "used": sum(s["size"] for s in songs), "limit": settings.get("cache_limit_gb") * 1024**3}


@router.get("/songs/{song_id}/lyrics")
async def get_lyrics(song_id: str):
    _check(song_id)
    meta = cache_manager.read_meta(song_id)
    return {"text": lyrics_source.current_text(song_id), "source": meta.get("lyrics_source"),
            "has_user_lyrics": lyrics_source.load_user(song_id) is not None}


@router.post("/lyrics/{song_id}", dependencies=HOST)
async def save_lyrics(song_id: str, req: LyricsRequest):
    """Pasted or edited lyrics: saved permanently, then aligned by the worker in turn."""
    _check(song_id)
    try:
        lines = lyrics_source.save_user(song_id, req.text)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    await worker.submit_lyrics(song_id)
    return {"ok": True, "lines": lines}


@router.post("/songs/{song_id}/regenerate", dependencies=HOST)
async def regenerate(song_id: str, req: RegenerateRequest):
    _check(song_id)
    if not cache_manager.song_dir(song_id).is_dir():
        raise HTTPException(404, "Song is not in the cache")
    if req.target == "all":
        if queue.is_playing(song_id):
            raise HTTPException(409, "This song is playing right now — skip it first")
        await worker.submit_rebuild(song_id)
    elif req.target == "video":
        await worker.submit_video(song_id)
    else:
        if not cache_manager.is_ready(song_id):
            raise HTTPException(409, "The song is still being processed")
        if req.reset:  # back to automatic: forget pasted text and search online afresh
            lyrics_source.delete_user(song_id)
            lyrics_source.forget_online(song_id)
        await worker.submit_lyrics(song_id)
    return {"ok": True}


@router.delete("/songs/{song_id}", dependencies=HOST)
async def delete_song(song_id: str, lyrics: bool = False):
    """Remove a song from the cache; ?lyrics=true also forgets its pasted lyrics."""
    _check(song_id)
    if queue.has_song(song_id) or song_id in worker.stages:
        raise HTTPException(409, "Remove it from the queue first")
    cache_manager.evict(song_id)
    if lyrics:
        lyrics_source.delete_user(song_id)
    return {"ok": True}
