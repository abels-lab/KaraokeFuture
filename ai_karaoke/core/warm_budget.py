"""How much of the cache the warm-up may use, and making room for its next song.

Warmed songs (prepared in the background, never played) may use "Cache share for warm-up"
of the cache limit. Before a warm-up song starts, unplayed warmed songs of an OLD rotation
are deleted (oldest first) until the new one fits — both into that share and into the whole
cache. If it still doesn't fit, the song is not started: a warm-up never deletes a guest's
song, and never pushes the cache over its limit.
"""
import logging
import statistics

from config import CACHE_HEADROOM_BYTES
from core import cache_manager, eviction, settings

log = logging.getLogger(__name__)
DEFAULT_SONG_BYTES = 150 * 1024**2   # stems + video of a 4-minute song, before we know better


def _songs() -> list[dict]:
    return cache_manager.list_songs()


def stale_ids() -> set[str]:
    return {s["id"] for s in _songs() if eviction.is_stale_warm(s)}


def estimate(songs: list[dict]) -> int:
    """Typical size of a finished song in this cache."""
    sizes = [s["size"] for s in songs if s.get("ready")]
    return int(statistics.median(sizes)) if sizes else DEFAULT_SONG_BYTES


def usage(songs: list[dict] | None = None) -> dict:
    songs = _songs() if songs is None else songs
    limit = settings.get("cache_limit_gb") * 1024**3
    return {"total": sum(s["size"] for s in songs), "limit": limit,
            "warm": sum(s["size"] for s in songs if eviction.is_warm(s)),
            "budget": limit * settings.get("warm_budget_pct") / 100}


def make_room(protect: set[str]) -> bool:
    """True when one more song fits; deletes stale warm-ups (never `protect`) if needed."""
    while True:
        songs = _songs()
        need, used = max(estimate(songs), CACHE_HEADROOM_BYTES), usage(songs)
        if used["warm"] + need <= used["budget"] and used["total"] + need <= used["limit"]:
            return True
        stale = {s["id"] for s in songs if eviction.is_stale_warm(s)}
        victims = [i for i in eviction.order(songs) if i in stale and i not in protect]
        if not victims:
            log.info("Warm-up budget full: %.2f GB warm of %.2f GB, cache %.2f of %.2f GB",
                     used["warm"] / 1024**3, used["budget"] / 1024**3, used["total"] / 1024**3, used["limit"] / 1024**3)
            return False
        cache_manager.evict(victims[0])


def keep_for(song_id: str, rotation: str) -> None:
    """An already-warmed song picked again: it belongs to the current rotation now."""
    meta = cache_manager.read_meta(song_id)
    if eviction.is_warm(meta) and meta.get("rotation") != rotation:
        cache_manager.update_meta(song_id, rotation=rotation)
