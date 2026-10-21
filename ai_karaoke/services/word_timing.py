"""Final clean-up of word timings before they reach the screen and the singing game.

Forced alignment leaves a few typical glitches that look broken on stage:
  - zero-length words (often a line's first word): they flash instead of filling;
  - a line's last word stranded seconds later, right before the next line, so the line
    hangs through an instrumental break (or a first word stranded long before the rest);
  - words timed after the end of the audio (lyrics for a longer version of the song).
Only timings change here, never the text.
"""
MIN_WORD = 0.15     # shortest word duration shown (s)
STRAY_GAP = 2.0     # an edge word this far from the rest of its line is misplaced
STRAY_MAX = 1.0     # duration given to a moved word at most (s), without a vocal map
HOLD_MAX = 4.0      # ... with one: held to the end of the sung phrase, at most this long


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _held_until(start: float, regions) -> float | None:
    """End of the vocal phrase sung at `start` (the singer holds the line's last note)."""
    return next((e for s, e in regions if s - 0.2 <= start <= e), None)


def _reattach_edges(words: list[dict], prev_end: float | None, next_start: float | None, regions) -> None:
    """Only a word crammed against the neighbouring line is stranded; a lone late word with
    room around it may really be sung late."""
    if len(words) < 2:
        return
    last, before = words[-1], words[-2]
    if last["start"] - before["end"] > STRAY_GAP and next_start is not None and next_start - last["end"] < 0.3:
        start = before["end"] + 0.05
        held = _held_until(start, regions)
        span = _clamp((held or 0) - start, 0.3, HOLD_MAX) if held else _clamp(last["end"] - last["start"], 0.3, STRAY_MAX)
        last["start"], last["end"] = start, start + span
    first, after = words[0], words[1]
    if after["start"] - first["end"] > STRAY_GAP and prev_end is not None and first["start"] - prev_end < 0.3:
        span = _clamp(first["end"] - first["start"], 0.3, STRAY_MAX)
        first["end"] = after["start"] - 0.05
        first["start"] = first["end"] - span


def _lengthen_short(words: list[dict]) -> None:
    """Give too-short words MIN_WORD: from free time before them, then after, then from the next word."""
    for i, word in enumerate(words):
        need = MIN_WORD - (word["end"] - word["start"])
        if need <= 0:
            continue
        prev_end = words[i - 1]["end"] if i else max(0.0, word["start"] - 1.0)
        take = min(need, max(0.0, word["start"] - prev_end))
        word["start"] -= take
        need -= take
        if need <= 0:
            continue
        nxt = words[i + 1] if i + 1 < len(words) else None
        if nxt is None:
            word["end"] += need
            continue
        take = min(need, max(0.0, nxt["start"] - word["end"]))
        word["end"] += take
        need -= take
        spare = (nxt["end"] - nxt["start"]) - MIN_WORD
        if need > 0 and spare > 0:  # share the next word's time
            shift = min(need, spare)
            word["end"] += shift
            nxt["start"] = max(nxt["start"], word["end"])


def polish(segments: list[dict], duration: float | None = None, regions=()) -> list[dict]:
    """segments: [{start, end, text, words}] (lyrics.json format); regions: vocal map phrases.
    Returns cleaned copies."""
    kept = [[dict(w) for w in seg["words"] if duration is None or w["start"] < duration - 0.05] for seg in segments]
    out = []
    for i, (seg, words) in enumerate(zip(segments, kept)):
        if not words:
            continue
        prev_end = next((ws[-1]["end"] for ws in reversed(kept[:i]) if ws), None)
        next_start = next((ws[0]["start"] for ws in kept[i + 1:] if ws), None)
        _reattach_edges(words, prev_end, next_start, regions)
        text = "".join(w["word"] for w in words).strip() if len(words) < len(seg["words"]) else seg["text"]
        out.append({**seg, "text": text, "words": words})
    flat = [w for seg in out for w in seg["words"]]  # across lines: free time between lines counts
    _lengthen_short(flat)
    for seg in out:
        for w in seg["words"]:
            w["start"], w["end"] = round(w["start"], 3), round(w["end"] if duration is None else min(w["end"], duration), 3)
        seg["start"], seg["end"] = seg["words"][0]["start"], seg["words"][-1]["end"]
    return out
