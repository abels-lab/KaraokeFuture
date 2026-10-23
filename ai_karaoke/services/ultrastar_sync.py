"""Line an UltraStar file up with our audio and build melody.json from its notes.

The file was timed to some upload of the song; ours may have a longer intro. The offset is
the shift that puts most of the file's note time onto singing in our vocal map.
"""
import numpy as np
import soundfile as sf

from services import ultrastar

GRID = 0.05             # seconds per step of the offset search
HOP = 0.02              # melody.json frame step (same as services.melody)


def _mask(spans, length: int, shift: float = 0.0) -> np.ndarray:
    mask = np.zeros(length, dtype=bool)
    for a, b in spans:
        mask[max(0, int((a + shift) / GRID)): max(0, int((b + shift) / GRID))] = True
    return mask


def find_offset(song: dict, regions, duration: float, exact: bool) -> tuple[float, float]:
    """(offset in s, share of note time on singing). exact: timed to this very video (±1.5 s)."""
    notes = [(ultrastar.seconds(song, s["beat"]), ultrastar.seconds(song, s["beat"] + s["length"]))
             for lines in song["players"].values() for line in lines for s in line]
    n = int(duration / GRID) + 1
    sung = _mask(regions, n)
    total = max(sum(b - a for a, b in notes) / GRID, 1.0)
    reach = int((1.5 if exact else 30.0) / GRID)
    best, best_score = 0.0, -1.0
    for step in range(-reach, reach + 1):
        shift = step * GRID
        # notes moved past our audio's end count as missed; a tiny pull towards no shift breaks ties
        score = float((_mask(notes, n, shift) & sung).sum() / total) - 0.0005 * abs(shift)
        if score > best_score:
            best, best_score = shift, score
    return round(best, 2), round(best_score, 3)


def melody(vocals_path, song: dict, offset: float, lines: list[dict], duration: float) -> dict:
    """melody.json from the file's notes; loudness ("energy") still comes from our vocal stem."""
    data, sr = sf.read(str(vocals_path), dtype="float32", always_2d=True)
    hop = int(sr * HOP)
    mono = data.mean(axis=1)
    db = 20 * np.log10(np.sqrt((mono[: len(mono) // hop * hop].reshape(-1, hop) ** 2).mean(axis=1)) + 1e-9)
    energy = np.clip((db - (np.percentile(db, 95) - 40.0)) / 40.0, 0.0, 1.0)
    pitch = np.zeros(len(energy))
    notes = [n for n in ultrastar.to_notes(song, offset) if n["end"] <= duration]
    for note in sorted(notes, key=lambda n: n["singer"] == "P1"):  # P1 last: its pitch wins where parts overlap
        pitch[int(note["start"] / HOP): int(note["end"] / HOP)] = note["midi"]
    words = [w for line in lines for w in line["words"]]
    for note in notes:
        overlap = [min(note["end"], w["end"]) - max(note["start"], w["start"]) for w in words]
        note["word"] = int(np.argmax(overlap)) if overlap and max(overlap) > 0 else -1
    return {"hop": HOP, "pitch": [round(float(p), 2) for p in pitch],
            "energy": [round(float(e), 2) for e in energy], "notes": notes}


def pitch_agreement(song: dict, offset: float, midi: np.ndarray, voiced: np.ndarray) -> tuple:
    """(offset refined within ±1 s, agreement, chance, pitched share): how often the notes match the sung pitch
    (any octave, ±1 semitone) where our singer has a clear pitch. Chance is the same measure
    with the notes moved 5-15 s off, so the bar adapts to repetitive or monotone songs."""
    notes = [n for n in ultrastar.to_notes(song, 0.0)]

    def agree(shift: float) -> tuple[float, int, int]:
        hits = frames = total = 0
        for n in notes:
            a, b = int((n["start"] + shift) / HOP), int((n["end"] + shift) / HOP)
            if a < 0 or b > len(midi):
                continue
            total += b - a
            sung = voiced[a:b]
            diff = (midi[a:b][sung] - n["midi"] + 6) % 12 - 6  # octave folded
            hits, frames = hits + int((np.abs(diff) <= 1).sum()), frames + int(sung.sum())
        return hits / max(frames, 1), frames, total

    # Loudness only finds the offset roughly in continuous singing: the pitch match pins it down
    score, best = max((agree(offset + k * 0.04)[0], offset + k * 0.04) for k in range(-25, 26))
    _, frames, total = agree(best)
    chance = float(np.median([agree(best + s)[0] for s in (-15, -11, -7, -5, 5, 7, 11, 15)]))
    return round(best, 2), round(score, 3), round(chance, 3), round(frames / max(total, 1), 3)
