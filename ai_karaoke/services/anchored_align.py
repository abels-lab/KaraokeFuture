"""Repair word alignment with LRC line timestamps as anchors.

One forced alignment over a whole song is precise when it works, but on repetitive
lyrics ("Du / Du hast / Du hast mich") it loses its place and piles dozens of lines
into a few seconds. LRC line timestamps are usually right to ~0.5 s, so every line
whose aligned start strays from its anchor is re-aligned inside its own short window:
an error can no longer spread across the song.
"""
import logging

import numpy as np

log = logging.getLogger(__name__)

SR = 16000            # Whisper's sample rate
MAX_STRAY = 1.5       # aligned line may start this far from its anchor before it is redone
PAD_BEFORE = 0.6      # window around an anchored line
PAD_AFTER = 0.4
MAX_WINDOW = 15.0


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


def _align_line(model, audio, text: str, start: float, end: float, language):
    a = max(0.0, start - PAD_BEFORE)
    b = min(len(audio) / SR, end + PAD_AFTER, start + MAX_WINDOW)
    try:
        result = model.align(audio[int(a * SR): int(b * SR)], text, language=language, verbose=None)
    except Exception as exc:
        log.debug("Line align failed (%s): %s", exc, text)
        return None
    words = [{"word": w.word, "start": w.start + a, "end": w.end + a}
             for seg in (result.segments if result else []) for w in seg.words]
    return words if words and _zero_share(words) < 0.5 else None


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
    audio, fixed, spread = None, 0, 0
    out = []
    for i, (_, text) in enumerate(lines):
        start = anchors[i]
        end = anchors[i + 1] if i + 1 < len(anchors) else start + 8.0
        words = segments[i]["words"] if usable else []
        if words and abs(words[0]["start"] - start) <= MAX_STRAY and _zero_share(words) < 0.5:
            out.append({"words": words})
            continue
        if audio is None:
            audio = whisper.load_audio(vocals_path)
        words = _align_line(model, audio, text, start, end, language)
        if words is None:
            words, spread = _spread(text, start, end), spread + 1
        out.append({"words": words})
        fixed += 1
    log.info("Anchored alignment: shift %+.2f s, %d/%d lines re-aligned (%d spread evenly)",
             shift, fixed, len(lines), spread)
    return out
