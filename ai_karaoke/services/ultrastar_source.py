"""Ready-made UltraStar timing from USDB: lyrics, syllable timing, notes and duet parts.

fetch_for() runs right after the download (network only, alongside separation): it searches
USDB, checks the candidates and keeps the best as ultrastar.txt — an upload timed to our very
YouTube video first, else one whose artist/title match. apply() runs after separation: it
finds the file's offset to our audio from the vocal map, and only when the notes really line
up with the singing writes lyrics.json and melody.json, skipping alignment and pitch tracking.
A guest's pasted lyrics always win; any doubt keeps the normal pipeline.
"""
import json
import logging
import re

import numpy as np
import soundfile as sf

from config import LYRICS_FILE, MELODY_FILE, VOCALS_FILE
from core import cache_manager, settings
from services import lyrics_source, melody, ultrastar, ultrastar_sync, usdb, vocal_activity

log = logging.getLogger(__name__)

FILE = "ultrastar.txt"
MAX_CANDIDATES = 4      # txt downloads per song at most
MIN_COVERAGE = 0.75     # share of note time that must fall on detected singing
MIN_AGREEMENT = 0.35    # share of pitched note frames whose pitch the singer matches (any octave, ±1)...
MARGIN = 0.15           # ... and this far above chance (random notes already match ~25%)


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"\w+", lyrics_source.build_query(text).lower()))


def _similar(song: dict, query: str) -> float:
    want, got = _tokens(query), _tokens(f"{song['headers'].get('ARTIST', '')} {song['headers'].get('TITLE', '')}")
    return len(want & got) / max(len(want), 1)


def fetch_for(song_id: str) -> str | None:
    """Find, check and store an UltraStar file for a downloaded song: "video", "title" or None.
    Never raises: a song without a file is simply timed by the normal pipeline."""
    try:
        return _fetch(song_id)
    except Exception:
        log.exception("UltraStar lookup failed for %s", song_id)
        return None


def _fetch(song_id: str) -> str | None:
    path = cache_manager.song_file(song_id, FILE)
    meta = cache_manager.read_meta(song_id)
    if path.is_file() or not usdb.configured() or meta.get("usdb") is not None:
        return (meta.get("usdb") or {}).get("match")
    query = lyrics_source.build_query(meta.get("title", ""), meta.get("channel", ""))
    clean = lyrics_source.build_query(meta.get("title", ""))
    channel = re.sub(r"\s*(- topic|vevo|official)\s*$", "", meta.get("channel", ""), flags=re.IGNORECASE)
    artist, _, title = clean.partition(" - ") if " - " in clean else (channel, "", clean)
    found = usdb.search(artist.strip(), title.strip()) or usdb.search("", title.strip())
    best, why = None, None
    for usdb_id in found[:MAX_CANDIDATES]:
        try:
            song = ultrastar.parse(text := usdb.fetch_txt(usdb_id) or "")
        except (ValueError, KeyError):
            continue
        issues = ultrastar.problems(song, meta.get("duration"))
        if issues:
            log.info("USDB %d skipped for %s: %s", usdb_id, song_id, "; ".join(issues))
            continue
        if song_id in ultrastar.video_ids(song):
            best, why = (usdb_id, text), "video"
            break
        if best is None and _similar(song, query) >= 0.6:
            best, why = (usdb_id, text), "title"
    cache_manager.update_meta(song_id, usdb={"id": best[0], "match": why} if best else {})
    if best:
        path.write_text(best[1], encoding="utf-8")
        log.info("UltraStar file for %s: USDB %d (%s match)", song_id, best[0], why)
    return why


def forget(song_id: str) -> None:
    """Lyrics reset to automatic: drop the stored file so USDB is searched afresh."""
    cache_manager.song_file(song_id, FILE).unlink(missing_ok=True)
    cache_manager.update_meta(song_id, usdb=None)


def apply(song_id: str) -> bool:
    """Use the stored UltraStar file for this song if it lines up with our audio (never raises)."""
    try:
        return _apply(song_id)
    except Exception:
        log.exception("UltraStar timing failed for %s: aligning instead", song_id)
        return False


def _write(song_id: str, name: str, data) -> None:
    target = cache_manager.song_file(song_id, name)
    target.with_suffix(".tmp").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    target.with_suffix(".tmp").replace(target)  # atomic: the stage may be reading it


def _apply(song_id: str) -> bool:
    path = cache_manager.song_file(song_id, FILE)
    if not path.is_file() or lyrics_source.load_user(song_id):
        return False
    song = ultrastar.parse(path.read_text(encoding="utf-8"))
    duration = sf.info(str(cache_manager.song_file(song_id, VOCALS_FILE))).duration
    vocal_map = vocal_activity.map_for(song_id)
    exact = song_id in ultrastar.video_ids(song)
    offset, coverage = ultrastar_sync.find_offset(song, vocal_map["regions"], duration, exact)
    if coverage < MIN_COVERAGE or ultrastar.problems(song, duration):
        log.info("UltraStar file for %s not used: %.0f%% of its notes on singing (offset %+.2f s)",
                 song_id, coverage * 100, offset)
        return False
    f0, conf, _ = melody._pitch_track(cache_manager.song_file(song_id, VOCALS_FILE))  # ~10 s GPU
    midi = 69 + 12 * np.log2(np.maximum(f0, 1.0) / 440.0)
    voiced = (conf > settings.get("melody_voiced")) & (f0 > 0)
    tuned, agree, chance, pitched = ultrastar_sync.pitch_agreement(song, offset, midi, voiced)
    offset = tuned if pitched >= 0.2 else offset
    # Same song, same key: notes match the singer far above chance. Mostly unpitched (shouts, rap):
    # trust only a file timed to this very video.
    if (agree < max(MIN_AGREEMENT, chance + MARGIN)) if pitched >= 0.2 else not exact:
        log.info("UltraStar file for %s not used: pitch agrees %.0f%% (chance %.0f%%, %.0f%% pitched)",
                 song_id, agree * 100, chance * 100, pitched * 100)
        return False
    lines = [s for s in ultrastar.to_lyrics(song, offset) if s["start"] < duration]
    notes = ultrastar_sync.melody(cache_manager.song_file(song_id, VOCALS_FILE), song, offset, lines, duration)
    _write(song_id, LYRICS_FILE, lines)
    _write(song_id, MELODY_FILE, notes)
    missing = vocal_activity.unmatched(vocal_map["loud"], lines)
    span = [n["midi"] for n in notes["notes"]]
    cache_manager.update_meta(
        song_id, lyrics_source="ultrastar", aligner="ultrastar", lyric_lines=len(lines), usdb_pitch=agree,
        timing=vocal_activity.timing_quality(lines, vocal_map["regions"]), unmatched_vocals=missing,
        unmatched_seconds=round(sum(e - s for s, e in missing), 1), ultrastar={"offset": offset, "coverage": coverage},
        melody={"notes": len(span), "voiced": round(sum(p > 0 for p in notes["pitch"]) / max(len(notes["pitch"]), 1), 2),
                "range": [min(span), max(span)] if span else None})
    log.info("UltraStar timing for %s: %d lines, offset %+.2f s, %.0f%% of notes on singing%s", song_id,
             len(lines), offset, coverage * 100, " (duet)" if len(song["players"]) > 1 else "")
    return True
