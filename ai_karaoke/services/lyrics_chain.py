"""The order lyric text is looked for online, as set in Settings › Sources.

Synced lyrics first (they carry line timing), then plain lyrics, then chord sheets; within each
kind the host's order, skipping what is switched off (core/sources_registry.py). The host's own
lyrics links are plain-lyrics sources. Each source is tried until one returns enough lines.
"""
import logging
from typing import Callable, Iterator

import syncedlyrics

from core import settings, sources_registry
from services import custom_lyrics, genius, guitar_tabs, lrclib

log = logging.getLogger(__name__)
KINDS = ("synced", "lyrics", "chords")


def _fetcher(entry: dict, query: str, plain: str, channel: str, duration: float | None) -> Callable[[], str | None]:
    sid = entry["id"]
    if not entry["builtin"]:
        return lambda: custom_lyrics.fetch(entry, query, channel)
    return {
        "lrclib": lambda: lrclib.search(query, duration) if duration else None,
        "syncedlyrics": lambda: syncedlyrics.search(query),
        "genius": lambda: genius.fetch(query, plain),
        "ultimate-guitar": lambda: guitar_tabs.fetch_ultimate_guitar(query, plain),
        "amdm": lambda: guitar_tabs.fetch_amdm(query, plain),
    }.get(sid, lambda: None)


def found(query: str, plain: str, channel: str = "", duration: float | None = None) -> Iterator[tuple[str, str]]:
    """(source name, raw text) from each switched-on source in order, lazily: stop iterating
    once the text is good enough and later sites are never asked."""
    for kind in KINDS:
        if kind == "chords" and not settings.get("use_chords_lyrics"):
            continue
        for entry in sources_registry.ordered(kind):
            try:
                raw = _fetcher(entry, query, plain, channel, duration)()
            except Exception as exc:   # providers fail in many ways; never block the pipeline
                log.warning("%s failed for %r: %s", entry["name"], query, exc)
                continue
            if raw:
                yield entry["name"], raw
