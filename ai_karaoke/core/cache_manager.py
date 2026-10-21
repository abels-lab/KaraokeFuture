"""5 GB LRU song cache: per-song folders, metadata (meta.json) and eviction."""
import json
import logging
import os
import shutil
import threading
import time
from pathlib import Path
from typing import Iterable

from config import (
    CACHE_DIR,
    CACHE_HEADROOM_BYTES,
    CACHE_LIMIT_BYTES,
    INSTRUMENTAL_FILE,
    LYRICS_FILE,
    META_FILE,
    VOCALS_FILE,
)

log = logging.getLogger(__name__)
_lock = threading.RLock()

READY_FILES = (VOCALS_FILE, INSTRUMENTAL_FILE, LYRICS_FILE)


def song_dir(song_id: str) -> Path:
    return CACHE_DIR / song_id


def song_file(song_id: str, name: str) -> Path:
    return song_dir(song_id) / name


# ── Metadata ─────────────────────────────────────────────────────────────────
def read_meta(song_id: str) -> dict:
    try:
        with open(song_file(song_id, META_FILE), encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def write_meta(song_id: str, data: dict) -> None:
    """Atomic write (temp file + os.replace) so readers never see half a file."""
    with _lock:
        folder = song_dir(song_id)
        folder.mkdir(parents=True, exist_ok=True)
        tmp = folder / f"{META_FILE}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, folder / META_FILE)


def update_meta(song_id: str, **fields) -> dict:
    with _lock:
        meta = read_meta(song_id)
        meta.setdefault("id", song_id)
        meta.setdefault("created", time.time())
        meta.update(fields)
        meta.setdefault("last_accessed", time.time())
        write_meta(song_id, meta)
        return meta


def touch(song_id: str) -> None:
    """Mark a song as recently used (call when it starts playing)."""
    if song_dir(song_id).is_dir():
        update_meta(song_id, last_accessed=time.time())


def is_ready(song_id: str) -> bool:
    if read_meta(song_id).get("status") != "ready":
        return False
    return all(song_file(song_id, f).is_file() for f in READY_FILES)


def list_songs() -> list[dict]:
    """Every cached song folder (ready or still processing), most recently used first."""
    songs = [{**read_meta(d.name), "id": d.name, "ready": is_ready(d.name), "size": folder_size(d)}
             for d in _song_dirs()]
    return sorted(songs, key=lambda m: m.get("last_accessed", 0), reverse=True)


# ── Size accounting & eviction ───────────────────────────────────────────────
def _song_dirs() -> list[Path]:
    return [d for d in CACHE_DIR.iterdir() if d.is_dir()]


def folder_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def total_size() -> int:
    return sum(folder_size(d) for d in _song_dirs())


def _last_access(path: Path) -> float:
    meta = read_meta(path.name)
    return float(meta.get("last_accessed") or path.stat().st_mtime)


def evict(song_id: str) -> None:
    with _lock:
        shutil.rmtree(song_dir(song_id), ignore_errors=True)
        log.info("Evicted %s from cache", song_id)


def ensure_space(protect: Iterable[str] = (), headroom: int = CACHE_HEADROOM_BYTES) -> list[str]:
    """Evict least-recently-used songs until cache + headroom fits in 5 GB.

    `protect` = ids that must survive (now playing / still queued).
    """
    protected = set(protect)
    evicted: list[str] = []
    with _lock:
        dirs = _song_dirs()
        sizes = {d: folder_size(d) for d in dirs}
        total = sum(sizes.values())
        for folder in sorted(dirs, key=_last_access):
            if total + headroom <= CACHE_LIMIT_BYTES:
                break
            if folder.name in protected:
                continue
            evict(folder.name)
            # On Windows a file being streamed can't be removed; recount what's left.
            remaining = folder_size(folder) if folder.exists() else 0
            total -= sizes[folder] - remaining
            evicted.append(folder.name)
    if evicted:
        log.info("Cache now %.2f GB after evicting %d song(s)", total / 1024**3, len(evicted))
    return evicted


def purge_incomplete() -> list[str]:
    """Remove folders left half-processed by a crash (call once at startup)."""
    removed = [d.name for d in _song_dirs() if not is_ready(d.name)]
    for song_id in removed:
        evict(song_id)
    return removed
