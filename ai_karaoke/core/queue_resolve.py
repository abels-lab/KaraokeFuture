"""Resolve a playlist item (text or {query, title, artist, song_id}) to a song: ready cache first,
then an online search (mixed into core/queue_manager.QueueManager).
"""
import asyncio
import logging

from core import cache_manager
from services import sources
from services.song_names import song_key

log = logging.getLogger(__name__)


class PlaylistResolver:
    def _find_cached_song(self, query: str) -> dict | None:
        """Find a cached song matching the query/artist-title if ready."""
        wanted = song_key(query)
        for s in cache_manager.list_songs():
            k = song_key(s.get("title", ""), s.get("channel", ""))
            if k == wanted and cache_manager.is_ready(s["id"]):
                return s
        return None

    async def _resolve_playlist_item(self, item: dict | str) -> dict:
        """Resolve a playlist item to {song_id, title, channel, duration, thumbnail, ready}."""
        from core.warmer import choose
        from services import search

        if isinstance(item, str):
            query = item.strip()
            item = {"query": query, "title": query, "artist": ""}
        else:
            query = item.get("query") or f"{item.get('artist', '')} - {item.get('title', '')}".strip(" -")
            if not query:
                query = item.get("title") or ""

        song_id = item.get("song_id")
        if song_id and cache_manager.is_ready(song_id):
            meta = cache_manager.read_meta(song_id)
            return {
                "song_id": song_id,
                "title": meta.get("title") or item.get("title", query),
                "channel": meta.get("channel") or item.get("artist", ""),
                "duration": meta.get("duration"),
                "thumbnail": meta.get("thumbnail") or sources.thumbnail(song_id),
                "ready": True,
            }

        # Check local cache first
        cached = self._find_cached_song(query)
        if cached:
            return {
                "song_id": cached["id"],
                "title": cached.get("title", query),
                "channel": cached.get("channel", ""),
                "duration": cached.get("duration"),
                "thumbnail": cached.get("thumbnail") or sources.thumbnail(cached["id"]),
                "ready": True,
            }

        # Search online
        try:
            results = await asyncio.to_thread(search.search, query)
        except Exception as e:
            log.warning("Playlist search failed for %r: %s", query, e)
            results = []

        best = choose(query, results) or (results[0] if results else None)
        if best:
            sid = best["id"]
            return {
                "song_id": sid,
                "title": best.get("title", query),
                "channel": best.get("channel", ""),
                "duration": best.get("duration"),
                "thumbnail": best.get("thumbnail") or sources.thumbnail(sid),
                "ready": cache_manager.is_ready(sid),
            }

        return {
            "song_id": "",
            "title": item.get("title", query),
            "channel": item.get("artist", ""),
            "duration": None,
            "thumbnail": None,
            "ready": False,
        }
