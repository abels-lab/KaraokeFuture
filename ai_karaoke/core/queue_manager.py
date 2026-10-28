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
        self.played: list[dict] = []
        self.playback: dict = {"time": 0.0, "duration": 0.0, "paused": True, "updated_at": 0.0}
        self._last_save: float = 0.0

    def update_playback(self, uid: str, time_sec: float, duration: float, paused: bool) -> None:
        if self.current and self.current.get("uid") == uid:
            self.playback = {
                "uid": uid,
                "time": round(float(time_sec), 3),
                "duration": round(float(duration), 3),
                "paused": bool(paused),
                "updated_at": time.time(),
            }
            now = time.monotonic()
            if now - self._last_save >= 2.0 or self.playback.get("paused") != paused:
                self._last_save = now
                self._save()

    def _save(self) -> None:
        try:
            from config import QUEUE_FILE
            data = {
                "entries": self.entries,
                "current": self.current,
                "played": self.played,
                "playback": self.playback,
            }
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
                self.played = data.get("played", [])
                self.playback = data.get("playback", {"time": 0.0, "duration": 0.0, "paused": True, "updated_at": 0.0})
                if not self.current:
                    self.playback = {"time": 0.0, "duration": 0.0, "paused": True, "updated_at": 0.0}
                for entry in self._everyone():
                    sid = entry.get("song_id")
                    if sid and cache_manager.is_ready(sid):
                        entry["status"] = "ready"
                        entry["media"] = media_urls(sid)
                log.info("Restored %d queued song(s), %d played from %s", len(self.entries), len(self.played), QUEUE_FILE)
        except Exception as e:
            log.warning("Failed to restore queue: %s", e)

    # ── Queries ──────────────────────────────────────────────────────────────
    def snapshot(self) -> dict:
        np = dict(self.current) if self.current else None
        if np:
            np["playback"] = self.playback
        return {
            "now_playing": np,
            "queue": self.entries,
            "played": self.played,
            "tv_connected": hub.tv_connected(),
            "screens": hub.count("screen"),
            "playback": self.playback,
        }

    def _everyone(self) -> list[dict]:
        return self.entries + ([self.current] if self.current else []) + self.played

    def find(self, uid: str) -> dict | None:
        return next((e for e in self.entries if e["uid"] == uid), None)

    def find_played(self, uid: str) -> dict | None:
        return next((e for e in self.played if e["uid"] == uid), None)

    def find_any(self, uid: str) -> dict | None:  # waiting, playing now or played
        return next((e for e in self._everyone() if e["uid"] == uid), None)

    def has_song(self, song_id: str) -> bool:
        return song_id in self.protected_ids()

    def is_playing(self, song_id: str) -> bool:
        return bool(self.current and self.current["song_id"] == song_id)

    def active_ids(self) -> set[str]:
        """Songs queued or playing now."""
        return {e["song_id"] for e in self.entries + ([self.current] if self.current else []) if e.get("song_id")}

    def protected_ids(self) -> set[str]:
        """Songs the cache must not evict: now playing + everything queued + recent played."""
        return self.active_ids() | {e["song_id"] for e in self.played[-10:] if e.get("song_id")}

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

    async def next(self) -> dict | None:
        """Play the first ready entry (singers whose track is still processing keep their spot)."""
        if self.current:
            self.played.append(self.current)
        ready = next((e for e in self.entries if e["status"] == "ready"), None)
        if ready:
            self.entries.remove(ready)
            cache_manager.touch(ready["song_id"])
        self.current = ready
        self.playback = {
            "uid": ready["uid"] if ready else "",
            "time": 0.0,
            "duration": ready.get("duration", 0.0) if ready else 0.0,
            "paused": True,
            "updated_at": 0.0,
        }
        await self.broadcast_state()
        return ready

    async def previous(self) -> dict | None:
        """Play the previous song from history (e.g. if mistakenly skipped).
        The currently playing song is placed back at the beginning of the queue."""
        if not self.played:
            return None
        prev_song = self.played.pop()
        if self.current:
            self.entries.insert(0, self.current)
        sid = prev_song.get("song_id")
        if sid and cache_manager.is_ready(sid):
            prev_song["status"] = "ready"
            prev_song["media"] = media_urls(sid)
        self.current = prev_song
        self.playback = {
            "uid": prev_song["uid"] if prev_song else "",
            "time": 0.0,
            "duration": prev_song.get("duration", 0.0) if prev_song else 0.0,
            "paused": True,
            "updated_at": 0.0,
        }
        await self.broadcast_state()
        return prev_song

    async def play_played(self, uid: str) -> dict | None:
        """Host selects a specific song from played history to play right now."""
        entry = self.find_played(uid)
        if not entry:
            return None
        self.played.remove(entry)
        if self.current:
            self.entries.insert(0, self.current)
        sid = entry.get("song_id")
        if sid and cache_manager.is_ready(sid):
            entry["status"] = "ready"
            entry["media"] = media_urls(sid)
        self.current = entry
        self.playback = {
            "uid": entry["uid"] if entry else "",
            "time": 0.0,
            "duration": entry.get("duration", 0.0) if entry else 0.0,
            "paused": True,
            "updated_at": 0.0,
        }
        await self.broadcast_state()
        return entry

    async def requeue(self, uid: str) -> dict | None:
        """Move an already played song back into the waiting queue."""
        entry = self.find_played(uid)
        if not entry:
            return None
        self.played.remove(entry)
        sid = entry.get("song_id")
        if sid and cache_manager.is_ready(sid):
            entry["status"] = "ready"
            entry["media"] = media_urls(sid)
        entry["added"] = time.time()
        self.entries.append(entry)
        await self.broadcast_state()
        return entry

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
