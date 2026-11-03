"""The look-and-queue tools everyone in the chat may use. They act as the person asking (`who`):
a guest's song is queued under their own login, exactly as /api/queue does it."""
import asyncio
from typing import Any

from fastapi import HTTPException

from core import auth, cache_manager, settings
from core.playlist_manager import playlist_manager
from core.queue_manager import queue
from services import search as smart_search
from services.agent import store


def party_status(who: auth.Who, args: dict) -> dict[str, Any]:
    snap = queue.snapshot()
    current = snap.get("now_playing")
    pick = ("uid", "song_id", "title", "singer")
    return {
        "you": {"name": who.name or "Host", "host": who.admin},
        "now_playing": {**{k: current.get(k) for k in pick}, "duration": current.get("duration"),
                        "yours": auth.owns(who, current)} if current else None,
        "queue_count": len(snap.get("queue", [])),
        "upcoming": [{**{k: e.get(k) for k in pick}, "index": i + 1, "yours": auth.owns(who, e)}
                     for i, e in enumerate(snap.get("queue", [])[:10])],
        "active_playlist": snap.get("active_playlist"),
        "look": {k: settings.get(k) for k in ("theme", "accent", "style_font", "style_title_effect",
                                              "style_background")},
    }


async def library_songs(who: auth.Who, args: dict) -> dict[str, Any]:
    limit = max(1, min(100, int(args.get("limit") or 30)))
    query = str(args.get("search") or "").lower().strip()
    songs = await asyncio.to_thread(cache_manager.list_songs)
    hits = [s for s in songs if not query or query in str(s.get("title", "")).lower()
            or query in str(s.get("channel", "")).lower()]
    return {"total_cached": len(songs), "matched_count": len(hits),
            "songs": [{"id": s.get("id"), "title": s.get("title", "Unknown"), "channel": s.get("channel", ""),
                       "ready": bool(s.get("ready"))} for s in hits[:limit]]}


async def search_and_queue(who: auth.Who, args: dict) -> dict[str, Any]:
    from core.queue_access import enqueue, singer_for   # the same rules as the queue API (name, owner, limits)
    query = str(args.get("query") or "").strip()
    if not query:
        return {"error": "Empty query"}
    try:
        singer, owner = singer_for(who, str(args.get("singer") or ("" if who.guest_id is not None else "Host")))
    except HTTPException as exc:
        return {"error": exc.detail}
    results, _ = await asyncio.to_thread(smart_search.run, query)
    if not results:
        return {"error": f"No songs found for '{query}'"}
    top = results[0]
    mode = args.get("mode") if args.get("mode") in ("party", "score", "battle") else None
    try:
        entry = await enqueue(top.get("id") or top.get("song_id"), top.get("title", "Unknown"),
                              top.get("channel", ""), top.get("duration", 0) or 0, singer, owner,
                              mode=mode, thumbnail=top.get("thumbnail"))
    except HTTPException as exc:
        return {"error": exc.detail}
    if queue.current is None and entry.get("status") == "ready":   # idle and already processed: start now
        await queue.next()
    playing = bool(queue.current and queue.current.get("uid") == entry["uid"])
    return {"status": "playing" if playing else "queued", "title": entry["title"], "singer": singer,
            "uid": entry["uid"], "ready": entry.get("status") == "ready", "now_playing": playing}


def list_playlists(who: auth.Who, args: dict) -> dict[str, Any]:
    active_id = queue.active_playlist.get("id") if queue.active_playlist else None
    return {"playlists": playlist_manager.list_playlists(active_playlist_id=active_id),
            "active_playlist": queue.active_playlist_snapshot()}


def get_playlist(who: auth.Who, args: dict) -> dict[str, Any]:
    pid = args.get("playlist_id")
    pl = playlist_manager.get_playlist(pid) if pid else None
    return pl or {"error": f"Playlist '{pid}' not found"}


def improvement_request(who: auth.Who, args: dict) -> dict[str, Any]:
    topic = str(args.get("topic") or "unspecified").strip()[:80]
    desc = str(args.get("description") or "").strip()[:1000]
    alt = str(args.get("safe_alternative") or "").strip()[:500]
    store.record_improvement("feature_request", f"{topic}: {desc[:100]}",
                             {"topic": topic, "description": desc, "safe_alternative": alt,
                              "asked_by": who.name or "Host"})
    return {"status": "recorded", "topic": topic, "note": "Saved in the wishlist for a future update."}
