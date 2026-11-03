"""Lyrics tools: everyone may read a song's lyrics, only the host may change them (registry.py),
like the lyrics editor in the library."""
from typing import Any

from core import auth, cache_manager
from core.queue_manager import queue
from core.worker import worker
from services import lyrics_source, ultrastar_source


def _matches(item: dict, q: str) -> bool:
    return any(q in str(item.get(k, "")).lower() for k in ("title", "channel", "id", "song_id"))


def resolve_song(song_id: str | None = None, query: str | None = None) -> tuple[str | None, str | None, dict | None]:
    """(song id, title, meta) from an id, a title / artist query, or else the now playing / next song."""
    if song_id and cache_manager.song_dir(song_id).is_dir():
        meta = cache_manager.read_meta(song_id)
        return song_id, meta.get("title", song_id), meta
    snap = queue.snapshot()
    queued = [e for e in [snap.get("now_playing"), *snap.get("queue", [])] if e]
    if query:
        q = query.lower().strip()
        for item in queued:
            if _matches(item, q):
                sid = item.get("id") or item.get("song_id")
                return sid, item.get("title"), cache_manager.read_meta(sid)
        for s in cache_manager.list_songs():
            if _matches(s, q):
                return s["id"], s.get("title", s["id"]), s
    if queued:
        sid = queued[0].get("id") or queued[0].get("song_id")
        return sid, queued[0].get("title"), cache_manager.read_meta(sid)
    return None, None, None


NO_SONG = "Could not tell which song you mean: name it, or have one playing or queued."


def get_lyrics(who: auth.Who, args: dict) -> dict[str, Any]:
    song_id, title, meta = resolve_song(args.get("song_id"), args.get("query"))
    if not song_id:
        return {"error": NO_SONG}
    text = lyrics_source.current_text(song_id)
    if not text:
        return {"song_id": song_id, "title": title, "text": "", "line_count": 0, "has_user_lyrics": False,
                "status": "no_lyrics_found"}
    return {"song_id": song_id, "title": title, "has_user_lyrics": lyrics_source.load_user(song_id) is not None,
            "source": meta.get("lyrics_source") if meta else None, "line_count": len(text.splitlines()),
            "text": text}


async def edit_lyrics(who: auth.Who, args: dict) -> dict[str, Any]:
    song_id, title, _ = resolve_song(args.get("song_id"), args.get("query"))
    if not song_id:
        return {"error": NO_SONG}
    if args.get("reset"):
        lyrics_source.delete_user(song_id)
        lyrics_source.forget_online(song_id)
        ultrastar_source.forget(song_id)
        await worker.submit_lyrics(song_id)
        return {"status": "reset", "song_id": song_id, "title": title,
                "summary": f"Reset lyrics for '{title}' to the automatic ones; re-timing them."}
    old, new, full = args.get("old_snippet"), args.get("new_snippet"), args.get("text")
    if old is not None and new is not None:
        current = lyrics_source.current_text(song_id).replace("\r\n", "\n")
        old = str(old).replace("\r\n", "\n")
        if old not in current:
            return {"error": f"Could not find '{old}' in the lyrics of '{title}'.",
                    "current_lyrics_preview": "\n".join(current.splitlines()[:8])}
        final = current.replace(old, str(new).replace("\r\n", "\n"))
    elif full:
        final = full
    else:
        return {"error": "Give either 'text' (all lyrics) or 'old_snippet' and 'new_snippet'."}
    try:
        lines = lyrics_source.save_user(song_id, final)
    except ValueError as exc:
        return {"error": str(exc)}
    await worker.submit_lyrics(song_id)
    return {"status": "updated", "song_id": song_id, "title": title, "line_count": lines,
            "summary": f"Updated the lyrics of '{title}' ({lines} lines); re-timing them."}
