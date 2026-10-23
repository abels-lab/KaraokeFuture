"""Priority job queue for the single background worker (event loop only, no locks needed).

HIGH = anything a guest or the host is waiting for (process, lyrics, rebuild, video, melody).
LOW  = background warm-up of popular songs.
A waiting HIGH job always runs before any waiting LOW job; among equals, first come first
served. A LOW job that was paused for a guest goes back with its original sequence number,
so it resumes before warm-ups that were queued after it.
"""
import asyncio
import heapq
import itertools

HIGH, LOW = 0, 1


class JobQueue:
    def __init__(self) -> None:
        self._heap: list[tuple[int, int, tuple[str, str]]] = []   # (priority, sequence, job)
        self._seq = itertools.count()
        self._wake = asyncio.Event()

    def put(self, job: tuple[str, str], priority: int = HIGH, seq: int | None = None) -> int:
        seq = next(self._seq) if seq is None else seq
        heapq.heappush(self._heap, (priority, seq, job))
        self._wake.set()
        return seq

    async def get(self) -> tuple[int, int, tuple[str, str]]:
        """(priority, sequence, job) of the most urgent job, waiting for one if needed."""
        while not self._heap:
            self._wake.clear()
            await self._wake.wait()
        return heapq.heappop(self._heap)

    def high_waiting(self) -> bool:
        """A guest is waiting: a running warm-up should pause at its next stage boundary."""
        return any(priority == HIGH for priority, _, _ in self._heap)

    def count(self, priority: int) -> int:
        return sum(p == priority for p, _, _ in self._heap)

    def __len__(self) -> int:
        return len(self._heap)
