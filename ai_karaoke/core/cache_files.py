"""Low-level helpers for song folders: atomic writes, one-pass folder scans, cached JSON reads.

- `write_atomic`: temp file + os.replace, so a crash or a reader never sees half a file.
  The temp name is unique per thread and ends in ".tmp" (core/cache_heal.py removes leftovers).
- `scan`: size and file names of a folder in one os.scandir pass (on Windows the sizes come
  with the listing, no extra stat per file).
- `kept_file`: where a song's found lyrics live (outside the cache, never evicted).
- `read_json` / `write_json`: meta.json parsed once and kept in memory, checked against the
  file's mtime + size on every read, so lookups don't re-parse the whole cache. Writes from
  this process refresh the memory copy directly; callers always get their own copy.
"""
import copy
import json
import os
import shutil
import threading
from pathlib import Path

from config import LYRICS_STORE_DIR

_lock = threading.Lock()
_parsed: dict[str, tuple[tuple[int, int], dict]] = {}   # path -> (stamp, parsed content)


def write_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(f"{path.name}.{os.getpid()}-{threading.get_ident()}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def scan(folder: Path) -> tuple[int, set[str]]:
    """(total bytes including subfolders, names of the files directly inside)."""
    size, names = 0, set()
    try:
        entries = list(os.scandir(folder))
    except (FileNotFoundError, NotADirectoryError):
        return 0, names
    for entry in entries:
        try:
            if entry.is_file():
                size += entry.stat().st_size
                names.add(entry.name)
            elif entry.is_dir():
                size += scan(Path(entry.path))[0]
        except FileNotFoundError:   # removed while we looked
            continue
    return size, names


def _stamp(path: Path) -> tuple[int, int] | None:
    try:
        st = path.stat()
    except (FileNotFoundError, NotADirectoryError):
        return None
    return st.st_mtime_ns, st.st_size


def read_json(path: Path) -> dict | None:
    """Parsed JSON object, or None when the file is missing, unreadable or not an object."""
    key, stamp = str(path), _stamp(path)
    with _lock:
        hit = _parsed.get(key)
        if stamp is None:
            _parsed.pop(key, None)
            return None
        if hit and hit[0] == stamp:
            return copy.deepcopy(hit[1])
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    with _lock:
        _parsed[key] = (stamp, data)
    return copy.deepcopy(data)


def write_json(path: Path, data: dict, **dump_args) -> None:
    text = json.dumps(data, ensure_ascii=False, **dump_args)
    with _lock:
        write_atomic(path, text)
        if (stamp := _stamp(path)) is not None:
            _parsed[str(path)] = (stamp, json.loads(text))


def forget(folder: Path) -> None:
    """Drop memory copies of files in a folder that was deleted."""
    prefix = str(folder) + os.sep
    with _lock:
        for key in [k for k in _parsed if k.startswith(prefix)]:
            del _parsed[key]


def kept_file(song_id: str, name: str) -> Path:
    """Small lyric files kept outside the cache (config.KEPT_FILES): survive eviction."""
    folder = LYRICS_STORE_DIR / "found"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{song_id}.{name}"


def disk_free(path: Path) -> int:
    try:
        return shutil.disk_usage(path).free
    except OSError:
        return 0
