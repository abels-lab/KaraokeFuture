"""Background warm-up: keeps a rotating set of karaoke classics ready to sing instantly.

Shortly after startup and then every "Check every" hours, the current rotation's songs
(data/top_hits.json, the next block of "Songs per rotation" each week) are found through the
normal smart search and handed to the worker as LOW-priority jobs. They run through the
full pipeline only while no guest is waiting, never push the cache past its limit
(core/warm_budget.py) and are marked in meta.json (warmed_at, rotation). They are not
queue entries; once played they count as ordinary songs.
"""
import asyncio
import contextlib
import datetime as dt
import json
import logging

from config import TOP_HITS_FILE, WARM_START_DELAY_SEC
from core import eviction, settings
from core.worker import worker
from services import search
from services.song_names import song_key

log = logging.getLogger(__name__)


def load_hits() -> list[str]:
    try:
        hits = json.loads(TOP_HITS_FILE.read_text(encoding="utf-8")).get("hits") or []
    except (OSError, ValueError) as exc:
        log.warning("No warm-up list (%s): %s", TOP_HITS_FILE, exc)
        return []
    return [h.strip() for h in hits if isinstance(h, str) and h.strip()]


def pick(hits: list[str], count: int, today: dt.date | None = None) -> tuple[str, list[str]]:
    """(rotation id, songs): week N takes the N-th block of `count` songs, wrapping around,
    so the choice is the same all week and the whole list gets its turn."""
    if not hits or count <= 0:
        return "", []
    year, week, _ = (today or dt.date.today()).isocalendar()
    block = (year * 53 + week) * count
    chosen = [hits[(block + i) % len(hits)] for i in range(min(count, len(hits)))]
    return f"{year}-W{week:02d}", chosen


def choose(hit: str, results: list[dict]) -> dict | None:
    """The search result that really is this song (not a cover, live or karaoke take)."""
    wanted = song_key(hit)
    exact = next((r for r in results if r.get("key") == wanted), None)
    words = set(wanted.split())
    return exact or next((r for r in results if "|" not in r.get("key", "|")
                          and words <= set(r["key"].split())), None)


async def run_once(count: int | None = None) -> list[str]:
    """Queue the current rotation's songs for warming. Returns the song ids handed over."""
    rotation, hits = pick(load_hits(), int(settings.get("warm_count") if count is None else count))
    eviction.current_rotation = rotation
    handed: list[str] = []
    for hit in hits:
        await asyncio.sleep(1.0)  # polite pacing between warm-up searches
        try:
            results = await asyncio.to_thread(search.search, hit)
        except Exception as exc:  # network trouble: try again next round
            log.warning("Warm-up search failed for %r: %s", hit, exc)
            continue
        if (best := choose(hit, results)) is None:
            log.info("Warm-up found no clean match for %r", hit)
            continue
        await worker.submit_warm(best["id"], rotation)
        handed.append(best["id"])
    log.info("Warm-up rotation %s: %d of %d song(s) handed to the worker", rotation, len(handed), len(hits))
    return handed


class Warmer:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop(), name="karaoke-warmer")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _loop(self) -> None:
        await asyncio.sleep(WARM_START_DELAY_SEC)
        while True:
            if settings.get("warm_enabled") and settings.get("warm_count"):
                try:
                    await run_once()
                except Exception:
                    log.exception("Warm-up round failed")
            await asyncio.sleep(settings.get("warm_interval_h") * 3600)


warmer = Warmer()
