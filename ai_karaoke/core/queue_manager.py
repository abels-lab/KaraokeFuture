"""In-memory singer queue and per-entry status (event loop only, so no locks needed).

Entry: {uid, song_id, singer, title, channel, duration, thumbnail, source, status, error, media,
added, owner, guide, mode, partner}. owner = guest id of whoever queued it (None: queued by the
host); guide (0-100 %) / mode (party | score | battle) = the singer's choices, None = the control
panel's own; partner = {id, name} of a second battle singer. See core/queue_personal.py.
"""
import asyncio
import json
import logging
import os
import random
import time
import uuid

from fastapi import WebSocket

from core import cache_manager, settings
from core.hub import hub
from core.media import media_urls
from core.queue_personal import PersonalQueue
from services import sources
from services.song_names import song_key

log = logging.getLogger(__name__)
PENDING = ("queued", "downloading", "separating", "aligning")


class QueueManager(PersonalQueue):
    def __init__(self) -> None:
        self.entries: list[dict] = []
        self.current: dict | None = None
        self.played: list[dict] = []
        self.playback: dict = {"time": 0.0, "duration": 0.0, "paused": True, "updated_at": 0.0}
        self.active_playlist: dict | None = None
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
        return song_id in self.protected_ids()

    def is_playing(self, song_id: str) -> bool:
        return bool(self.current and self.current["song_id"] == song_id)

    def active_ids(self) -> set[str]:
        """Songs queued or playing now."""
        return {e["song_id"] for e in self.entries + ([self.current] if self.current else []) if e.get("song_id")}

    def protected_ids(self) -> set[str]:
        """Songs the cache must not evict: now playing + everything queued + recent played."""
        return self.active_ids() | {e["song_id"] for e in self.played[-10:] if e.get("song_id")}

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
            if sid and not cache_manager.is_ready(sid):
                from core.worker import worker
                await worker.submit_warm(sid, self.active_playlist.get("id", "playlist"))
        except Exception as e:
            log.debug("Failed pre-warming playlist item: %s", e)

    async def _pop_and_prepare_playlist_song(self) -> dict | None:
        """Get next song from active playlist with less priority."""
        if not self.active_playlist or not self.active_playlist.get("queue"):
            if self.active_playlist and self.active_playlist.get("loop") and self.active_playlist.get("played"):
                self.active_playlist["queue"] = list(self.active_playlist["played"])
                self.active_playlist["played"] = []
            else:
                return None

        item = self.active_playlist["queue"].pop(0)
        self.active_playlist.setdefault("played", []).append(item)
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
        else:
            await worker.submit(sid)
        return entry

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
        """Play the first ready entry. If user queue has no ready songs and is empty,
        plays the next song from active playlist (less priority)."""
        if self.current:
            self.played.append(self.current)
        ready = next((e for e in self.entries if e["status"] == "ready"), None)
        if ready:
            self.entries.remove(ready)
            cache_manager.touch(ready["song_id"])
            self.current = ready
        elif not self.entries and self.active_playlist and self.active_playlist.get("enabled", True):
            # User queue is empty: Auto-DJ filler from active playlist
            pl_entry = await self._pop_and_prepare_playlist_song()
            self.current = pl_entry
        else:
            self.current = None

        self.playback = {
            "uid": self.current["uid"] if self.current else "",
            "time": 0.0,
            "duration": self.current.get("duration", 0.0) if self.current else 0.0,
            "paused": True,
            "updated_at": 0.0,
        }
        await self.broadcast_state()
        return self.current

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
