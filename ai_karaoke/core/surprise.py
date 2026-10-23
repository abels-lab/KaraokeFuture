"""'I don't know what to sing': a random song that is ready to start instantly.

Only fully processed songs qualify (no waiting), never one that is queued or playing, and
not one sung in the last hour (nobody wants the same song twice in a row). Preference, in
order: this week's warmed-up karaoke classics (core/warmer.py) — chosen because they are
crowd-pleasers — then any other warmed song, then the rest of the library. If everything
ready was sung within the hour, an hour-old repeat beats no song at all.
"""
import random
import time

from core import cache_manager, eviction

RECENT_SECONDS = 3600


def pick(exclude: set[str], now: float | None = None) -> dict | None:
    """The chosen song's meta (with "id"), or None when nothing ready is free."""
    now = time.time() if now is None else now
    free = [m for m in cache_manager.list_songs() if m.get("ready") and m["id"] not in exclude]
    fresh = [m for m in free if now - float(m.get("played_at") or 0) > RECENT_SECONDS]
    rotation = eviction.current_rotation
    tiers = (
        [m for m in fresh if m.get("warmed_at") and rotation and m.get("rotation") == rotation],
        [m for m in fresh if m.get("warmed_at")],
        fresh,
        free,
    )
    for tier in tiers:
        if tier:
            return random.choice(tier)
    return None
