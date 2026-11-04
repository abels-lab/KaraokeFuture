"""Song search through the host's own links: a search or playlist page that yt-dlp can read.

The link is a URL template with {query}, e.g. https://vimeo.com/search?q={query} or a site's
own search page; yt-dlp supports well over a thousand sites. The filled-in page is opened
flat (no downloads) and every video on it becomes a search result. A YouTube or SoundCloud
video listed there keeps its normal id; anything else gets an "x_" id (core/source_ids.py) and
is downloaded through yt-dlp like the others. The URL is checked against the link rules
(core/source_links.py) first: public http(s) hosts only, never this laptop or the LAN.
"""
import logging

from yt_dlp import YoutubeDL

from core import source_ids
from core.source_links import LinkError, check_url, fill
from services import sources
from services.song_names import clean_channel, officialness, song_key

log = logging.getLogger(__name__)
TIMEOUT = 15   # seconds a custom search may take before search.run gives up on it


def _known(entry: dict) -> dict | None:
    """A YouTube / SoundCloud video listed on the page, as a normal result of that source."""
    key = (entry.get("ie_key") or entry.get("extractor_key") or "").lower()
    for name in (sources.YOUTUBE, sources.SOUNDCLOUD):
        if key.startswith(name):
            return sources.to_result(entry, name)
    return None


def _result(entry: dict, link: dict) -> dict | None:
    url = entry.get("webpage_url") or entry.get("url") or ""
    try:
        check_url(url, resolve=False)
    except LinkError:
        return None
    song_id = source_ids.make_id(url)
    title = entry.get("title") or "Unknown title"
    raw_channel = entry.get("channel") or entry.get("uploader") or link["name"]
    duration = entry.get("duration")
    thumbs = entry.get("thumbnails") or []
    return {
        "id": song_id, "title": title, "channel": clean_channel(raw_channel),
        "duration": int(round(duration)) if duration else None,
        "thumbnail": entry.get("thumbnail") or (thumbs[-1].get("url") if thumbs else None),
        "source": link["id"], "source_name": link["name"], "url": url,
        "live": entry.get("live_status") in ("is_live", "is_upcoming") or bool(entry.get("is_live")),
        "key": song_key(title, raw_channel), "title_key": song_key(title),
        "official": officialness(title, raw_channel),
    }


def search(link: dict, query: str, count: int) -> list[dict]:
    """Results from one custom song link (at most `count`). Raises on a bad link or a failed page."""
    url = check_url(fill(link["template"], query=query))
    with YoutubeDL({**sources.BASE_OPTS, "extract_flat": "in_playlist", "skip_download": True,
                    "playlistend": count}) as ydl:
        info = ydl.extract_info(url, download=False) or {}
    entries = info.get("entries")
    entries = list(entries)[:count] if entries is not None else [info]
    results = [_known(e) or _result(e, link) for e in entries if isinstance(e, dict)]
    results = [r for r in results if r]
    source_ids.remember([r["url"] for r in results if source_ids.PATTERN.match(r["id"])])
    log.info("Custom source %s: %d result(s) for %r", link["name"], len(results), query)
    return results
