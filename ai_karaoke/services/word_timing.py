"""Final clean-up of word timings before they reach the screen and the singing game.

Forced alignment leaves a few typical glitches that look broken on stage:
  - zero-length words (often a line's first word): they flash instead of filling;
  - a line's last word stranded seconds later, right before the next line, so the line
    hangs through an instrumental break (or a first word stranded long before the rest);
  - words timed after the end of the audio (lyrics for a longer version of the song);
  - a section's last word stretched across the following break (bleed in the vocal stem);
  - words that end while the singer still holds the note (hold_notes, run once the melody exists).
Only timings change here, never the text. The shortest word ("min_word") and the longest
held word ("hold_max") come from the Settings page.
"""
from core import settings

_min_word = lambda: settings.get("min_word")  # noqa: E731
_hold_max = lambda: settings.get("hold_max")  # noqa: E731
STRAY_GAP = 2.0     # an edge word this far from the rest of its line is misplaced
STRAY_MAX = 1.0     # duration given to a moved word at most (s), without a vocal map
HOLD_SEMITONES = 2.0   # a held note may drift (vibrato, slides) this far before it counts as a new one
HOLD_GAP_FRAMES = 4    # unvoiced pitch frames (80 ms) that don't end a held note
PHRASE_PAD = 0.3       # a word may end this far past the vocal phrase it starts in


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _held_until(start: float, regions) -> float | None:
    """End of the vocal phrase sung at `start` (the singer holds the line's last note)."""
    return next((e for s, e in regions if s - 0.2 <= start <= e), None)


def _reattach_edges(words: list[dict], prev_end: float | None, next_start: float | None, regions) -> None:
    """Words after a long gap inside a line are stranded when crammed against the next line, or
    when the gap is very long (aligners park them in bleed during a break); a lone late word with
    room around it may really be sung late. A stranded tail follows the rest of its line."""
    if len(words) < 2:
        return
    # Guard against any single word excessively stretched across a non-vocal gap
    if regions:
        for word in words:
            if word["end"] - word["start"] > STRAY_MAX:
                held = _held_until(word["start"], regions)
                if held is not None and word["end"] > held + PHRASE_PAD:
                    word["end"] = max(held + PHRASE_PAD, word["start"] + _min_word())
                elif held is None:
                    next_s = next((s for s, e in regions if s > word["start"]), None)
                    cap = word["start"] + STRAY_MAX
                    if next_s is not None and next_s > word["start"]:
                        cap = min(cap, max(word["start"] + _min_word(), next_s - 0.05))
                    word["end"] = max(cap, word["start"] + _min_word())
    for k in range(1, len(words)):
        gap = words[k]["start"] - words[k - 1]["end"]
        crammed = next_start is not None and next_start - words[-1]["end"] < 0.3
        if gap > STRAY_GAP and (crammed or gap > 2 * STRAY_GAP):
            # Don't pull real singing backwards into silence/bleed if words[k] is on vocals and in a different phrase
            if regions and _held_until(words[k]["start"], regions) is not None and _held_until(words[k]["start"], regions) != _held_until(words[k - 1]["start"], regions):
                continue
            # The word before the gap usually swallowed the tail's real time: share it out by length
            moved = words[k - 1:]
            start = moved[0]["start"]
            end = max(moved[0]["end"], start + 0.3 * len(moved))
            weights = [len(w["word"].strip()) + 1 for w in moved]
            t = start
            for word, weight in zip(moved, weights):
                word["start"], t = t, t + (end - start) * weight / sum(weights)
                word["end"] = t - 0.02
            break
    first, after = words[0], words[1]
    if after["start"] - first["end"] > STRAY_GAP and prev_end is not None and first["start"] - prev_end < 0.3:
        span = _clamp(first["end"] - first["start"], 0.3, STRAY_MAX)
        first["end"] = after["start"] - 0.05
        first["start"] = first["end"] - span


def _cap_to_phrase(words: list[dict], regions) -> None:
    """A word ends with the vocal phrase it starts in: aligners hand the sound in a following
    instrumental break (bleed in the vocal stem) to the last word before it."""
    for word in words:
        held = _held_until(word["start"], regions)
        if held is not None:
            if word["end"] > held + PHRASE_PAD:
                word["end"] = max(held + PHRASE_PAD, word["start"] + _min_word())
        elif regions and word["end"] - word["start"] > STRAY_MAX:
            next_start = next((s for s, e in regions if s > word["start"]), None)
            limit = word["start"] + STRAY_MAX
            if next_start is not None and next_start > word["start"]:
                limit = min(limit, max(word["start"] + _min_word(), next_start - 0.05))
            word["end"] = max(limit, word["start"] + _min_word())


def _lengthen_short(words: list[dict]) -> None:
    """Give too-short words the minimum duration: from free time before them, then after, then from the next word."""
    for i, word in enumerate(words):
        need = _min_word() - (word["end"] - word["start"])
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
        spare = (nxt["end"] - nxt["start"]) - _min_word()
        if need > 0 and spare > 0:  # share the next word's time
            shift = min(need, spare)
            word["end"] += shift
            nxt["start"] = max(nxt["start"], word["end"])


def hold_notes(segments: list[dict], pitch: list[float], hop: float) -> int:
    """Alignment ends a word soon after it starts, but singers hold the vowel: extend each word
    while the pitch track (melody.json, MIDI or 0) stays on the same note, never into the next
    word. Without this the line on screen switches while its last word is still being sung.
    Returns the number of words extended (in place)."""
    words = [w for seg in segments for w in seg["words"]]
    extended = 0
    for i, word in enumerate(words):
        limit = min(words[i + 1]["start"] - 0.05 if i + 1 < len(words) else word["end"] + _hold_max(),
                    word["end"] + _hold_max())
        frame, gap = int(word["end"] / hop), 0
        if not (0 <= frame < len(pitch)) or pitch[frame] <= 0:
            continue  # not singing a clear note at the word's end
        # The note the word itself ends on (running twice must not stretch into the next note)
        ref = pitch[frame - 1] if frame > 0 and pitch[frame - 1] > 0 else pitch[frame]
        while frame < len(pitch) and frame * hop < limit:
            if pitch[frame] > 0:
                if abs(pitch[frame] - ref) > HOLD_SEMITONES:
                    break  # a new note: probably the next syllable
                ref, gap = 0.8 * ref + 0.2 * pitch[frame], 0
            elif (gap := gap + 1) > HOLD_GAP_FRAMES:
                break
            frame += 1
        end = min((frame - gap) * hop, limit)
        if end - word["end"] >= 0.1:
            word["end"] = round(end, 3)
            extended += 1
    for seg in segments:
        if seg["words"]:
            seg["end"] = seg["words"][-1]["end"]
    return extended


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
        _cap_to_phrase(words, regions)  # first: a CTC word runs through silence up to the next word
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
