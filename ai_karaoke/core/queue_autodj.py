"""Auto-DJ: turn the active playlist's next item into a queue entry and pre-warm the one after
(mixed into core/queue_manager.QueueManager). Item -> song resolution: core/queue_resolve.py.
"""
import asyncio
import logging
import time
import uuid

from core import cache_manager
from core.media import media_urls
from services import sources

log = logging.getLogger(__name__)


class AutoDJQueue:
    def _prewarm_upcoming_playlist(self) -> None:
        """Submit the next upcoming playlist song for background warming."""
        if not self.active_playlist or not self.active_playlist.get("queue"):
            return
        upcoming = self.active_playlist["queue"][0]
        asyncio.create_task(self._warm_item(upcoming))

    async def _warm_item(self, item: dict | str) -> None:
        try:
            resolved = await self._resolve_playlist_item(item)
            sid = resolved.get("song_id")
            if sid:
                if isinstance(item, dict):
                    item["song_id"] = sid
                if not cache_manager.is_ready(sid):
                    from core.worker import worker
                    await worker.submit_warm(sid, self.active_playlist.get("id", "playlist"))
        except Exception as e:
            log.debug("Failed pre-warming playlist item: %s", e)

    async def _pop_and_prepare_playlist_song(self) -> dict | None:
        """One Auto-DJ pick at a time: two next() calls at once must not each start a song."""
        if self._dj_picking:
            return None
        self._dj_picking = True
        try:
            return await self._pick_playlist_song()
        finally:
            self._dj_picking = False

    async def _pick_playlist_song(self) -> dict | None:
        """Get next song from active playlist with less priority."""
        if not self.active_playlist or not self.active_playlist.get("queue"):
            if self.active_playlist and self.active_playlist.get("loop") and self.active_playlist.get("played"):
                self.active_playlist["queue"] = list(self.active_playlist["played"])
                self.active_playlist["played"] = []
            else:
                return None

        item = self.active_playlist["queue"].pop(0)
        self.active_playlist.setdefault("played", []).append(item)
        self._user_stopped_playlist = False
        self._prewarm_upcoming_playlist()

        resolved = await self._resolve_playlist_item(item)
        sid = resolved.get("song_id")
        if not sid:
            log.warning("Could not resolve playlist song: %s", item)
            return None

        from core.worker import worker
        pl_name = self.active_playlist.get("name", "Playlist")
        entry = {
            "uid": uuid.uuid4().hex[:12],
            "song_id": sid,
            "singer": f"Auto-DJ ({pl_name})",
            "title": resolved.get("title") or "Unknown title",
            "channel": resolved.get("channel") or "",
            "duration": resolved.get("duration"),
            "thumbnail": resolved.get("thumbnail") or sources.thumbnail(sid),
            "source": sources.source_of(sid),
            "status": "ready" if cache_manager.is_ready(sid) else "queued",
            "error": None,
            "media": media_urls(sid) if cache_manager.is_ready(sid) else None,
            "added": time.time(),
            "owner": None,
            "guide": None,
            "mode": "party",
            "partner": None,
            "is_playlist": True,
            "playlist_id": self.active_playlist.get("id"),
        }
        if cache_manager.is_ready(sid):
            cache_manager.touch(sid)
            return entry
        # Not processed yet: wait in the queue like any song; set_song_status() starts it when ready
        self.entries.append(entry)
        await worker.submit(sid)
        return None
