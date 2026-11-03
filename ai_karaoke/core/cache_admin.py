"""Host tools for the song cache: usage numbers, trimming to the limit, clearing in bulk.

Nothing here ever deletes a protected song: playing, queued, recently played (the queue's
protected_ids) or with worker jobs pending (worker.busy_ids). On Windows a file being
streamed can't be removed, so "freed" is measured, not assumed.
"""
import shutil

from config import CACHE_DIR
from core import cache_manager, eviction, warm_budget


def protected() -> set[str]:
    from core.queue_manager import queue   # late imports: the worker imports this package
    from core.worker import worker
    return queue.protected_ids() | worker.busy_ids()


def stats() -> dict:
    songs, keep = cache_manager.list_songs(), protected()
    used = warm_budget.usage(songs)
    ready = [s for s in songs if s["ready"]]
    warm = [s for s in songs if eviction.is_warm(s)]
    kept = [s for s in songs if s["id"] in keep]
    return {
        "used": used["total"], "limit": used["limit"], "over_limit": used["total"] > used["limit"],
        "songs": len(songs), "ready": len(ready), "incomplete": len(songs) - len(ready),
        "warm_songs": len(warm), "warm_used": used["warm"], "warm_budget": used["budget"],
        "stale_warm": sum(1 for s in warm if eviction.is_stale_warm(s)),
        "protected": len(kept), "protected_used": sum(s["size"] for s in kept),
        "disk_free": shutil.disk_usage(CACHE_DIR).free,
    }


def trim() -> dict:
    """Evict until the cache fits its limit (after the limit was lowered, or a video overshot)."""
    before = cache_manager.total_size()
    evicted = cache_manager.ensure_space(protect=protected(), headroom=0)
    return {"evicted": evicted, "freed": max(0, before - cache_manager.total_size())}


def clear(what: str) -> dict:
    """what = "warm": unplayed warm-ups only; "all": every song that isn't protected."""
    if what not in ("warm", "all"):
        raise ValueError(f"Unknown cache selection: {what!r}")
    keep, before = protected(), cache_manager.total_size()
    songs = cache_manager.list_songs()
    victims = [s["id"] for s in songs if s["id"] not in keep and (what == "all" or eviction.is_warm(s))]
    for song_id in victims:
        cache_manager.evict(song_id)
    return {"evicted": victims, "freed": max(0, before - cache_manager.total_size())}
