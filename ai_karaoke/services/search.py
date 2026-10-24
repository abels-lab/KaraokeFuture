"""Smart song search: YouTube + SoundCloud, filtered, de-duplicated and checked.

1. Both sources are searched at once. Flat search is fast but says nothing about whether a
   result can actually be downloaded.
2. search_filter hides whatever isn't a singable song; search_merge folds uploads of the
   same recording into one result with mirrors.
3. The results about to be shown are opened in parallel, the way a download would open them
   (without downloading). A broken one is swapped for its first working mirror, or dropped.
   Checks that haven't answered within "Search check time" keep their result unchecked:
   the download falls back to the mirrors anyway. Measured: ~2 s on top of ~1.5 s search.
"""
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, wait

from core import cache_manager, settings
from services import search_filter, search_memory, search_merge, sources

log = logging.getLogger(__name__)
_pool = ThreadPoolExecutor(max_workers=16, thread_name_prefix="search")
MAX_TRIES = 3   # uploads opened per song before giving up on it
SPARES = 2      # extra songs checked so broken ones can be replaced


def _flat(source: str, query: str, count: int, stats: dict) -> list[dict]:
    try:
        return sources.flat_search(source, query, count)
    except Exception as exc:  # one source being down must not break the other
        log.warning("%s search failed for %r: %s", source, query, exc)
        stats["errors"].append(source)
        return []


def check(song_id: str) -> bool:
    """Can this upload be downloaded right now? (remembered for half an hour)"""
    known = search_memory.checked(song_id)
    if known is not None:
        return known
    try:
        info = sources.probe(song_id)
        ok = info.get("live_status") not in ("is_live", "is_upcoming") and search_filter.duration_ok(info.get("duration"))
    except Exception as exc:  # unavailable, private, geo-blocked, DRM, preview only...
        clean_reason = re.sub(r"^(?:Download failed:\s*)?(?:ERROR:\s*)?", "", str(exc).strip())
        log.info("Candidate %s unavailable: %s", song_id, clean_reason[:140])
        ok = False
    search_memory.record_check(song_id, ok)
    return ok


def _first_working(members: list[dict]) -> list[dict] | None:
    """The members from the first working one on (broken ones dropped), or None."""
    for i, member in enumerate(members[:MAX_TRIES]):
        if cache_manager.is_ready(member["id"]) or check(member["id"]):
            return members[i:]
    return None


def _validate(groups: list[list[dict]], stats: dict) -> list[list[dict]]:
    timeout = settings.get("search_check_seconds")
    if not timeout:
        stats["unchecked"] = len(groups)
        return groups
    futures = [_pool.submit(_first_working, g) for g in groups]
    done, _ = wait(futures, timeout=timeout)
    kept = []
    for members, future in zip(groups, futures):
        if future not in done:
            stats["unchecked"] += 1
            kept.append(members)
        elif future.exception() is not None:   # a bug in one check must not sink the whole search
            log.warning("Checking %s failed: %r", members[0]["id"], future.exception())
            stats["unchecked"] += 1
            kept.append(members)
        elif (working := future.result()) is None:
            stats["unavailable"] += 1
        else:
            stats["swapped"] += working[0] is not members[0]
            kept.append(working)
    return kept


def run(query: str, limit: int | None = None) -> tuple[list[dict], dict]:
    """(results, stats). Results keep the old fields (id, title, channel, duration,
    thumbnail, too_long, cached) plus source, url, key and mirrors."""
    started = time.perf_counter()
    limit = int(limit or settings.get("search_results"))
    stats = {"raw": 0, "hidden": 0, "merged": 0, "unavailable": 0, "swapped": 0, "unchecked": 0, "errors": []}
    use_sc = settings.get("use_soundcloud")
    youtube = _pool.submit(_flat, sources.YOUTUBE, query, max(10, limit * 2), stats)
    soundcloud = _pool.submit(_flat, sources.SOUNDCLOUD, query, max(5, limit), stats) if use_sc else None
    raw = youtube.result() + (soundcloud.result() if soundcloud else [])
    if len(stats["errors"]) == (2 if use_sc else 1):
        raise RuntimeError("no search source answered")
    kept = [r for r in raw if search_filter.keep(r)]
    groups = search_merge.merge(kept, cache_manager.is_ready)
    stats.update(raw=len(raw), hidden=len(raw) - len(kept), merged=len(kept) - len(groups),
                 soundcloud=sum(r["source"] == sources.SOUNDCLOUD for r in raw))
    shown = _validate(groups[:limit + SPARES], stats)[:limit]
    for members in shown:
        search_memory.remember(members)
    results = [search_merge.as_result(members, cache_manager.is_ready) for members in shown]
    stats.update(shown=len(results), ms=round((time.perf_counter() - started) * 1000))
    log.info("Search %r: %s", query, stats)
    return results, stats


def search(query: str, limit: int | None = None) -> list[dict]:
    query = (query or "").strip()
    return run(query, limit)[0] if query else []
