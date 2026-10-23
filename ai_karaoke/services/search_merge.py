"""Merge uploads of the same recording into one search result with backup "mirrors".

Two results are the same song when their normalised artist + title (song_names.song_key)
match and their lengths differ by at most a few seconds (a live take or the music video
with a long intro differs more and stays separate). The guest sees one representative:
already cached first (instant), then the artist's own upload (Topic / VEVO / official),
then YouTube over SoundCloud (it has a video), then search rank. The others are kept as
`mirrors` so a failed download can switch to them automatically.
"""
from typing import Callable

from services.song_names import same_song

DURATION_TOLERANCE = 5   # seconds


def _same(group: list[dict], item: dict) -> bool:
    anchor = group[0]   # compare with the first upload so a chain of near-matches can't drift
    return (same_song(anchor, item) and anchor["duration"] is not None and item["duration"] is not None
            and abs(anchor["duration"] - item["duration"]) <= DURATION_TOLERANCE)


def group(results: list[dict]) -> list[list[dict]]:
    """Groups in order of their best-ranked member (results arrive YouTube first)."""
    groups: list[list[dict]] = []
    for item in results:
        match = next((g for g in groups if _same(g, item)), None)
        if match is None:
            groups.append([item])
        elif item["id"] not in {m["id"] for m in match}:
            match.append(item)
    return groups


def rank(members: list[dict], is_cached: Callable[[str], bool]) -> list[dict]:
    """Best representative first; `members` must be in search-rank order."""
    order = {m["id"]: i for i, m in enumerate(members)}
    return sorted(members, key=lambda m: (not is_cached(m["id"]), -m.get("official", 0),
                                          m["source"] != "youtube", order[m["id"]]))


def as_result(members: list[dict], is_cached: Callable[[str], bool]) -> dict:
    """The guest-facing result: the representative's fields + `mirrors` (ids, best first)."""
    best, *others = members
    result = {k: v for k, v in best.items() if k not in ("live", "official", "title_key")}
    return {**result, "cached": is_cached(best["id"]), "too_long": False,
            "mirrors": [m["id"] for m in others]}


def merge(results: list[dict], is_cached: Callable[[str], bool]) -> list[list[dict]]:
    """Grouped and ranked members, one list per distinct song."""
    return [rank(g, is_cached) for g in group(results)]
