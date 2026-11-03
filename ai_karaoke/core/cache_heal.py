"""Startup repair of the song cache after a crash, a power cut or a killed download.

Run once at startup, before the queue is restored and before the worker starts (nothing is
being written then, so every temp file is a leftover):
- leftovers are deleted: our *.tmp files, yt-dlp's *.part / *.ytdl / original.webm, and
  audio-separator's long-named "..._(Vocals)_model.wav" outputs (hundreds of MB) when the
  process died between separating and renaming;
- JSON files that don't parse and empty WAVs are deleted, so their stage runs again
  (lyrics, melody, vocal map and pulse are all recomputed from the stems);
- a truncated download (original.wav without the "downloaded" mark in meta.json) is deleted,
  so a queued song doesn't get its half audio separated;
- a song with stems and lyrics but a lost/corrupt meta.json gets a minimal one back instead
  of being thrown away with minutes of GPU work.
Then `purge_incomplete` removes what still isn't ready and isn't queued.
"""
import json
import logging
from pathlib import Path
from typing import Iterable

from config import INSTRUMENTAL_FILE, META_FILE, ORIGINAL_FILE, VOCALS_FILE
from core import cache_manager

log = logging.getLogger(__name__)
TEMP_ENDINGS = (".tmp", ".part", ".ytdl")
STEM_MARKS = ("_(vocals)", "_(instrumental)", "_(other)", "_(drums)", "_(bass)")
DOWNLOADED = {"downloaded", "separated", "ready"}
WAV_HEADER = 44


def is_leftover(name: str) -> bool:
    low = name.lower()
    if low.endswith(TEMP_ENDINGS) or ".part-frag" in low or ".temp." in low:
        return True
    if low.startswith("original.") and low != ORIGINAL_FILE:   # yt-dlp's download before FFmpeg
        return True
    return low.endswith(".wav") and any(mark in low for mark in STEM_MARKS)


def _broken(path: Path) -> bool:
    if path.suffix == ".wav":
        return path.stat().st_size <= WAV_HEADER
    if path.suffix == ".json" and path.name != META_FILE:
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return True
    return False


def heal_folder(folder: Path, report: dict) -> None:
    for path in [p for p in folder.iterdir() if p.is_file()]:
        if is_leftover(path.name):
            report["leftovers"] += 1
        elif _broken(path):
            report["broken"] += 1
        else:
            continue
        report["freed"] += path.stat().st_size
        path.unlink(missing_ok=True)
    song_id, meta = folder.name, cache_manager.read_meta(folder.name)
    has = lambda name: (folder / name).is_file()  # noqa: E731
    stems = has(VOCALS_FILE) and has(INSTRUMENTAL_FILE)
    if not meta and all(has(f) for f in cache_manager.READY_FILES):
        stamp = (folder / VOCALS_FILE).stat().st_mtime
        cache_manager.write_meta(song_id, {"id": song_id, "status": "ready", "created": stamp,
                                           "last_accessed": stamp, "healed": True})
        report["meta_rebuilt"] += 1
    elif has(ORIGINAL_FILE) and not stems and meta.get("status") not in DOWNLOADED:
        report["freed"] += (folder / ORIGINAL_FILE).stat().st_size
        (folder / ORIGINAL_FILE).unlink(missing_ok=True)
        report["partial_downloads"] += 1


def heal() -> dict:
    """Repair every song folder; returns what was done (counts and bytes freed)."""
    report = {"leftovers": 0, "broken": 0, "partial_downloads": 0, "meta_rebuilt": 0, "freed": 0}
    for folder in cache_manager.song_dirs():
        try:
            heal_folder(folder, report)
        except OSError as exc:   # a locked file: try again next start
            log.warning("Could not repair cache folder %s: %s", folder.name, exc)
    if any(report[k] for k in ("leftovers", "broken", "partial_downloads", "meta_rebuilt")):
        log.info("Cache repaired: %s", report)
    return report


def purge_incomplete(protect: Iterable[str] = ()) -> list[str]:
    """Remove folders left half-processed by a crash (call once at startup, after `heal`),
    excluding any songs currently protected or queued."""
    protected = set(protect)
    removed = [d.name for d in cache_manager.song_dirs()
               if not cache_manager.is_ready(d.name) and d.name not in protected]
    for song_id in removed:
        cache_manager.evict(song_id)
    return removed
