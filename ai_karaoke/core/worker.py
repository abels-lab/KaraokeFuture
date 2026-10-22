"""Sequential background worker: download -> separate -> UltraStar file or align + melody.

One asyncio task runs one job at a time, each blocking step in a thread, so no two models are
ever in VRAM together. Jobs: process | lyrics | rebuild | video | melody.
"""
import asyncio
import contextlib
import logging
import time

from core import cache_manager, settings
from core.hub import hub
from core.queue_manager import queue
from services import downloader, lyrics_aligner, melody, separator, ultrastar_source

log = logging.getLogger(__name__)


class Worker:
    def __init__(self) -> None:
        self._jobs: asyncio.Queue[tuple[str, str]] | None = None   # (kind, song_id)
        self._pending: set[tuple[str, str]] = set()
        self._task: asyncio.Task | None = None
        self.current_song: str | None = None
        self.stages: dict[str, str] = {}   # song_id -> waiting|downloading|separating|aligning

    def start(self) -> None:
        """Call from inside the running event loop (FastAPI lifespan)."""
        self._jobs = asyncio.Queue()
        self._task = asyncio.create_task(self._run(), name="karaoke-worker")
        log.info("Background worker started")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def submit(self, song_id: str) -> None:
        """Enqueue a song once; duplicates and cached songs are skipped."""
        if not cache_manager.is_ready(song_id):
            await self._put(("process", song_id))

    async def submit_lyrics(self, song_id: str) -> None:
        """Re-align lyrics (pasted, edited or reset to automatic), after earlier jobs."""
        await self._put(("lyrics", song_id))

    async def submit_rebuild(self, song_id: str) -> None:  # throw away the cache, run it all again
        await self._put(("rebuild", song_id))

    async def submit_video(self, song_id: str) -> None:  # songs cached before videos existed
        await self._put(("video", song_id))

    async def submit_melody(self, song_id: str) -> None:  # songs cached before the singing game
        await self._put(("melody", song_id))

    async def _melody(self, song_id: str) -> None:  # never fails the song: it plays without scoring
        try:
            await asyncio.to_thread(melody.extract, song_id)
        except Exception:
            log.exception("Melody extraction failed for %s", song_id)

    async def _put(self, job: tuple[str, str]) -> None:
        if job not in self._pending:
            self._pending.add(job)
            self.stages.setdefault(job[1], "waiting")
            await self._jobs.put(job)
            await hub.broadcast({"type": "library"})

    async def _stage(self, song_id: str, stage: str, status: bool = True) -> None:
        self.stages[song_id] = stage
        if status:  # a re-sync keeps the song playable: its queue status stays untouched
            await queue.set_song_status(song_id, stage)
        await hub.broadcast({"type": "library"})

    async def _run(self) -> None:
        while True:
            kind, song_id = job = await self._jobs.get()
            self.current_song = song_id
            try:
                if kind == "lyrics":
                    await self._realign(song_id)
                elif kind == "video":
                    await self._stage(song_id, "downloading")
                    if await asyncio.to_thread(downloader.download_video, song_id):
                        await queue.media_updated(song_id)
                elif kind == "melody" and cache_manager.is_ready(song_id):
                    await self._stage(song_id, "melody")
                    await self._melody(song_id)
                    await queue.media_updated(song_id)
                elif kind == "rebuild":
                    cache_manager.evict(song_id)
                    await queue.reset_song(song_id)
                    await self._process(song_id)
                elif queue.has_song(song_id):
                    await self._process(song_id)
                else:
                    log.info("Skipping %s: removed from queue before processing", song_id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.exception("%s job for %s failed", kind, song_id)
                if kind in ("process", "rebuild"):  # failed lyrics/video jobs keep the playable song
                    cache_manager.evict(song_id)
                    await queue.set_song_status(song_id, "error", str(exc)[:200])
            finally:
                self.current_song = None
                self._pending.discard(job)
                if not any(s == song_id for _, s in self._pending):
                    self.stages.pop(song_id, None)
                self._jobs.task_done()
                await hub.broadcast({"type": "library"})

    async def _realign(self, song_id: str) -> None:
        if not cache_manager.is_ready(song_id):  # not processed yet: the pipeline reads the text
            return
        await self._stage(song_id, "aligning", status=False)
        await asyncio.to_thread(ultrastar_source.fetch_for, song_id)  # songs cached before USDB support
        await self._time_lyrics(song_id, status=False)
        await queue.media_updated(song_id)

    async def _time_lyrics(self, song_id: str, status: bool = True) -> None:  # UltraStar file, else align + pitch
        if not await asyncio.to_thread(ultrastar_source.apply, song_id):
            meta = cache_manager.read_meta(song_id)
            await asyncio.to_thread(lyrics_aligner.generate_lyrics, song_id, meta.get("title", ""), meta.get("channel", ""))
            await self._stage(song_id, "melody", status)
            await self._melody(song_id)  # notes are tagged with lyric words: refresh them too

    async def _process(self, song_id: str) -> None:
        if cache_manager.is_ready(song_id):
            await queue.set_song_status(song_id, "ready")
            return
        started = time.perf_counter()
        await self._stage(song_id, "downloading")
        await asyncio.to_thread(downloader.download, song_id, queue.protected_ids())
        await self._stage(song_id, "separating")
        # Network-only while the GPU separates: an UltraStar file and the video (neither raises)
        side = [asyncio.create_task(asyncio.to_thread(ultrastar_source.fetch_for, song_id))]
        if settings.get("download_video"):
            side.append(asyncio.create_task(asyncio.to_thread(downloader.download_video, song_id)))
        await asyncio.to_thread(separator.separate, song_id)
        await asyncio.gather(*side)
        await self._stage(song_id, "aligning")
        await self._time_lyrics(song_id)
        cache_manager.update_meta(song_id, status="ready", last_accessed=time.time())
        await queue.set_song_status(song_id, "ready")
        log.info("%s ready in %.0fs", song_id, time.perf_counter() - started)


worker = Worker()
