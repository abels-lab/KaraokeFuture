"""Lyric TIMING: forced alignment of known text, else Whisper transcription.

Output lyrics.json: [{start, end, text, words: [{word, start, end}]}]; words keep
Whisper's leading spaces so CJK and Latin text both join correctly.
Text comes from services.lyrics_source (pasted > online > none). Lines with LRC
timestamps are checked against them and repaired by services.anchored_align.
"""
import json
import logging
import re

from config import (ALIGN_FAILURE_THRESHOLD, CONDITION_ON_PREVIOUS_TEXT, LYRICS_FILE,
                    MAX_CHARS_PER_SEC, VOCALS_FILE, WHISPER_COMPUTE_TYPE, WHISPER_MODEL, free_vram)
from core import cache_manager
from services import anchored_align, lyrics_source, vocal_activity

log = logging.getLogger(__name__)

# Phrases Whisper invents over music/silence (learned from subtitled videos), not sung lyrics
_HALLUCINATIONS = re.compile(r"^(thank you( for watching)?|thanks for watching|please subscribe|you|"
                             r"продолжение следует|спасибо за просмотр|субтитры .*|редактор субтитров .*)[.!…\s]*$",
                             re.IGNORECASE)


def _run_with_model(step, *args):
    """Load the Whisper model, run one step, then release it (strict 6 GB VRAM)."""
    import torch  # import first: puts torch's cuDNN/cuBLAS DLLs on the search path
    import stable_whisper

    model, on_gpu = None, torch.cuda.is_available()
    try:
        model = stable_whisper.load_faster_whisper(
            WHISPER_MODEL, device="cuda" if on_gpu else "cpu",
            compute_type=WHISPER_COMPUTE_TYPE if on_gpu else "int8")
        return step(model, *args)
    finally:
        del model
        free_vram()


def _plain(result) -> list[dict]:
    """stable-ts result -> [{"words": [{word, start, end}]}], one entry per segment."""
    return [{"words": [{"word": w.word, "start": w.start, "end": w.end} for w in (seg.words or [])]}
            for seg in (result.segments if result else [])]


def _align(model, vocals: str, lines, regions):
    text = "\n".join(t for _, t in lines)
    language = lyrics_source.detect_language(text)
    try:  # original_split keeps one segment per lyric line
        result = model.align(vocals, text, language=language, original_split=True,
                             failure_threshold=ALIGN_FAILURE_THRESHOLD)
    except Exception as exc:
        log.warning("Global alignment failed: %s", exc)
        result = None
    segments = _plain(result)
    if lyrics_source.timed(lines):  # LRC anchors: redo every line that strayed from its timestamp
        repaired = anchored_align.repair(model, vocals, segments, lines, regions, language)
        # Safety net: keep whichever version lines up better with the actual singing
        badness = lambda segs: sum(list(timing_quality(segs, regions).values())[:2])  # noqa: E731
        if not any(s["words"] for s in segments) or badness(repaired) < badness(segments):
            return repaired
        log.info("Kept the global alignment: it matches the vocals better than the repair")
    return segments if any(s["words"] for s in segments) else None


def _transcribe(model, vocals: str):
    transcribe = getattr(model, "transcribe_stable", None) or model.transcribe
    result = transcribe(vocals, word_timestamps=True, vad=True,
                        condition_on_previous_text=CONDITION_ON_PREVIOUS_TEXT)
    return _plain(result.split_by_gap(0.8).split_by_length(max_chars=48))


def _to_segments(raw: list[dict], drop_dense: bool, regions=()) -> list[dict]:
    """drop_dense (transcriptions): skip lines sung impossibly fast, stock phrases, and
    lines over silence — all signs of a Whisper hallucination."""
    segments = []
    for seg in raw:
        words = [{"word": w["word"], "start": round(w["start"], 3), "end": round(w["end"], 3)}
                 for w in seg["words"] if w["word"].strip()]
        if not words:
            continue
        text = "".join(w["word"] for w in words).strip()
        start, end = words[0]["start"], words[-1]["end"]
        silent = bool(regions) and vocal_activity.vocal_fraction(start, end, regions) < 0.2
        if drop_dense and (len(text) > MAX_CHARS_PER_SEC * max(end - start, 0.1) or silent
                           or _HALLUCINATIONS.match(text)):
            log.info("Dropping implausible line (%.1fs%s): %s", end - start, ", silent" if silent else "", text)
            continue
        segments.append({"start": start, "end": end, "text": text, "words": words})
    return segments


def timing_quality(segments: list[dict], regions) -> dict:
    """Share of words with no duration / not on the vocals. High values = alignment got lost."""
    words = [w for s in segments for w in s["words"]]
    n = max(len(words), 1)
    zero = float(sum(w["end"] - w["start"] < 0.02 for w in words) / n)
    off = float(sum(vocal_activity.vocal_fraction(w["start"], max(w["end"], w["start"] + 0.05), regions) < 0.2
                    for w in words) / n) if regions else 0.0
    return {"zero_words": round(zero, 3), "off_vocals": round(off, 3), "poor": bool(zero > 0.2 or off > 0.25)}


def generate_lyrics(song_id: str, title: str, channel: str = "") -> dict:
    """Write lyrics.json for a separated song. Returns {source, lines, timing}."""
    target = cache_manager.song_file(song_id, LYRICS_FILE)
    vocals = cache_manager.song_file(song_id, VOCALS_FILE)
    if not vocals.is_file():
        raise FileNotFoundError(f"Missing {VOCALS_FILE} for {song_id}")
    try:  # CPU-only; needed before alignment for the anchor offset and quality checks
        vocal_map = vocal_activity.map_for(song_id)
    except Exception as exc:  # a missing map only costs the QA extras
        log.warning("Vocal map failed for %s: %s", song_id, exc)
        vocal_map = {"regions": [], "loud": []}
    regions = vocal_map["regions"]

    # Pasted lyrics win; otherwise search online (network first, GPU stays free)
    raw, origin = lyrics_source.load_user(song_id), "user"
    if not raw:
        raw, origin = lyrics_source.online_for(song_id, title, channel), "synced"
    lines = lyrics_source.parse_lines(raw) if raw else []
    aligned = _run_with_model(_align, str(vocals), lines, regions) if lines else None
    segments = _to_segments(aligned, drop_dense=False) if aligned else []
    timing = timing_quality(segments, regions)
    # Plain online text that would not line up: timing beats words for karaoke -> transcribe.
    # The guest's own text is kept (flagged in the library) — they chose it on purpose.
    if not segments or (timing["poor"] and origin == "synced" and not lyrics_source.timed(lines)):
        origin = "transcribed"
        segments = _to_segments(_run_with_model(_transcribe, str(vocals)), drop_dense=True, regions=regions)
        timing = timing_quality(segments, regions)
    missing = vocal_activity.unmatched(vocal_map["loud"], segments)

    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(segments, ensure_ascii=False), encoding="utf-8")
    tmp.replace(target)  # atomic swap: the TV never reads a half-written file

    cache_manager.update_meta(song_id, lyrics_source=origin, lyric_lines=len(segments), timing=timing,
                              unmatched_vocals=missing, unmatched_seconds=round(sum(e - s for s, e in missing), 1))
    log.info("Lyrics for %s: %d lines (%s), timing %s, %d sung parts without lyrics",
             song_id, len(segments), origin, timing, len(missing))
    return {"source": origin, "lines": len(segments), "timing": timing}
