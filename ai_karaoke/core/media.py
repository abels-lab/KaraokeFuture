"""URLs of a cached song's files, as the stage and the singing game load them."""
from config import INSTRUMENTAL_FILE, LYRICS_FILE, MELODY_FILE, VOCAL_MAP_FILE, VOCALS_FILE
from core import cache_manager


def media_urls(song_id: str) -> dict:
    base, meta = f"/media/{song_id}", cache_manager.read_meta(song_id)
    has = lambda name: name and cache_manager.song_file(song_id, name).is_file()  # noqa: E731
    return {"instrumental": f"{base}/{INSTRUMENTAL_FILE}",
            "vocals": f"{base}/{VOCALS_FILE}", "lyrics": f"{base}/{LYRICS_FILE}",
            "lyrics_source": meta.get("lyrics_source"),
            "video": f"{base}/{meta['video']}" if has(meta.get("video")) else None,
            "vocal_map": f"{base}/{VOCAL_MAP_FILE}" if has(VOCAL_MAP_FILE) else None,
            "melody": f"{base}/{MELODY_FILE}" if has(MELODY_FILE) else None}
