"""Lyric TIMING: forced alignment of known text, else Whisper transcription.

Output lyrics.json: [{start, end, text, words: [{word, start, end}]}]; words keep leading
spaces so CJK and Latin text both join correctly. Text comes from services.lyrics_source
(pasted > online > none). Known text is aligned by services.mms_align, or by stable-ts
(repaired with LRC anchors by services.anchored_align) for scripts MMS can't read or when
MMS loses the voice. LRC timed past the end of the audio (another version) is aligned as
plain text. Glitches are cleaned up by services.word_timing before saving.
"""
import json
import logging
import re

import soundfile as sf

from config import (ALIGN_FAILURE_THRESHOLD, CONDITION_ON_PREVIOUS_TEXT, LYRICS_ALIGNER, LYRICS_FILE,
                    MAX_CHARS_PER_SEC, VOCALS_FILE, WHISPER_COMPUTE_TYPE, WHISPER_MODEL, free_vram)
from core import cache_manager
from services import anchored_align, lrclib, lyrics_source, mms_align, vocal_activity, word_timing

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
        badness = lambda segs: sum(list(vocal_activity.timing_quality(segs, regions).values())[:2])  # noqa: E731
        if not any(s["words"] for s in segments) or badness(repaired) < badness(segments):
            return repaired
        log.info("Kept the global alignment: it matches the vocals better than the repair")
    return segments if any(s["words"] for s in segments) else None


def _align_known(vocals: str, lines, regions):
    """MMS first (does not drift on repetitive or half-spoken songs), else stable-ts."""
    aligned = mms_align.align(vocals, lines) if LYRICS_ALIGNER == "mms" else None
    if aligned and not vocal_activity.timing_quality(_to_segments(aligned, drop_dense=False), regions)["poor"]:
        return aligned, "mms"
    if LYRICS_ALIGNER == "mms":
        log.info("MMS could not align these lyrics%s: using stable-ts", " well" if aligned else "")
    return _run_with_model(_align, vocals, lines, regions), "stable-ts"


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
    duration = sf.info(str(vocals)).duration

    # Pasted lyrics win; otherwise search online (network first, GPU stays free)
    raw, origin = lyrics_source.load_user(song_id), "user"
    if not raw:
        raw, origin = lyrics_source.online_for(song_id, title, channel, duration), "synced"
    lines = lyrics_source.parse_lines(raw) if raw else []
    if lyrics_source.timed(lines) and not lrclib.fits(raw, duration):
        log.info("LRC of %s outlasts the audio (%.0f s): another version, timestamps ignored", song_id, duration)
        lines = [(None, text) for _, text in lines]
    aligned, aligner = _align_known(str(vocals), lines, regions) if lines else (None, None)
    segments = _to_segments(aligned, drop_dense=False) if aligned else []
    timing = vocal_activity.timing_quality(segments, regions)
    # Plain online text that would not line up: timing beats words for karaoke -> transcribe.
    # The guest's own text is kept (flagged in the library) — they chose it on purpose.
    if not segments or (timing["poor"] and origin == "synced" and not lyrics_source.timed(lines)):
        origin, aligner = "transcribed", "whisper"
        segments = _to_segments(_run_with_model(_transcribe, str(vocals)), drop_dense=True, regions=regions)
        timing = vocal_activity.timing_quality(segments, regions)
    segments = word_timing.polish(segments, duration, regions)  # after QA: timing reports the raw alignment
    missing = vocal_activity.unmatched(vocal_map["loud"], segments)

    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(segments, ensure_ascii=False), encoding="utf-8")
    tmp.replace(target)  # atomic swap: the TV never reads a half-written file

    cache_manager.update_meta(song_id, lyrics_source=origin, aligner=aligner, lyric_lines=len(segments), timing=timing,
                              unmatched_vocals=missing, unmatched_seconds=round(sum(e - s for s, e in missing), 1))
    log.info("Lyrics for %s: %d lines (%s, %s), timing %s, %d sung parts without lyrics",
             song_id, len(segments), origin, aligner, timing, len(missing))
    return {"source": origin, "lines": len(segments), "timing": timing}
