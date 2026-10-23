"""Which cached songs go first when space is needed (pure rules, easy to test).

1. Warmed-up songs (prepared in the background, see core/warmer.py) that nobody ever
   played and that belong to an older rotation: they were a guess that didn't pay off.
2. Then everything else, least recently used first (warmed songs of the current rotation
   compete normally; a played warmed song is an ordinary song).
Songs that are queued, playing or being processed are never evicted (the caller's protect).
"""
current_rotation: str | None = None   # set by the warmer when a rotation starts


def last_access(meta: dict) -> float:
    return float(meta.get("last_accessed") or meta.get("created") or 0)


def is_warm(meta: dict) -> bool:
    """Prepared by the warm-up and never played since."""
    return bool(meta.get("warmed_at")) and not meta.get("played_at")


def is_stale_warm(meta: dict, rotation: str | None = None) -> bool:
    return is_warm(meta) and meta.get("rotation") != (rotation if rotation is not None else current_rotation)


def order(metas: list[dict], rotation: str | None = None) -> list[str]:
    """Song ids in the order they should be evicted."""
    stale = sorted((m for m in metas if is_stale_warm(m, rotation)), key=last_access)
    stale_ids = {m["id"] for m in stale}
    rest = sorted((m for m in metas if m["id"] not in stale_ids), key=last_access)
    return [m["id"] for m in stale + rest]
