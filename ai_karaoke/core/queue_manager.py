"""In-memory singer queue and per-entry status (event loop only, so no locks needed)."""
import logging
import time
import uuid

from fastapi import WebSocket

from config import INSTRUMENTAL_FILE, LYRICS_FILE, MELODY_FILE, VOCAL_MAP_FILE, VOCALS_FILE
from core import cache_manager
from core.hub import hub

log = logging.getLogger(__name__)

PENDING = ("queued", "downloading", "separating", "aligning")


def media_urls(song_id: str) -> dict:
    base, meta = f"/media/{song_id}", cache_manager.read_meta(song_id)
    has = lambda name: name and cache_manager.song_file(song_id, name).is_file()  # noqa: E731
    return {"instrumental": f"{base}/{INSTRUMENTAL_FILE}",
            "vocals": f"{base}/{VOCALS_FILE}", "lyrics": f"{base}/{LYRICS_FILE}",
            "lyrics_source": meta.get("lyrics_source"),
            "video": f"{base}/{meta['video']}" if has(meta.get("video")) else None,
            "vocal_map": f"{base}/{VOCAL_MAP_FILE}" if has(VOCAL_MAP_FILE) else None,
            "melody": f"{base}/{MELODY_FILE}" if has(MELODY_FILE) else None}


class QueueManager:
    def __init__(self) -> None:
        self.entries: list[dict] = []
        self.current: dict | None = None

    # ── Queries ──────────────────────────────────────────────────────────────
    def snapshot(self) -> dict:
        return {"now_playing": self.current, "queue": self.entries,
                "tv_connected": hub.tv_connected(), "screens": hub.count("screen")}

    def _everyone(self) -> list[dict]:
        return self.entries + ([self.current] if self.current else [])

    def find(self, uid: str) -> dict | None:
        return next((e for e in self.entries if e["uid"] == uid), None)

    def has_song(self, song_id: str) -> bool:
        return song_id in self.protected_ids()

    def is_playing(self, song_id: str) -> bool:
        return bool(self.current and self.current["song_id"] == song_id)

    def protected_ids(self) -> set[str]:
        """Songs the cache must not evict: now playing + everything queued."""
        return {e["song_id"] for e in self._everyone()}

    # ── Mutations ────────────────────────────────────────────────────────────
    async def add(self, song_id: str, title: str, channel: str, duration, singer: str) -> dict:
        entry = {
            "uid": uuid.uuid4().hex[:12], "song_id": song_id, "singer": singer,
            "title": title, "channel": channel, "duration": duration,
            "thumbnail": f"https://i.ytimg.com/vi/{song_id}/hqdefault.jpg",
            "status": "queued", "error": None, "media": None, "added": time.time(),
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
        await hub.broadcast({"type": "state", "data": self.snapshot()})

    async def control(self, action: str, value: float | None = None) -> None:
        """Player commands for the TV: play | pause | restart | seek (s) | seek_by (±s)."""
        await hub.broadcast({"type": "control", "action": action, "value": value}, "tv")


queue = QueueManager()
