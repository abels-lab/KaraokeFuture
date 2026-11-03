"""Built-in playlists, generated on every read: weekly_hits (this week's core.warmer rotation) and
top_hits (all of data/top_hits.json). Mixed into core/playlist_manager.PlaylistManager.
"""
import time
from typing import Any

from core import settings
from core.playlist_songs import normalize_song
from core.warmer import load_hits, pick

BUILTIN_WEEKLY = "weekly_hits"
BUILTIN_TOP = "top_hits"


class BuiltinPlaylists:
    def get_weekly_hits(self) -> dict[str, Any]:
        """Built-in playlist: Current week's rotation from core.warmer."""
        hits = load_hits()
        warm_count = int(settings.get("warm_count", 20))
        rotation, picked = pick(hits, warm_count)
        songs = [normalize_song(h) for h in picked]
        return {
            "id": BUILTIN_WEEKLY,
            "name": f"Weekly Hits ({rotation})",
            "description": "Evergreen karaoke classics currently rotating in background warm-up",
            "songs": songs,
            "count": len(songs),
            "is_built_in": True,
            "rotation": rotation,
            "updated_at": time.time(),
        }

    def get_top_hits(self) -> dict[str, Any]:
        """Built-in playlist: All evergreen hits from data/top_hits.json."""
        hits = load_hits()
        songs = [normalize_song(h) for h in hits]
        return {
            "id": BUILTIN_TOP,
            "name": "Top Hits (All-Time)",
            "description": "Complete catalog of evergreen karaoke hits",
            "songs": songs,
            "count": len(songs),
            "is_built_in": True,
            "updated_at": time.time(),
        }
