"""In-memory singer queue and per-entry status (event loop only, so no locks needed).

Entry: {uid, song_id, singer, title, channel, duration, thumbnail, source, status, error, media,
added, owner, guide, mode, partner}. owner = guest id of whoever queued it (None: queued by the
host); guide (0-100 %) / mode (party | score | battle) = the singer's choices, None = the control
panel's own; partner = {id, name} of a second battle singer. See core/queue_personal.py.
"""

import logging
import time
import uuid

from fastapi import WebSocket

from core import cache_manager
from core.hub import hub
from core.media import media_urls
from core.queue_autodj import AutoDJQueue
from core.queue_personal import PersonalQueue
from core.queue_playback import QueuePlayback
from core.queue_playlist import PlaylistQueue
from core.queue_resolve import PlaylistResolver
from core.queue_store import QueueStore
from services import sources

log = logging.getLogger(__name__)
PENDING = ("queued", "downloading", "separating", "aligning")


class QueueManager(QueueStore, QueuePlayback, PlaylistQueue, AutoDJQueue, PlaylistResolver, PersonalQueue):
    def __init__(self) -> None:
        self.entries: list[dict] = []
        self.current: dict | None = None
        self.played: list[dict] = []
        self.playback: dict = {"time": 0.0, "duration": 0.0, "paused": True, "updated_at": 0.0}
        self.active_playlist: dict | None = None
        self._user_stopped_playlist: bool = False
        self._dj_picking: bool = False   # a next() is choosing the Auto-DJ song (awaits the search)
        self._last_save: float = 0.0

    # ── Mutations ────────────────────────────────────────────────────────────
    async def add(self, song_id: str, title: str, channel: str, duration, singer: str,
                  thumbnail: str | None = None, owner: int | None = None, guide: int | None = None,
                  mode: str | None = None) -> dict:
        # Check if song is in active playlist; if so promote (remove from playlist queue)
        self.check_and_promote_from_playlist(song_id, title, channel)

        entry = {
            "uid": uuid.uuid4().hex[:12], "song_id": song_id, "singer": singer,
            "title": title, "channel": channel, "duration": duration,
            "thumbnail": thumbnail or sources.thumbnail(song_id) or cache_manager.read_meta(song_id).get("thumbnail"),
            "source": sources.source_of(song_id),
            "status": "queued", "error": None, "media": None, "added": time.time(),
            "owner": owner, "guide": guide, "mode": mode, "partner": None,
            "is_playlist": False,
        }
        if cache_manager.is_ready(song_id):
            entry.update(status="ready", media=media_urls(song_id))
        else:  # same song already in the pipeline -> mirror its progress
            twin = next((e for e in self.entries if e["song_id"] == song_id and e["status"] in PENDING), None)
            entry["status"] = twin["status"] if twin else "queued"
        self.entries.append(entry)
        log.info("%s queued %s", singer, title)
        await self._changed()
        return entry

    async def set_song_status(self, song_id: str, status: str, error: str | None = None) -> None:
        for entry in self.entries:
            if entry["song_id"] == song_id and entry["status"] != "ready":
                entry.update(status=status, error=error)
                if status == "ready":
                    entry["media"] = media_urls(song_id)
        if self.current and self.current["song_id"] == song_id and self.current["status"] != "ready":
            self.current.update(status=status, error=error)
            if status == "ready":
                self.current["media"] = media_urls(song_id)
        if status == "error":  # an Auto-DJ song that can't be made: drop it, the playlist moves on
            self.entries = [e for e in self.entries if not (e["song_id"] == song_id and e.get("is_playlist"))]
        if not self.current and status in ("ready", "error"):
            if status == "error" or any(e["status"] == "ready" for e in self.entries):
                await self.next()
                return
        await self._changed()

    async def reset_song(self, song_id: str) -> None:
        """Audio is being rebuilt: queued entries wait for it again."""
        for entry in self.entries:
            if entry["song_id"] == song_id:
                entry.update(status="queued", error=None, media=None)
        await self.broadcast_state()

    async def media_updated(self, song_id: str) -> None:
        """New lyrics/video for a song: refresh entries; the stage reloads them mid-song."""
        for entry in self._everyone():
            if entry["song_id"] == song_id and entry["media"]:
                entry["media"] = media_urls(song_id)
        await hub.broadcast({"type": "media", "song_id": song_id})
        await self.broadcast_state()

    async def remove(self, uid: str) -> bool:
        if self.current and self.current["uid"] == uid:
            await self.next()
            return True
        if entry := self.find(uid):
            self.entries.remove(entry)
            await self.broadcast_state()
            return True
        if played_entry := self.find_played(uid):
            self.played.remove(played_entry)
            await self.broadcast_state()
            return True
        return False

    async def move(self, uid: str, offset: int) -> bool:
        if not (entry := self.find(uid)):
            return False
        index = self.entries.index(entry)
        target = max(0, min(len(self.entries) - 1, index + offset))
        self.entries.insert(target, self.entries.pop(index))
        await self.broadcast_state()
        return True

    async def move_to(self, uid: str, target_index: int) -> bool:
        if not (entry := self.find(uid)):
            return False
        curr_index = self.entries.index(entry)
        target = max(0, min(len(self.entries) - 1, target_index))
        if curr_index != target:
            self.entries.insert(target, self.entries.pop(curr_index))
            await self.broadcast_state()
        return True

    # ── Clients ──────────────────────────────────────────────────────────────
    async def client_joined(self, ws: WebSocket, role: str) -> None:
        await hub.send(ws, {"type": "state", "data": self.snapshot()})
        if role == "tv":
            await self._changed()

    async def broadcast_state(self) -> None:
        self._save()
        await hub.broadcast({"type": "state", "data": self.snapshot()})

    async def control(self, action: str, value: float | None = None) -> None:
        """Player commands for the TV: play | pause | restart | seek (s) | seek_by (±s)."""
        await hub.broadcast({"type": "control", "action": action, "value": value}, "tv")


queue = QueueManager()
