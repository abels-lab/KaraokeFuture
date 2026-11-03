"""Playlist management: built-in weekly hits rotation and custom party playlists.

Playlists are stored in data/playlists/<id>.json. Built-in playlists (weekly_hits and top_hits)
are dynamically sourced from data/top_hits.json and core.warmer rotation.
Generating the built-ins: core/playlist_builtin.py; editing custom ones: core/playlist_edit.py.
"""
import json
import logging
import re
from pathlib import Path
from typing import Any

from config import PLAYLISTS_DIR
from core.playlist_builtin import BUILTIN_TOP, BUILTIN_WEEKLY, BuiltinPlaylists
from core.playlist_edit import PlaylistEditor
from core.playlist_songs import normalize_song, parse_song_text, slugify  # noqa: F401 (re-exported)

log = logging.getLogger(__name__)


class PlaylistManager(BuiltinPlaylists, PlaylistEditor):
    def __init__(self, directory: Path = PLAYLISTS_DIR) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)

    def _file_path(self, playlist_id: str) -> Path:
        safe_id = re.sub(r"[^a-zA-Z0-9_-]", "", playlist_id)
        return self.directory / f"{safe_id}.json"

    def list_playlists(self, active_playlist_id: str | None = None) -> list[dict[str, Any]]:
        """List all built-in and custom playlists."""
        res: list[dict[str, Any]] = []

        # 1. Built-in playlists
        weekly = self.get_weekly_hits()
        res.append({
            "id": weekly["id"],
            "name": weekly["name"],
            "description": weekly["description"],
            "count": weekly["count"],
            "is_built_in": True,
            "is_active": (active_playlist_id == weekly["id"]),
        })

        top = self.get_top_hits()
        res.append({
            "id": top["id"],
            "name": top["name"],
            "description": top["description"],
            "count": top["count"],
            "is_built_in": True,
            "is_active": (active_playlist_id == top["id"]),
        })

        # 2. Custom playlists on disk
        for file in sorted(self.directory.glob("*.json")):
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
                pid = data.get("id") or file.stem
                songs = data.get("songs") or []
                res.append({
                    "id": pid,
                    "name": data.get("name", pid),
                    "description": data.get("description", ""),
                    "count": len(songs),
                    "is_built_in": False,
                    "is_active": (active_playlist_id == pid),
                    "created_at": data.get("created_at"),
                    "updated_at": data.get("updated_at"),
                })
            except Exception as e:
                log.warning("Failed reading playlist %s: %s", file, e)

        return res

    def get_playlist(self, playlist_id: str) -> dict[str, Any] | None:
        """Get full playlist with songs."""
        if playlist_id == BUILTIN_WEEKLY:
            return self.get_weekly_hits()
        if playlist_id == BUILTIN_TOP:
            return self.get_top_hits()

        path = self._file_path(playlist_id)
        if not path.is_file():
            return None

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            data["id"] = data.get("id") or playlist_id
            data["is_built_in"] = False
            raw_songs = data.get("songs") or []
            data["songs"] = [normalize_song(s) for s in raw_songs]
            data["count"] = len(data["songs"])
            return data
        except Exception as e:
            log.warning("Failed loading playlist %s: %s", playlist_id, e)
            return None


playlist_manager = PlaylistManager()
