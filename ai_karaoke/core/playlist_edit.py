"""Create / update / delete custom playlists in data/playlists/<id>.json (mixed into
core/playlist_manager.PlaylistManager). Built-in playlists are read-only.
"""
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from core.playlist_builtin import BUILTIN_TOP, BUILTIN_WEEKLY
from core.playlist_songs import normalize_song, slugify

log = logging.getLogger(__name__)


class PlaylistEditor:
    def _file_path(self, playlist_id: str) -> Path:  # provided by PlaylistManager
        raise NotImplementedError

    def create_playlist(
        self,
        name: str,
        songs: list[Any],
        description: str = "",
        playlist_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a new custom playlist and persist to JSON."""
        name = name.strip()
        if not name:
            raise ValueError("Playlist name is required")

        pid = playlist_id or slugify(name)
        if pid in (BUILTIN_WEEKLY, BUILTIN_TOP):
            raise ValueError(f"'{pid}' is a reserved built-in playlist id")

        path = self._file_path(pid)
        if path.is_file():
            # If auto-generated collision, append timestamp
            if not playlist_id:
                pid = f"{pid}_{int(time.time())}"
                path = self._file_path(pid)
            else:
                raise ValueError(f"Playlist with id '{pid}' already exists")

        normalized = [normalize_song(s) for s in songs if s]
        now = time.time()
        record = {
            "id": pid,
            "name": name,
            "description": description.strip(),
            "songs": normalized,
            "count": len(normalized),
            "created_at": now,
            "updated_at": now,
        }

        self._save_file(path, record)
        log.info("Created custom playlist '%s' (%s) with %d songs", name, pid, len(normalized))
        return record

    def update_playlist(
        self,
        playlist_id: str,
        name: str | None = None,
        description: str | None = None,
        songs: list[Any] | None = None,
        action: str = "set",
    ) -> dict[str, Any]:
        """Update an existing custom playlist."""
        if playlist_id in (BUILTIN_WEEKLY, BUILTIN_TOP):
            raise ValueError("Built-in playlists cannot be modified")

        path = self._file_path(playlist_id)
        if not path.is_file():
            raise ValueError(f"Playlist '{playlist_id}' not found")

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            raise ValueError(f"Failed reading playlist '{playlist_id}': {e}") from e

        if name is not None and name.strip():
            data["name"] = name.strip()
        if description is not None:
            data["description"] = description.strip()

        if songs is not None:
            new_norm = [normalize_song(s) for s in songs if s]
            if action in ("add_songs", "append"):
                existing = data.get("songs") or []
                existing_queries = {normalize_song(x)["query"].casefold() for x in existing}
                for s in new_norm:
                    if s["query"].casefold() not in existing_queries:
                        existing.append(s)
                data["songs"] = existing
            elif action == "remove_songs":
                remove_queries = {s["query"].casefold() for s in new_norm}
                existing = data.get("songs") or []
                data["songs"] = [x for x in existing if normalize_song(x)["query"].casefold() not in remove_queries]
            else:  # "set"
                data["songs"] = new_norm

        data["count"] = len(data.get("songs", []))
        data["updated_at"] = time.time()
        self._save_file(path, data)
        log.info("Updated playlist '%s' (%s), now has %d songs", data.get("name"), playlist_id, data["count"])
        return data

    def delete_playlist(self, playlist_id: str) -> bool:
        """Delete custom playlist from disk."""
        if playlist_id in (BUILTIN_WEEKLY, BUILTIN_TOP):
            raise ValueError("Built-in playlists cannot be deleted")

        path = self._file_path(playlist_id)
        if not path.is_file():
            return False

        try:
            path.unlink()
            log.info("Deleted custom playlist %s", playlist_id)
            return True
        except Exception as e:
            log.warning("Failed deleting playlist %s: %s", playlist_id, e)
            return False

    def _save_file(self, path: Path, data: dict[str, Any]) -> None:
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
