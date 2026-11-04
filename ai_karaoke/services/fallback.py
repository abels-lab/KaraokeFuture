"""Which uploads a download may try, in order, when the chosen one fails.

1. the upload the guest picked (its id stays the song's id everywhere: queue, cache, TV),
2. its mirrors from the search (same normalised artist + title, length within ±5 s) whose
   source is still switched on, in the host's source order (Settings › Sources),
3. a SoundCloud match found now (same key and length), when SoundCloud is switched on.
The audio actually used is recorded in meta.json (source, source_id, source_url).
"""
import logging
from typing import Iterator

from core import cache_manager, sources_registry
from services import search_filter, search_memory, search_merge, song_names, sources
from services.song_names import build_query

log = logging.getLogger(__name__)


def _hint(song_id: str) -> dict:
    """What the search knew about the song, else what an earlier download stored."""
    hint = search_memory.hint(song_id) or {}
    meta = cache_manager.read_meta(song_id)
    for key in ("title", "channel", "duration", "key", "mirrors"):
        if not hint.get(key) and meta.get(key):
            hint[key] = meta[key]
    return hint


def soundcloud_matches(hint: dict, exclude: set[str]) -> list[str]:
    """SoundCloud uploads of the same song (same key, length within the tolerance)."""
    if not hint.get("title") or not hint.get("key") or not hint.get("duration"):
        return []
    query = build_query(hint["title"], hint.get("channel") or "")
    try:
        found = sources.flat_search(sources.SOUNDCLOUD, query, 8)
    except Exception as exc:
        log.warning("SoundCloud fallback search failed for %r: %s", query, exc)
        return []
    tolerance = search_merge.DURATION_TOLERANCE
    return [r["id"] for r in found if r["id"] not in exclude and search_filter.keep(r)
            and song_names.same_song(r, hint) and abs(r["duration"] - hint["duration"]) <= tolerance]


def _kind(upload_id: str) -> str:
    """The registry id of an upload's source (a custom upload is ranked by its own link)."""
    source = sources.source_of(upload_id)
    return (search_memory.hint(upload_id) or {}).get("source", source) if source == sources.CUSTOM else source


def _allowed(upload_id: str) -> bool:
    """Backups only come from switched-on sources (the guest's own pick is always tried)."""
    kind = _kind(upload_id)
    return kind == sources.CUSTOM or sources_registry.enabled(kind)


def candidates(song_id: str) -> Iterator[str]:
    """Ids to try, best first. The SoundCloud search only runs if everything else failed."""
    hint = _hint(song_id)
    tried = [song_id]
    yield song_id
    mirrors = [m for m in hint.get("mirrors") or [] if sources.is_valid_id(m) and _allowed(m)]
    for mirror in sorted(mirrors, key=lambda m: sources_registry.rank(_kind(m))):   # stable: search rank within a source
        if mirror not in tried:
            tried.append(mirror)
            log.info("Trying mirror %s for %s", mirror, song_id)
            yield mirror
    if sources_registry.enabled(sources.SOUNDCLOUD):
        for match in soundcloud_matches(hint, set(tried)):
            log.info("Trying SoundCloud match %s for %s", match, song_id)
            yield match
