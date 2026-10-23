"""One song through the full pipeline, stage by stage, resumable at every stage boundary.

download -> separate (+ video in parallel) -> lyrics -> melody. Each stage is skipped when
its output already exists, so a warm-up that paused for a guest, or a song a guest queued
while it was being warmed, carries on where it stopped. Every stage runs in one thread and
is awaited before the next starts, so only one AI model is ever in VRAM.

A running stage is never interrupted (a GPU step can't be stopped safely mid-thread):
`should_yield` is asked only BETWEEN stages. The longest a guest waits behind a warm-up is
therefore one stage — in practice the vocal separation (about 1-2 min on an RTX 3060).
"""
import asyncio
import logging
from typing import Awaitable, Callable

from config import INSTRUMENTAL_FILE, LYRICS_FILE, MELODY_FILE, ORIGINAL_FILE, VOCALS_FILE
from core import cache_manager, settings
from services import downloader, lyrics_aligner, melody, separator, ultrastar_source

log = logging.getLogger(__name__)
Report = Callable[[str, str], Awaitable[None]]


def _has(song_id: str, *names: str) -> bool:
    return all(cache_manager.song_file(song_id, name).is_file() for name in names)


def _separated(song_id: str) -> bool:
    return _has(song_id, VOCALS_FILE, INSTRUMENTAL_FILE)


async def _download(song_id: str, protect: set[str]) -> None:
    await asyncio.to_thread(downloader.download, song_id, protect)


async def _separate(song_id: str, _protect: set[str]) -> None:
    # Network-only while the GPU separates: an UltraStar file and the video (neither raises)
    side = [asyncio.create_task(asyncio.to_thread(ultrastar_source.fetch_for, song_id))]
    if settings.get("download_video"):
        side.append(asyncio.create_task(asyncio.to_thread(downloader.download_video, song_id)))
    await asyncio.to_thread(separator.separate, song_id)
    await asyncio.gather(*side)


async def _lyrics(song_id: str, _protect: set[str]) -> None:
    if not await asyncio.to_thread(ultrastar_source.apply, song_id):
        meta = cache_manager.read_meta(song_id)
        await asyncio.to_thread(lyrics_aligner.generate_lyrics, song_id, meta.get("title", ""), meta.get("channel", ""))


async def melody_step(song_id: str, _protect: set[str] | None = None) -> None:
    """Never fails the song: it plays without scoring."""
    try:
        await asyncio.to_thread(melody.extract, song_id)
    except Exception:
        log.exception("Melody extraction failed for %s", song_id)


# (stage name shown to guests, step, "already done?" check)
STAGES = [
    ("downloading", _download, lambda s: _has(s, ORIGINAL_FILE) or _separated(s)),
    ("separating", _separate, _separated),
    ("aligning", _lyrics, lambda s: _has(s, LYRICS_FILE)),
    ("melody", melody_step, lambda s: _has(s, MELODY_FILE)),
]


async def run(song_id: str, report: Report, protect: Callable[[], set[str]],
              should_yield: Callable[[], bool] = lambda: False) -> bool:
    """Run every unfinished stage. False = paused before a stage because `should_yield`
    said so (call again later to resume); True = all stages done."""
    for name, step, done in STAGES:
        if done(song_id):
            continue
        if should_yield():
            log.info("Pausing %s before %s: a guest's job is waiting", song_id, name)
            return False
        await report(song_id, name)
        await step(song_id, protect())
    return True
