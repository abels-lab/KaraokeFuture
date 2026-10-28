"""Where singing actually happens, from the loudness of the isolated vocals.wav (CPU only).

Two maps, because loudness tells silence from sound reliably but not singing from bleed:
  regions (lenient) -> label instrumental breaks, drop transcribed lines over silence
  loud    (strict)  -> flag sung parts the lyrics miss, without false alarms from bleed
Saved as vocals.json: {"regions": [[start, end], ...], "loud": [[start, end], ...]} in seconds.
"""
import json
import logging

import numpy as np
import soundfile as sf

from config import VOCAL_MAP_FILE, VOCALS_FILE
from core import cache_manager, settings

log = logging.getLogger(__name__)

FRAME = 0.05          # 50 ms loudness frames
GRID = 10             # timeline resolution for coverage maths (10 steps per second)
BRIDGE_GAP = 0.6      # breaths shorter than this don't split a vocal phrase
MIN_PHRASE = 0.3      # shorter blips are clicks or bleed, not singing


def _runs(mask: np.ndarray, step: float) -> list[list[float]]:
    edges = np.flatnonzero(np.diff(np.concatenate(([0], mask.astype(np.int8), [0]))))
    return [[float(s * step), float(e * step)] for s, e in zip(edges[::2], edges[1::2])]


def _phrases(mask: np.ndarray) -> list[list[float]]:
    merged: list[list[float]] = []
    for start, end in _runs(mask, FRAME):
        if merged and start - merged[-1][1] < BRIDGE_GAP:
            merged[-1][1] = end
        else:
            merged.append([start, end])
    return [[round(s, 2), round(e, 2)] for s, e in merged if e - s >= MIN_PHRASE]


def analyse(path) -> dict:
    data, sr = sf.read(str(path), dtype="float32", always_2d=True)
    mono = data.mean(axis=1)
    hop = int(sr * FRAME)
    frames = mono[: len(mono) // hop * hop].reshape(-1, hop)
    db = 20 * np.log10(np.sqrt((frames ** 2).mean(axis=1)) + 1e-9)
    peak = float(np.percentile(db, 95))
    return {"regions": _phrases(db > max(peak - settings.get("vocal_lenient_db"), -50.0)),
            "loud": _phrases(db > peak - settings.get("vocal_strict_db"))}


def map_for(song_id: str) -> dict:
    """Cached vocals.json, computed on first use."""
    target = cache_manager.song_file(song_id, VOCAL_MAP_FILE)
    try:
        cached = json.loads(target.read_text(encoding="utf-8"))
        if "loud" in cached:
            return cached
    except (FileNotFoundError, ValueError):
        pass
    vocal_map = analyse(cache_manager.song_file(song_id, VOCALS_FILE))
    target.write_text(json.dumps(vocal_map), encoding="utf-8")
    log.info("Vocal map for %s: %d phrases, %.0f s with vocals", song_id,
             len(vocal_map["regions"]), sum(e - s for s, e in vocal_map["regions"]))
    return vocal_map


def _mask(spans, length: int, before: float = 0.0, after: float = 0.0) -> np.ndarray:
    mask = np.zeros(length, dtype=bool)
    for start, end in spans:
        mask[max(0, int((start - before) * GRID)): max(0, int((end + after) * GRID))] = True
    return mask


def vocal_fraction(start: float, end: float, regions) -> float:
    """Share of [start, end] during which someone is actually singing."""
    sung = sum(max(0.0, min(end, e) - max(start, s)) for s, e in regions)
    return sung / max(end - start, 0.01)


def unmatched(loud, segments) -> list[list[float]]:
    """Clearly sung stretches that no lyric line covers — lines the lyrics are probably missing."""
    if not loud:
        return []
    length = int((loud[-1][1] + 2) * GRID)
    sung = _mask(loud, length)
    covered = _mask(((s["start"], s["end"]) for s in segments), length, before=0.3, after=settings.get("hold_pad"))
    merged: list[list[float]] = []
    for start, end in _runs(sung & ~covered, 1 / GRID):
        if merged and start - merged[-1][1] < BRIDGE_GAP:
            merged[-1][1] = end
        else:
            merged.append([start, end])
    return [[round(s, 1), round(e, 1)] for s, e in merged if e - s >= settings.get("min_unmatched")]


def first_vocal_onset(vocal_map: dict, start_time: float = 0.0, min_duration: float = 1.0) -> float:
    """First sustained vocal phrase onset from loud activity, stepped back slightly.

    Finds the first phrase in loud with duration >= min_duration, checks for a covering
    lenient region (or steps back ~1.5s) to include any quiet breath or pickup word
    preceding the loud singing, and clamps to at least start_time.
    """
    loud = vocal_map.get("loud", [])
    sustained = [p for p in loud if p[1] - p[0] >= min_duration and p[1] > start_time]
    if not sustained:
        return start_time
    loud_start = sustained[0][0]
    regions = vocal_map.get("regions", [])
    covering = next((r for r in regions if r[0] <= loud_start <= r[1]), None)
    if covering:
        onset = max(loud_start - 2.0, min(covering[0], loud_start - 1.0))
    else:
        onset = loud_start - 1.5
    return max(start_time, round(onset, 2))


def timing_quality(segments: list[dict], regions, loud=()) -> dict:
    """Share of words with no duration / not on the vocals. High values = alignment got lost."""
    words = [w for s in segments for w in s["words"]]
    n = max(len(words), 1)
    zero = float(sum(w["end"] - w["start"] < 0.02 for w in words) / n)
    vocal_regions = regions
    sustained = [p for p in loud if p[1] - p[0] >= 1.0] if loud else []
    if sustained:
        first_loud = sustained[0][0]
        # Ignore pre-intro lenient regions that have no loud singing
        vocal_regions = [r for r in regions if r[1] > first_loud or any(max(r[0], l[0]) < min(r[1], l[1]) for l in loud)]
    off = float(sum(vocal_fraction(w["start"], max(w["end"], w["start"] + 0.05), vocal_regions) < 0.2
                    for w in words) / n) if vocal_regions else 0.0
    poor = bool(zero > 0.2 or off > 0.25)
    if not poor and sustained and segments:
        first_loud = sustained[0][0]
        # Multiple lines placed before sustained singing without loud vocals indicates pre-intro bleed
        pre_bleed_lines = [s for s in segments if s["end"] <= first_loud and vocal_fraction(s["start"], s["end"], loud) < 0.1]
        if len(pre_bleed_lines) >= 2:
            poor = True
    return {"zero_words": round(zero, 3), "off_vocals": round(off, 3), "poor": poor}
