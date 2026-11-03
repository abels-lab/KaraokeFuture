"""The active playlist (Auto-DJ filler): start / stop, its snapshot, promoting its songs into the
singer queue (mixed into core/queue_manager.QueueManager). Picking the filler song: core/queue_autodj.py.
"""
import logging
import random
import time

from core import settings
from services.song_names import song_key

log = logging.getLogger(__name__)


class PlaylistQueue:
    def active_playlist_snapshot(self) -> dict | None:
        if not self.active_playlist:
            return None
        q = self.active_playlist.get("queue", [])
        p = self.active_playlist.get("played", [])
        is_playing = bool(self.current and self.current.get("is_playlist"))
        total = len(q) + len(p) + (1 if is_playing else 0)
        return {
            "id": self.active_playlist.get("id"),
            "name": self.active_playlist.get("name"),
            "description": self.active_playlist.get("description", ""),
            "queue": q[:30],
            "remaining": len(q),
            "played_count": len(p),
            "total": total,
            "loop": bool(self.active_playlist.get("loop", False)),
            "enabled": bool(self.active_playlist.get("enabled", True)),
        }

    # ── Playlist & Promotion ─────────────────────────────────────────────────
    def check_and_promote_from_playlist(self, song_id: str, title: str = "", channel: str = "") -> dict | None:
        """If enabled in settings and song is in active playlist queue, remove it from original position."""
        if not settings.get("playlist_promote_on_user_queue", True):
            return None
        if not self.active_playlist or not self.active_playlist.get("queue"):
            return None

        target_key = song_key(title, channel) if title else ""
        target_sid = song_id.strip() if song_id else ""

        queue_items = self.active_playlist["queue"]
        for i, item in enumerate(queue_items):
            item_sid = item.get("song_id") if isinstance(item, dict) else None
            item_title = item.get("title", "") if isinstance(item, dict) else str(item)
            item_artist = item.get("artist", "") if isinstance(item, dict) else ""
            item_query = item.get("query", item_title) if isinstance(item, dict) else str(item)

            matched = False
            if target_sid and item_sid and target_sid == item_sid:
                matched = True
            elif target_key and song_key(item_title, item_artist) == target_key:
                matched = True
            elif target_key and song_key(item_query) == target_key:
                matched = True

            if matched:
                promoted_item = queue_items.pop(i)
                log.info(
                    "Song '%s' removed from position %d in active playlist '%s' queue (promoted to user queue)",
                    item_title or target_sid, i, self.active_playlist.get("name")
                )
                return promoted_item
        return None

    async def start_playlist(self, playlist_id: str, shuffle: bool = False, loop: bool = False) -> dict:
        """Start playing a playlist with less priority in queue (Auto-DJ filler)."""
        from core.playlist_manager import playlist_manager
        pl = playlist_manager.get_playlist(playlist_id)
        if not pl:
            raise ValueError(f"Playlist '{playlist_id}' not found")
        songs = list(pl.get("songs") or [])
        if shuffle:
            random.shuffle(songs)
        self.active_playlist = {
            "id": pl["id"],
            "name": pl["name"],
            "description": pl.get("description", ""),
            "queue": songs,
            "played": [],
            "loop": bool(loop),
            "enabled": True,
            "started_at": time.time(),
        }
        self._prewarm_upcoming_playlist()
        log.info("Started playlist '%s' (%d songs, shuffle=%s, loop=%s)", pl["name"], len(songs), shuffle, loop)
        await self._changed()
        return self.active_playlist_snapshot() or {}

    async def stop_playlist(self) -> bool:
        """Stop active playlist background playback."""
        if not self.active_playlist:
            return False
        pl_name = self.active_playlist.get("name", "playlist")
        self.active_playlist = None
        self._user_stopped_playlist = True
        log.info("Stopped active playlist '%s'", pl_name)
        await self.broadcast_state()
        return True

    async def promote_playlist_song(self, query_or_index: str | int, singer: str = "Host", owner: int | None = None) -> dict | None:
        """Explicitly promote a song from the active playlist queue to the user queue."""
        if not self.active_playlist or not self.active_playlist.get("queue"):
            return None
        queue_items = self.active_playlist["queue"]
        target_item = None
        if isinstance(query_or_index, int) and 0 <= query_or_index < len(queue_items):
            target_item = queue_items[query_or_index]
        else:
            q_str = str(query_or_index).casefold().strip()
            for item in queue_items:
                if q_str in str(item.get("query", "")).casefold() or q_str in str(item.get("title", "")).casefold():
                    target_item = item
                    break
        if not target_item:
            return None

        resolved = await self._resolve_playlist_item(target_item)
        sid = resolved.get("song_id")
        if not sid:
            return None

        entry = await self.add(
            song_id=sid,
            title=resolved.get("title", "Unknown"),
            channel=resolved.get("channel", ""),
            duration=resolved.get("duration"),
            singer=singer,
            thumbnail=resolved.get("thumbnail"),
            owner=owner,
        )
        from core.worker import worker
        await worker.submit(sid)
        return entry
