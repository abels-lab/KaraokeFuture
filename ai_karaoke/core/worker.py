"""Sequential background worker: one job at a time, guests' jobs before warm-ups.

A single asyncio task takes the most urgent job from a priority queue (core/jobs.py); each
blocking step runs in a thread via asyncio.to_thread and is awaited before the next starts,
so the separator, Whisper/MMS and CREPE are never in VRAM together.
Jobs: process | lyrics | rebuild | video | melody (HIGH) and warm (LOW, core/warmer.py);
what each one does lives in core/worker_jobs.py.
A running warm-up pauses at its next stage boundary when a HIGH job arrives, goes back in
the queue and later resumes from the first unfinished stage (core/pipeline.py). Worst case
for a guest: waiting for the one warm-up stage that is running (see core/pipeline.py).
"""
import asyncio
import contextlib
import logging

from core import cache_manager, warm_budget, worker_jobs
from core.hub import hub
from core.jobs import HIGH, LOW, JobQueue
from core.queue_manager import queue

log = logging.getLogger(__name__)


class Worker:
    def __init__(self) -> None:
        self._jobs: JobQueue | None = JobQueue()
        self._pending: set[tuple[str, str]] = set()   # (kind, song_id), queued or running
        self._task: asyncio.Task | None = None
        self.current_song: str | None = None   # guest song being processed (the TV shows it)
        self.current_job: tuple[str, str] | None = None   # any job, warm-ups included
        self.stages: dict[str, str] = {}   # song_id -> waiting|downloading|separating|aligning|melody
        self.warm_rotation: dict[str, str] = {}   # song_id -> rotation, for queued warm-ups

    def start(self) -> None:
        """Call from inside the running event loop (FastAPI lifespan)."""
        if self._jobs is None:
            self._jobs = JobQueue()
        self._task = asyncio.create_task(self._run(), name="karaoke-worker")
        log.info("Background worker started")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    # ── Submitting (HIGH unless said otherwise) ──────────────────────────────
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

    async def submit_warm(self, song_id: str, rotation: str) -> None:
        """LOW: prepare a popular song in the background, only while no guest is waiting."""
        if cache_manager.is_ready(song_id):
            warm_budget.keep_for(song_id, rotation)
            return
        self.warm_rotation[song_id] = rotation
        await self._put(("warm", song_id), LOW)

    # ── State ────────────────────────────────────────────────────────────────
    def busy_ids(self) -> set[str]:
        """Songs with work queued or running: never evict them."""
        return set(self.stages)

    def high_waiting(self) -> bool:
        return bool(self._jobs is not None and self._jobs.high_waiting())

    def backlog(self) -> dict:
        jobs = self._jobs
        return {"high": jobs.count(HIGH) if jobs is not None else 0, "low": jobs.count(LOW) if jobs is not None else 0}

    async def report(self, song_id: str, stage: str) -> None:
        """Stage shown in the library and on queue entries of this song."""
        self.stages[song_id] = stage
        await queue.set_song_status(song_id, stage)
        await hub.broadcast({"type": "library"})

    async def _put(self, job: tuple[str, str], priority: int = HIGH) -> None:
        if job not in self._pending:
            self._pending.add(job)
            self.stages.setdefault(job[1], "waiting")
            if self._jobs is not None:
                self._jobs.put(job, priority)
            await hub.broadcast({"type": "library"})

    # ── Running ──────────────────────────────────────────────────────────────
    async def _run(self) -> None:
        while True:
            priority, seq, job = await self._jobs.get()
            kind, song_id = job
            self.current_job, finished = job, True
            self.current_song = song_id if priority == HIGH else None
            try:
                finished = await worker_jobs.dispatch(self, kind, song_id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.exception("%s job for %s failed", kind, song_id)
                if kind in ("process", "rebuild", "warm"):  # failed lyrics/video jobs keep the playable song
                    cache_manager.evict(song_id)
                    await queue.set_song_status(song_id, "error", str(exc)[:200])
                if kind == "warm":
                    await asyncio.sleep(5.0)  # cooldown on warm-up error to avoid tripping bot rate limits
            finally:
                self.current_song = self.current_job = None
                if finished:
                    self._pending.discard(job)
                    if kind == "warm":
                        self.warm_rotation.pop(song_id, None)
                    if not any(s == song_id for _, s in self._pending):
                        self.stages.pop(song_id, None)
                else:  # paused for a guest: back in line, ahead of later warm-ups
                    self._jobs.put(job, priority, seq)
                    self.stages[song_id] = "waiting"
                await hub.broadcast({"type": "library"})


worker = Worker()
