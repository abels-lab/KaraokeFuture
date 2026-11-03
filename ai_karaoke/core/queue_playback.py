"""What plays now: next / previous / replay from history (mixed into core/queue_manager.QueueManager).

next() prefers the first ready waiting song, then the active playlist's Auto-DJ filler, and with
nothing at all starts the default playlist (settings autodj_auto_start / autodj_default_playlist).
"""
import time

from core import cache_manager, settings
from core.hub import hub
from core.media import media_urls


class QueuePlayback:
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
        elif not self.entries and not self.active_playlist and not getattr(self, "_user_stopped_playlist", False) and settings.get("autodj_auto_start", True):
            # User queue empty and no active playlist: auto-start default playlist
            default_pl = settings.get("autodj_default_playlist", "weekly_hits")
            self.current = None
            await self.start_playlist(default_pl)   # its _changed() may already have picked a song
            if self.active_playlist and not self.current and not self.entries:
                self.current = await self._pop_and_prepare_playlist_song()
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
