"""What recent searches found, kept in memory for the download fallback and repeat searches.

- hints: every id a guest was shown -> its title, channel, length, key and mirror ids, so a
  download that fails later can switch to a mirror or a SoundCloud match of the same song.
- checks: availability checks (ok / failed) for half an hour, so searching the same song
  again doesn't re-open every result.
Both are bounded; losing them (restart) only costs a slower search or no fallback.
"""
import threading
import time
from collections import OrderedDict

_MAX_HINTS, _MAX_CHECKS, CHECK_TTL = 2000, 2000, 30 * 60
_lock = threading.Lock()
_hints: OrderedDict[str, dict] = OrderedDict()
_checks: OrderedDict[str, tuple[float, bool]] = OrderedDict()


def _put(store: OrderedDict, key: str, value, limit: int) -> None:
    store[key] = value
    store.move_to_end(key)
    while len(store) > limit:
        store.popitem(last=False)


def remember(members: list[dict]) -> None:
    """One song's uploads (best first): each id learns the others as its mirrors."""
    with _lock:
        for item in members:
            hint = {k: item.get(k) for k in ("title", "channel", "duration", "key", "source", "url", "thumbnail")}
            hint["mirrors"] = [m["id"] for m in members if m["id"] != item["id"]]
            _put(_hints, item["id"], hint, _MAX_HINTS)


def add_mirrors(song_id: str, mirrors: list[str], **fields) -> None:
    """Mirrors sent along with a queue request (e.g. after a server restart)."""
    with _lock:
        hint = dict(_hints.get(song_id) or {})
        for key, value in fields.items():
            hint.setdefault(key, value)
        known = hint.get("mirrors") or []
        hint["mirrors"] = known + [m for m in mirrors if m not in known and m != song_id]
        _put(_hints, song_id, hint, _MAX_HINTS)


def hint(song_id: str) -> dict | None:
    with _lock:
        found = _hints.get(song_id)
        return dict(found) if found else None


def checked(song_id: str) -> bool | None:
    """True/False from a recent availability check, None when unknown or too old."""
    with _lock:
        entry = _checks.get(song_id)
    if entry and time.time() - entry[0] < CHECK_TTL:
        return entry[1]
    return None


def record_check(song_id: str, ok: bool) -> None:
    with _lock:
        _put(_checks, song_id, (time.time(), ok), _MAX_CHECKS)
