"""Playlist song items: 'Artist - Title' text or dicts, normalized to {query, title, artist, song_id}."""
import re
from typing import Any


def parse_song_text(item: str) -> tuple[str, str]:
    """Parse 'Artist - Title' into (title, artist). Fallback to (item, '')."""
    if " - " in item:
        artist, title = item.split(" - ", 1)
        return title.strip(), artist.strip()
    return item.strip(), ""


def normalize_song(item: Any) -> dict[str, Any]:
    """Normalize a playlist song item into a standard dict: {query, title, artist, song_id}."""
    if isinstance(item, str):
        item_str = item.strip()
        title, artist = parse_song_text(item_str)
        return {
            "query": item_str,
            "title": title or item_str,
            "artist": artist,
            "song_id": None,
        }
    if isinstance(item, dict):
        q = item.get("query") or item.get("title") or ""
        t = item.get("title") or q
        a = item.get("artist") or item.get("channel") or ""
        if not a and " - " in q:
            t, a = parse_song_text(q)
        return {
            "query": q,
            "title": t,
            "artist": a,
            "song_id": item.get("song_id") or item.get("id"),
        }
    s = str(item).strip()
    return {"query": s, "title": s, "artist": "", "song_id": None}


def slugify(text: str) -> str:
    """Generate safe filesystem slug from playlist name."""
    clean = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower()).strip("_")
    return clean[:48] or "playlist"
