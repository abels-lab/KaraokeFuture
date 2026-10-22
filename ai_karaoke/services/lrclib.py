"""Synced lyrics from LRCLIB for the exact version of a song, matched by its duration.

syncedlyrics returns the first hit, often the album cut; a music-video edit or radio
version is shorter, so its LRC timestamps run past the end of our audio. LRCLIB lists
every upload with its duration, so we can pick the version that matches ours.
"""
import logging
import re

import requests

from core import settings

log = logging.getLogger(__name__)

SEARCH_URL = "https://lrclib.net/api/search"
_STAMP = re.compile(r"\[(\d{1,3}):(\d{1,2}(?:\.\d{1,3})?)\]")


def last_stamp(lrc: str) -> float | None:
    """Time of the last timestamped line with words (an empty "[02:20.02]" marks the song's end), or None."""
    stamps = [int(m) * 60 + float(s) for line in (lrc or "").splitlines() if _STAMP.sub("", line).strip()
              for m, s in _STAMP.findall(line)]
    return max(stamps) if stamps else None


def fits(lrc: str, duration: float | None) -> bool:
    """False when the LRC has lines timed after our audio ends: it is for another version."""
    last = last_stamp(lrc)
    return duration is None or last is None or last < duration - 1.0


def search(query: str, duration: float) -> str | None:
    """Synced LRC of the upload closest to `duration` (within the "lrclib_duration_diff" setting), else None."""
    for _ in range(2):  # LRCLIB answers 503 "server busy" now and then
        try:
            response = requests.get(SEARCH_URL, params={"q": query}, timeout=15,
                                    headers={"User-Agent": "ai-karaoke (local party app)"})
            if response.status_code == 503:
                continue
            response.raise_for_status()
            results = response.json()
            break
        except (requests.RequestException, ValueError) as exc:
            log.warning("LRCLIB search failed for %r: %s", query, exc)
            return None
    else:
        return None
    # Uploaded durations are sometimes wrong (album LRC labelled as the video edit): check the stamps too
    matches = [r for r in results if isinstance(r, dict) and r.get("syncedLyrics") and r.get("duration")
               and abs(r["duration"] - duration) <= settings.get("lrclib_duration_diff") and fits(r["syncedLyrics"], duration)]
    if not matches:
        return None
    best = min(matches, key=lambda r: abs(r["duration"] - duration))
    log.info("LRCLIB: %r matched %s - %s (%.0f s, ours %.0f s)", query, best.get("artistName"),
             best.get("trackName"), best["duration"], duration)
    return best["syncedLyrics"]
