"""In-memory singer queue and per-entry status (event loop only, so no locks needed).

Entry: {uid, song_id, singer, title, channel, duration, thumbnail, source, status, error, media,
added, owner, guide, mode, partner}. owner = guest id of whoever queued it (None: queued by the
host); guide (0-100 %) / mode (party | score | battle) = the singer's choices, None = the control
panel's own; partner = {id, name} of a second battle singer. See core/queue_personal.py.
"""
import json
import logging
import os
import time
import uuid

from fastapi import WebSocket

from core import cache_manager
from core.hub import hub
from core.media import media_urls
from core.queue_personal import PersonalQueue
from services import sources

log = logging.getLogger(__name__)
PENDING = ("queued", "downloading", "separating", "aligning")


class QueueManager(PersonalQueue):
    def __init__(self) -> None:
        self.entries: list[dict] = []
        self.current: dict | None = None

    def _save(self) -> None:
        try:
            from config import QUEUE_FILE
            data = {"entries": self.entries, "current": self.current}
            tmp = QUEUE_FILE.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
            os.replace(tmp, QUEUE_FILE)
        except Exception as e:
            log.warning("Failed to save queue: %s", e)

    def restore(self) -> None:
        try:
            from config import QUEUE_FILE
            if QUEUE_FILE.is_file():
                with open(QUEUE_FILE, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self.entries = data.get("entries", [])
                self.current = data.get("current")
                for entry in self._everyone():
                    sid = entry.get("song_id")
                    if sid and cache_manager.is_ready(sid):
                        entry["status"] = "ready"
                        entry["media"] = media_urls(sid)
                log.info("Restored %d queued song(s) from %s", len(self.entries), QUEUE_FILE)
        except Exception as e:
            log.warning("Failed to restore queue: %s", e)

    # ── Queries ──────────────────────────────────────────────────────────────
    def snapshot(self) -> dict:
        return {"now_playing": self.current, "queue": self.entries,
                "tv_connected": hub.tv_connected(), "screens": hub.count("screen")}

    def _everyone(self) -> list[dict]:
        return self.entries + ([self.current] if self.current else [])

    def find(self, uid: str) -> dict | None:
        return next((e for e in self.entries if e["uid"] == uid), None)

    def find_any(self, uid: str) -> dict | None:  # waiting or playing now
        return next((e for e in self._everyone() if e["uid"] == uid), None)

    def has_song(self, song_id: str) -> bool:
        return song_id in self.protected_ids()

    def is_playing(self, song_id: str) -> bool:
        return bool(self.current and self.current["song_id"] == song_id)

    def protected_ids(self) -> set[str]:
        """Songs the cache must not evict: now playing + everything queued."""
        return {e["song_id"] for e in self._everyone()}

    # ── Mutations ────────────────────────────────────────────────────────────
    async def add(self, song_id: str, title: str, channel: str, duration, singer: str,
                  thumbnail: str | None = None, owner: int | None = None, guide: int | None = None,
                  mode: str | None = None) -> dict:
        entry = {
            "uid": uuid.uuid4().hex[:12], "song_id": song_id, "singer": singer,
            "title": title, "channel": channel, "duration": duration,
            "thumbnail": thumbnail or sources.thumbnail(song_id) or cache_manager.read_meta(song_id).get("thumbnail"),
            "source": sources.source_of(song_id),
            "status": "queued", "error": None, "media": None, "added": time.time(),
            "owner": owner, "guide": guide, "mode": mode, "partner": None,
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
        return entry is not None

    async def move(self, uid: str, offset: int) -> bool:
        if not (entry := self.find(uid)):
            return False
        index = self.entries.index(entry)
        target = max(0, min(len(self.entries) - 1, index + offset))
        self.entries.insert(target, self.entries.pop(index))
        await self.broadcast_state()
        return True

    async def next(self) -> dict | None:
        """Play the first ready entry (singers whose track is still processing keep their spot)."""
        ready = next((e for e in self.entries if e["status"] == "ready"), None)
        if ready:
            self.entries.remove(ready)
            cache_manager.touch(ready["song_id"])
        self.current = ready
        await self.broadcast_state()
        return ready

    async def finish(self, uid: str) -> None:
        if self.current and self.current["uid"] == uid:  # ignore stale/duplicate "ended"
            await self.next()

    async def _changed(self) -> None:
        if self.current is None and hub.tv_connected():  # auto-start when idle and a TV watches
            await self.next()
        else:
            await self.broadcast_state()

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
