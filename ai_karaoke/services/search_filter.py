"""Which search results guests may see at all: songs of a singable length, nothing else.

Results that fail are HIDDEN (never shown disabled): live streams, anything shorter than
"Shortest song allowed" or longer than "Longest song allowed" (the same rule the queue and
the downloader apply), and videos about a song rather than the song itself (tutorials,
reactions, hour-long loops...). Keywords match whole words only, and the list stays short on
purpose: a real song called "Review" is rare, a guest missing their song is worse.
"""
import re

from core import settings

_JUNK = re.compile(
    r"\b(tutorials?|reactions?|reacts|reacting|review|full album|interviews?|podcast|compilation|"
    r"documentary|vocal coach|first time hearing|live ?stream(ing)?|"
    r"(guitar|piano|drum|bass|ukulele|singing|vocal|cover) lessons?|lesson \d+|"
    r"how to (play|sing)|(1|one) hour|\d+ ?(hours?|hrs?) (loop|version|mix|of))\b",
    re.IGNORECASE,
)


def limits() -> tuple[int, int]:
    """(shortest, longest) allowed song length in seconds."""
    return int(settings.get("min_duration_sec")), int(settings.get("max_duration_min") * 60)


def duration_ok(seconds: float | None) -> bool:
    """Unknown length counts as not allowed: flat results without one are live or premieres."""
    shortest, longest = limits()
    return seconds is not None and shortest <= seconds <= longest


def duration_problem(seconds: float | None) -> str | None:
    """Plain-language reason a length is refused, or None when it is fine."""
    if seconds is None or duration_ok(seconds):
        return None
    shortest, longest = limits()
    if seconds < shortest:
        return f"Track is only {int(seconds)} s long (shortest allowed {shortest} s)"
    return f"Track is {int(seconds) // 60} min long (limit {longest // 60} min)"


def is_junk(title: str) -> bool:
    return bool(_JUNK.search(title or ""))


def keep(result: dict) -> bool:
    return not result.get("live") and duration_ok(result.get("duration")) and not is_junk(result.get("title"))
