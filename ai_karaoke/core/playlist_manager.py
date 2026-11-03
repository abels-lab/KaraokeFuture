"""Playlist management: built-in weekly hits rotation and custom party playlists.

Playlists are stored in data/playlists/<id>.json. Built-in playlists (weekly_hits and top_hits)
are dynamically sourced from data/top_hits.json and core.warmer rotation.
"""
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

from config import PLAYLISTS_DIR
from core import settings
from core.warmer import load_hits, pick

log = logging.getLogger(__name__)

BUILTIN_WEEKLY = "weekly_hits"
BUILTIN_TOP = "top_hits"


def parse_song_text(item: str) -> tuple[str, str]:
    """Parse 'Artist - Title' into (title, artist). Fallback to (item, '')."""
    if " - " in item:
        artist, title = item.split(" - ", 1)
        return title.strip(), artist.strip()
    return item.strip(), ""


def normalize_song(item: Any) -> dict[str, Any]:
    """Normalize a playlist song item into a standard dict: {query, title, artist, song_id}."""
    if isinstance(item, str):
        item_str = item.strip()
        title, artist = parse_song_text(item_str)
        return {
            "query": item_str,
            "title": title or item_str,
            "artist": artist,
            "song_id": None,
        }
    if isinstance(item, dict):
        q = item.get("query") or item.get("title") or ""
        t = item.get("title") or q
        a = item.get("artist") or item.get("channel") or ""
        if not a and " - " in q:
            t, a = parse_song_text(q)
        return {
            "query": q,
            "title": t,
            "artist": a,
            "song_id": item.get("song_id") or item.get("id"),
        }
    s = str(item).strip()
    return {"query": s, "title": s, "artist": "", "song_id": None}


def slugify(text: str) -> str:
    """Generate safe filesystem slug from playlist name."""
    clean = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower()).strip("_")
    return clean[:48] or "playlist"


class PlaylistManager:
    def __init__(self, directory: Path = PLAYLISTS_DIR) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)

    def _file_path(self, playlist_id: str) -> Path:
        safe_id = re.sub(r"[^a-zA-Z0-9_-]", "", playlist_id)
        return self.directory / f"{safe_id}.json"

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


playlist_manager = PlaylistManager()
