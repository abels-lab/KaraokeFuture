"""Where songs come from: YouTube (primary) and SoundCloud (extra results and fallback).

Song ids double as cache folder names and URL parts, so each source has a strict id shape:
- YouTube keeps its plain 11-character ids, so every existing cache folder stays valid.
- SoundCloud ids are "sc_" + the numeric track id padded to at least 10 digits. That makes
  them 13+ characters long, so one can never look like (or collide with) a YouTube id.

YouTube Music is not a separate source: yt-dlp's music search took ~25 s for one query (it
pages through every result) and returns neither duration nor artist, so results can't be
filtered or de-duplicated; its songs are ordinary YouTube ids that ytsearch finds anyway.
"""
import logging
import re

from yt_dlp import YoutubeDL

from services.song_names import clean_channel, officialness, song_key

log = logging.getLogger(__name__)

YOUTUBE, SOUNDCLOUD = "youtube", "soundcloud"
_YT_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_SC_ID = re.compile(r"^sc_(\d{10,15})$")
_SEARCH = {YOUTUBE: "ytsearch", SOUNDCLOUD: "scsearch"}
# SoundCloud "Go+" tracks only offer a 30 s preview to us: never pick that stream
_AUDIO_FORMAT = {YOUTUBE: "bestaudio/best", SOUNDCLOUD: "bestaudio[format_id!*=preview]/best[format_id!*=preview]"}


class _Quiet:
    """yt-dlp prints ERROR lines even when quiet; failures are reported by the callers."""
    def debug(self, msg): pass
    def info(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): log.debug("yt-dlp: %s", msg)


BASE_OPTS = {"quiet": True, "no_warnings": True, "noplaylist": True, "socket_timeout": 10, "logger": _Quiet()}


def source_of(song_id: str | None) -> str | None:
    if song_id and _YT_ID.match(song_id):
        return YOUTUBE
    if song_id and _SC_ID.match(song_id):
        return SOUNDCLOUD
    return None


def is_valid_id(song_id: str | None) -> bool:
    return source_of(song_id) is not None


def soundcloud_id(track_id) -> str:
    return f"sc_{int(track_id):010d}"


def page_url(song_id: str) -> str:
    if source_of(song_id) == SOUNDCLOUD:
        return f"https://api.soundcloud.com/tracks/{int(song_id[3:])}"
    return f"https://www.youtube.com/watch?v={song_id}"


def audio_format(song_id: str) -> str:
    return _AUDIO_FORMAT[source_of(song_id)]


def has_video(song_id: str) -> bool:
    """SoundCloud is audio only."""
    return source_of(song_id) == YOUTUBE


def thumbnail(song_id: str, artwork: str | None = None) -> str | None:
    if source_of(song_id) == YOUTUBE:
        return f"https://i.ytimg.com/vi/{song_id}/hqdefault.jpg"
    # SoundCloud "original" artwork can be 3000 px: the 500 px size is plenty for a phone
    return artwork.replace("-original.", "-t500x500.") if artwork else None


def _artwork(entry: dict) -> str | None:
    thumbs = entry.get("thumbnails") or []
    return entry.get("thumbnail") or (thumbs[-1].get("url") if thumbs else None)


def to_result(entry: dict, source: str) -> dict | None:
    """One yt-dlp entry (flat or full) as a search result, or None for an unusable id."""
    raw_id = entry.get("id")
    song_id = soundcloud_id(raw_id) if source == SOUNDCLOUD and str(raw_id or "").isdigit() else raw_id
    if source_of(song_id) != source:
        return None
    title = entry.get("title") or "Unknown title"
    raw_channel = entry.get("channel") or entry.get("uploader") or ""
    duration = entry.get("duration")
    return {
        "id": song_id, "title": title, "channel": clean_channel(raw_channel),
        "duration": int(round(duration)) if duration else None,
        "thumbnail": thumbnail(song_id, _artwork(entry)), "source": source,
        "url": entry.get("webpage_url") or page_url(song_id),
        "live": entry.get("live_status") in ("is_live", "is_upcoming") or bool(entry.get("is_live")),
        "key": song_key(title, raw_channel), "official": officialness(title, raw_channel),
    }


def flat_search(source: str, query: str, count: int) -> list[dict]:
    """Fast search without opening each result (so availability is NOT known yet)."""
    opts = {**BASE_OPTS, "extract_flat": "in_playlist", "skip_download": True}
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"{_SEARCH[source]}{count}:{query}", download=False)
    results = [to_result(entry, source) for entry in info.get("entries") or []]
    return [r for r in results if r]


def probe(song_id: str) -> dict:
    """Open one result like a download would (without downloading): raises when it is
    unavailable, private, geo-blocked, DRM-protected or only a preview. Returns the info."""
    with YoutubeDL({**BASE_OPTS, "format": audio_format(song_id), "skip_download": True}) as ydl:
        return ydl.extract_info(page_url(song_id), download=False)
