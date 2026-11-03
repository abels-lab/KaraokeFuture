"""Queue persistence (data/queue.json) and read-only lookups (mixed into core/queue_manager.QueueManager)."""
import json
import logging
import os
import time

from core import cache_manager
from core.hub import hub
from core.media import media_urls

log = logging.getLogger(__name__)


class QueueStore:
    entries: list[dict]
    current: dict | None
    played: list[dict]
    playback: dict
    active_playlist: dict | None
    _last_save: float

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
                "active_playlist": self.active_playlist,
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
                self.active_playlist = data.get("active_playlist")
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
            "active_playlist": self.active_playlist_snapshot(),
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
        if not song_id:
            return False
        if self.current and self.current.get("song_id") == song_id:
            return True
        if any(e.get("song_id") == song_id for e in self.entries):
            return True
        if self.active_playlist:
            for item in self.active_playlist.get("queue", []):
                if isinstance(item, dict) and item.get("song_id") == song_id:
                    return True
            for item in self.active_playlist.get("played", []):
                if isinstance(item, dict) and item.get("song_id") == song_id:
                    return True
        return song_id in self.protected_ids()

    def is_playing(self, song_id: str) -> bool:
        return bool(self.current and self.current["song_id"] == song_id)

    def active_ids(self) -> set[str]:
        """Songs queued or playing now."""
        return {e["song_id"] for e in self.entries + ([self.current] if self.current else []) if e.get("song_id")}

    def protected_ids(self) -> set[str]:
        """Songs the cache must not evict: now playing + everything queued + recent played."""
        return self.active_ids() | {e["song_id"] for e in self.played[-10:] if e.get("song_id")}
