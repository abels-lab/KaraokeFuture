"""What each worker job does. core/worker.py decides WHEN a job runs; this decides HOW.

Every function gets the worker for its stage reporting, protected ids and queue state.
Returning False means "paused at a stage boundary": the worker puts the job back in line.
"""
import asyncio
import logging
import time

from core import cache_manager, eviction, pipeline, warm_budget
from core.hub import hub
from core.queue_manager import queue
from services import downloader, lyrics_aligner

log = logging.getLogger(__name__)


async def dispatch(w, kind: str, song_id: str) -> bool:
    """Run one job; False = paused at a stage boundary, to be resumed later."""
    if kind == "lyrics":
        await _realign(w, song_id)
    elif kind == "video":
        await w.report(song_id, "downloading")
        if await asyncio.to_thread(downloader.download_video, song_id):
            await queue.media_updated(song_id)
    elif kind == "melody" and cache_manager.is_ready(song_id):
        await w.report(song_id, "melody")
        await pipeline.melody_step(song_id)
        await queue.media_updated(song_id)
    elif kind == "rebuild":
        cache_manager.evict(song_id)
        await queue.reset_song(song_id)
        await _process(w, song_id)
    elif kind == "warm":
        return await _warm(w, song_id)
    elif queue.has_song(song_id):
        await _process(w, song_id)
    else:
        log.info("Skipping %s: removed from queue before processing", song_id)
    return True


def guest_protect(w) -> set[str]:
    """Never evict what is queued, playing or has work pending."""
    return queue.protected_ids() | w.busy_ids()


async def _realign(w, song_id: str) -> None:
    if not cache_manager.is_ready(song_id):  # not processed yet: the pipeline reads the text
        return
    w.stages[song_id] = "aligning"
    await hub.broadcast({"type": "library"})
    meta = cache_manager.read_meta(song_id)
    await asyncio.to_thread(lyrics_aligner.generate_lyrics, song_id,
                            meta.get("title", ""), meta.get("channel", ""))
    await pipeline.melody_step(song_id)  # notes are tagged with lyric words: refresh them too
    await queue.media_updated(song_id)


async def _process(w, song_id: str) -> None:
    """A guest's song: every unfinished stage, never paused."""
    if not cache_manager.is_ready(song_id):
        started = time.perf_counter()
        await pipeline.run(song_id, w.report, lambda: guest_protect(w))
        cache_manager.update_meta(song_id, status="ready", last_accessed=time.time())
        log.info("%s ready in %.0fs", song_id, time.perf_counter() - started)
    await queue.set_song_status(song_id, "ready")


async def _warm(w, song_id: str) -> bool:
    """A popular song prepared in the background; pauses whenever a guest's job waits."""
    rotation = w.warm_rotation.get(song_id) or eviction.current_rotation or ""
    if cache_manager.is_ready(song_id):
        warm_budget.keep_for(song_id, rotation)
        return True
    if not cache_manager.song_dir(song_id).is_dir() and not warm_budget.make_room(guest_protect(w)):
        log.info("Warm-up skips %s: its cache budget is full", song_id)
        return True

    def protect() -> set[str]:  # a warm-up may only evict unplayed old warm-ups, never a guest's song
        return (cache_manager.song_ids() - warm_budget.stale_ids()) | guest_protect(w)

    if not await pipeline.run(song_id, w.report, protect, w.high_waiting):
        return False
    cache_manager.update_meta(song_id, status="ready", warmed_at=time.time(), rotation=rotation)
    await queue.set_song_status(song_id, "ready")   # a guest may have queued it meanwhile
    log.info("Warmed up %s (rotation %s)", song_id, rotation)
    return True
