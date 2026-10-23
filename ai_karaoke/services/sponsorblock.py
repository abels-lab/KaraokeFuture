"""SponsorBlock integration: detect non-music intros and skits in music videos.

Uses the community-curated 'music_offtopic' category from SponsorBlock to find
spoken dialogue, skits, and movie-style intros before the actual song starts.
This allows lyric aligners to skip the non-music portion and lets the player
start directly at the music.
"""
import json
import logging
import requests

from services import sources

log = logging.getLogger(__name__)

API_URL = "https://sponsor.ajay.app/api/skipSegments"
TIMEOUT_SEC = 3.0


def get_intro_end(song_id: str) -> float | None:
    """Return the end timestamp (seconds) of a non-music intro, or None.

    Only applies to YouTube videos. Never raises: on any network issue or when no
    segments exist, returns None.
    """
    if sources.source_of(song_id) != sources.YOUTUBE:
        return None

    try:
        response = requests.get(
            API_URL,
            params={"videoID": song_id, "categories": json.dumps(["music_offtopic"])},
            headers={"User-Agent": "ai-karaoke/1.0"},
            timeout=TIMEOUT_SEC,
        )
        if response.status_code != 200:
            return None

        segments = response.json()
        if not isinstance(segments, list):
            return None

        for item in segments:
            if item.get("category") == "music_offtopic" and item.get("actionType", "skip") == "skip":
                seg = item.get("segment") or []
                if len(seg) >= 2:
                    start, end = float(seg[0]), float(seg[1])
                    # An intro starts at or near 0 and lasts at least 3 seconds
                    if start <= 2.5 and end >= 3.0:
                        log.info("SponsorBlock intro found for %s: 0.0s - %.1fs", song_id, end)
                        return round(end, 2)
    except Exception as exc:
        log.debug("SponsorBlock lookup failed for %s: %s", song_id, exc)

    return None
