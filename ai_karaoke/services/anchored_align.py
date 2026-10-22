"""Repair word alignment with LRC line timestamps as anchors.

One forced alignment over a whole song is precise when it works, but on repetitive
lyrics ("Du / Du hast / Du hast mich") it loses its place and piles dozens of lines
into a few seconds. LRC line timestamps are usually right to ~0.5 s, so every line
whose aligned start strays from its anchor is re-aligned inside its own short window:
an error can no longer spread across the song. A line squeezed into a fraction of the
singing in its slot (typical for half-spoken or quiet vocals) is redone too, and a line no
alignment can place gets its words laid over the voiced parts of its slot.
"""
import logging

import numpy as np

from core import settings

log = logging.getLogger(__name__)

SR = 16000            # Whisper's sample rate
PAD_BEFORE = 0.6      # window around an anchored line
PAD_AFTER = 0.4
MAX_WINDOW = 15.0
FRAME = 0.05          # loudness frames for the voice map
VOICE_DB = 20.0       # "voice present": within this many dB of the singer's loud parts
MAX_WORDS_PER_SEC = 6.0


def estimate_offset(anchors: list[float], segments: list[dict], regions) -> float:
    """Constant shift between LRC times and this audio (a music-video edit can have a
    longer intro than the album version).

    Best evidence: lines the global alignment got right agree on one shift, wrong ones
    scatter, so the most common difference wins. Fallback: match anchors to vocal onsets.
    """
    if len(segments) == len(anchors):
        diffs = np.array([s["words"][0]["start"] - a for s, a in zip(segments, anchors)
                          if s["words"] and _zero_share(s["words"]) < 0.5])
        if len(diffs) >= 3:
            values, counts = np.unique(np.round(diffs / 0.25) * 0.25, return_counts=True)
            mode = values[np.argmax(counts)]
            if counts.max() >= max(3, 0.15 * len(anchors)):
                return float(np.median(diffs[np.abs(diffs - mode) <= 0.5]))
    return _offset_from_onsets(anchors, regions)


def _offset_from_onsets(anchors: list[float], regions) -> float:
    onsets = np.array([s for s, _ in regions])
    if not len(onsets) or not anchors:
        return 0.0
    anchors_np = np.array(anchors)

    def score(shift: float) -> float:
        gaps = np.abs((anchors_np + shift)[:, None] - onsets[None, :]).min(axis=1)
        return float(np.exp(-(gaps / 0.5) ** 2).sum())

    shifts = np.arange(-30.0, 30.0, 0.05)
    # Tiny pull towards 0: in repetitive songs a shift of one bar can score almost as well
    scores = np.array([score(s) for s in shifts]) - 0.01 * np.abs(shifts)
    best = float(shifts[np.argmax(scores)])
    # LRC times typically sit ~0.3-0.5 s after the vocal onset (fine as is); only accept a
    # real edit offset when it clearly beats no shift at all
    return best if abs(best) > 1.0 and scores.max() > 1.3 * score(0.0) else 0.0


def _zero_share(words) -> float:
    return sum(w["end"] - w["start"] < 0.02 for w in words) / max(len(words), 1)


def _voice_frames(audio) -> np.ndarray:
    hop = int(SR * FRAME)
    frames = audio[: len(audio) // hop * hop].reshape(-1, hop)
    db = 20 * np.log10(np.sqrt((frames ** 2).mean(axis=1)) + 1e-9)
    return db > np.percentile(db, 95) - VOICE_DB


def _crammed(words, voice, start: float, end: float) -> bool:
    """Words squeezed far tighter than the singing in their slot: the alignment lost the voice."""
    span = max(words[-1]["end"] - words[0]["start"], 0.1)
    sung = voice[int(max(start, 0) / FRAME): int(end / FRAME)].sum() * FRAME
    return len(words) / span > MAX_WORDS_PER_SEC or (sung > 1.0 and span < 0.4 * sung)


def _align_line(model, audio, text: str, start: float, end: float, language, voice):
    a = max(0.0, start - PAD_BEFORE)
    b = min(len(audio) / SR, end + PAD_AFTER, start + MAX_WINDOW)
    try:
        result = model.align(audio[int(a * SR): int(b * SR)], text, language=language, verbose=None)
    except Exception as exc:
        log.debug("Line align failed (%s): %s", exc, text)
        return None
    words = [{"word": w.word, "start": w.start + a, "end": w.end + a}
             for seg in (result.segments if result else []) for w in seg.words]
    return words if words and _zero_share(words) < 0.5 and not _crammed(words, voice, start, end) else None


def _place(text: str, start: float, end: float, voice) -> list[dict]:
    """Last resort: lay the words over the voiced parts of the slot, longer words longer."""
    first, last = int(max(start - 0.3, 0) / FRAME), int(min(end, start + MAX_WINDOW) / FRAME)
    sung = np.flatnonzero(voice[first:last]) + first
    tokens = text.split()
    if len(sung) * FRAME < 0.3 or not tokens:
        return _spread(text, start, end)
    weights = np.cumsum([0] + [len(t) + 1 for t in tokens]) / (sum(len(t) + 1 for t in tokens))
    edges = np.minimum((weights * len(sung)).astype(int), len(sung) - 1)
    return [{"word": (" " if i else "") + tok, "start": float(sung[edges[i]] * FRAME),
             "end": float(sung[max(edges[i + 1] - 1, edges[i])] * FRAME + FRAME)} for i, tok in enumerate(tokens)]


def _spread(text: str, start: float, end: float) -> list[dict]:
    """Last resort: spread the words evenly over the line's slot so it still shows on time."""
    tokens = text.split()
    span = min(max(end - start, 0.5), 0.45 * len(tokens) + 1.0)
    step = span / max(len(tokens), 1)
    return [{"word": (" " if i else "") + tok, "start": start + i * step, "end": start + (i + 1) * step}
            for i, tok in enumerate(tokens)]


def repair(model, vocals_path: str, segments: list[dict], lines, regions, language) -> list[dict]:
    """segments: global alignment, one per line (may be empty). lines: [(anchor, text)].
    Returns one segment per line, keeping every line that already sits near its anchor."""
    import whisper  # openai-whisper: 16 kHz mono loader, already a stable-ts dependency

    shift = estimate_offset([t for t, _ in lines], segments, regions)
    anchors = [t + shift for t, _ in lines]
    usable = len(segments) == len(lines)
    audio = whisper.load_audio(vocals_path)
    voice = _voice_frames(audio)
    fixed, spread = 0, 0
    out = []
    for i, (_, text) in enumerate(lines):
        start = anchors[i]
        end = anchors[i + 1] if i + 1 < len(anchors) else start + 8.0
        words = segments[i]["words"] if usable else []
        if (words and abs(words[0]["start"] - start) <= settings.get("anchor_max_stray") and _zero_share(words) < 0.5
                and not _crammed(words, voice, start, end)):
            out.append({"words": words})
            continue
        words = _align_line(model, audio, text, start, end, language, voice)
        if words is None:
            words, spread = _place(text, start, end, voice), spread + 1
        out.append({"words": words})
        fixed += 1
    log.info("Anchored alignment: shift %+.2f s, %d/%d lines re-aligned (%d placed on the voice)",
             shift, fixed, len(lines), spread)
    return out
