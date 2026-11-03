"""5 GB LRU song cache: per-song folders, metadata (meta.json) and eviction (order: core/eviction).

meta.json reads are served from memory while the file is unchanged and folders are sized in
one scandir pass (core/cache_files.py), so listing the library doesn't re-read the disk.
Crash repair at startup: core/cache_heal.py. Host tools (stats, trim, clear): core/cache_admin.py.
"""
import logging
import shutil
import threading
import time
from pathlib import Path
from typing import Iterable

from config import (
    CACHE_DIR,
    CACHE_HEADROOM_BYTES,
    INSTRUMENTAL_FILE,
    LYRICS_FILE,
    META_FILE,
    VOCALS_FILE,
)
from core import cache_files, eviction, settings

log = logging.getLogger(__name__)
_lock = threading.RLock()

READY_FILES = (VOCALS_FILE, INSTRUMENTAL_FILE, LYRICS_FILE)


def song_dir(song_id: str) -> Path:
    return CACHE_DIR / song_id


def song_file(song_id: str, name: str) -> Path:
    return song_dir(song_id) / name


# ── Metadata ─────────────────────────────────────────────────────────────────
def read_meta(song_id: str) -> dict:
    """The song's meta.json ({} when missing or corrupt); a private copy, safe to change."""
    return cache_files.read_json(song_file(song_id, META_FILE)) or {}


def write_meta(song_id: str, data: dict) -> None:
    """Atomic write (temp file + os.replace) so readers never see half a file."""
    with _lock:
        song_dir(song_id).mkdir(parents=True, exist_ok=True)
        cache_files.write_json(song_file(song_id, META_FILE), data, indent=2)


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
        now = time.time()
        update_meta(song_id, last_accessed=now, played_at=now)  # played: no longer a warm-up guess


def is_ready(song_id: str) -> bool:
    if read_meta(song_id).get("status") != "ready":
        return False
    return all(song_file(song_id, f).is_file() for f in READY_FILES)


def _entry(folder: Path) -> dict:
    size, names = cache_files.scan(folder)
    meta = read_meta(folder.name)
    ready = meta.get("status") == "ready" and all(f in names for f in READY_FILES)
    return {**meta, "id": folder.name, "ready": ready, "size": size}


def list_songs() -> list[dict]:
    """Every cached song folder (ready or still processing), most recently used first."""
    songs = [_entry(d) for d in song_dirs()]
    return sorted(songs, key=lambda m: m.get("last_accessed", 0), reverse=True)


# ── Size accounting & eviction ───────────────────────────────────────────────
def song_dirs() -> list[Path]:
    return [d for d in CACHE_DIR.iterdir() if d.is_dir()]


def folder_size(path: Path) -> int:
    return cache_files.scan(path)[0]


def total_size() -> int:
    return sum(folder_size(d) for d in song_dirs())


def song_ids() -> set[str]:
    return {d.name for d in song_dirs()}


def _meta_of(path: Path) -> dict:
    meta = read_meta(path.name)
    return {**meta, "id": path.name, "last_accessed": meta.get("last_accessed") or path.stat().st_mtime}


def evict(song_id: str) -> None:
    with _lock:
        shutil.rmtree(song_dir(song_id), ignore_errors=True)
        cache_files.forget(song_dir(song_id))
        log.info("Evicted %s from cache", song_id)


def ensure_space(protect: Iterable[str] = (), headroom: int = CACHE_HEADROOM_BYTES) -> list[str]:
    """Evict songs until cache + headroom fits in the limit: unplayed warm-ups of an old
    rotation first, then least recently used.

    `protect` = ids that must survive (now playing / still queued / being processed).
    """
    protected = set(protect)
    evicted: list[str] = []
    with _lock:
        dirs = {d.name: d for d in song_dirs()}
        sizes = {d: folder_size(d) for d in dirs.values()}
        total = sum(sizes.values())
        for folder in (dirs[i] for i in eviction.order([_meta_of(d) for d in dirs.values()])):
            if total + headroom <= settings.get("cache_limit_gb") * 1024**3:
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

