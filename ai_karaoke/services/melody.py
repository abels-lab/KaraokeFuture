"""Reference melody for the singing game: pitch of the isolated vocals (torchcrepe, GPU).

melody.json = {"hop": 0.02,
               "pitch": [MIDI float or 0 per frame],   # 0 = no clear pitch (silence, shouts)
               "energy": [0..1 per frame],              # vocal loudness, for amplitude matching
               "notes": [{"start", "end", "midi": int, "word": index or -1}]}
Notes are stable-pitch stretches, like the note bars of SingStar / UltraStar.
"""
import json
import logging

import numpy as np
import soundfile as sf

from config import LYRICS_FILE, MELODY_FILE, VOCALS_FILE, free_vram
from core import cache_manager

log = logging.getLogger(__name__)

HOP = 0.02            # 50 frames per second
SR = 16000            # CREPE's sample rate
VOICED = 0.4          # periodicity above this = a clear sung pitch
BRIDGE = 3            # unvoiced frames (60 ms) that don't break a note
SPLIT = 0.8           # semitones away from the running note that start a new one ...
SPLIT_FRAMES = 3      # ... when it lasts this many frames (60 ms)
MIN_NOTE = 0.1        # seconds


def _pitch_track(path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    import torch
    import torchaudio
    import torchcrepe

    data, sr = sf.read(str(path), dtype="float32", always_2d=True)
    mono = torch.from_numpy(data.mean(axis=1))[None]
    audio = torchaudio.functional.resample(mono, sr, SR)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    try:
        pitch, periodicity = torchcrepe.predict(
            audio, SR, hop_length=int(SR * HOP), fmin=65, fmax=1000, model="full",
            decoder=torchcrepe.decode.viterbi, return_periodicity=True, batch_size=512, device=device)
        periodicity = torchcrepe.filter.median(periodicity, 3)
        f0, conf = pitch[0].cpu().numpy(), periodicity[0].cpu().numpy()
    finally:
        del audio
        free_vram()  # CREPE is unloaded before the next model, like every AI step
    frames = mono[0].numpy()[: len(mono[0]) // int(sr * HOP) * int(sr * HOP)].reshape(-1, int(sr * HOP))
    db = 20 * np.log10(np.sqrt((frames ** 2).mean(axis=1)) + 1e-9)
    n = min(len(f0), len(db))
    return f0[:n], conf[:n], db[:n]


def _notes(midi: np.ndarray, voiced: np.ndarray) -> list[dict]:
    notes, run = [], []

    def close():
        if len(run) * HOP >= MIN_NOTE:
            values = midi[[i for i in run if voiced[i]]]
            notes.append({"start": round(run[0] * HOP, 2), "end": round((run[-1] + 1) * HOP, 2),
                          "midi": int(round(float(np.median(values))))})
        run.clear()

    gap = 0
    for i in range(len(midi)):
        if not voiced[i]:
            gap += 1
            if gap > BRIDGE and run:
                close()
            continue
        gap = 0
        if run:
            ref = float(np.median(midi[[j for j in run[-25:] if voiced[j]]]))
            if abs(midi[i] - ref) > SPLIT and all(abs(midi[k] - ref) > SPLIT for k in range(i, min(i + SPLIT_FRAMES, len(midi))) if voiced[k]):
                close()
        run.append(i)
    if run:
        close()
    return notes


def _hold_words(song_id: str, midi: np.ndarray) -> None:
    """Stretch lyric words over the notes the singer holds (see word_timing.hold_notes)."""
    from services import word_timing
    path = cache_manager.song_file(song_id, LYRICS_FILE)
    try:
        lines = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return
    if extended := word_timing.hold_notes(lines, midi.tolist(), HOP):
        path.with_suffix(".tmp").write_text(json.dumps(lines, ensure_ascii=False), encoding="utf-8")
        path.with_suffix(".tmp").replace(path)  # atomic: the stage may be reading it
        log.info("Held notes: %d lyric words of %s extended", extended, song_id)


def _tag_words(notes: list[dict], song_id: str) -> None:
    try:
        lines = json.loads(cache_manager.song_file(song_id, LYRICS_FILE).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        lines = []
    words = [w for line in lines for w in line["words"]]
    for note in notes:  # the word sharing most time with the note (a long held note can outlast its middle)
        overlap = [min(note["end"], w["end"] + 0.15) - max(note["start"], w["start"] - 0.15) for w in words]
        best = int(np.argmax(overlap)) if overlap else -1
        note["word"] = best if best >= 0 and overlap[best] > 0 else -1


def _clean(notes: list[dict], song_id: str) -> list[dict]:
    """Keep sung notes: lyric words only when there are lyrics (bleed in the vocal stem is pitched
    too), else clear singing ≥ 0.3 s. Fold octave slips of the pitch tracker into the voice's range."""
    from services import vocal_activity
    loud, lyrics = vocal_activity.map_for(song_id).get("loud", []), any(n["word"] >= 0 for n in notes)
    kept = [n for n in notes if n["word"] >= 0 or (not lyrics and n["end"] - n["start"] >= 0.3 and
            vocal_activity.vocal_fraction(n["start"], n["end"], loud) > 0.6)]
    if kept:
        centre = float(np.median([n["midi"] for n in kept]))
        for n in kept:
            while n["midi"] - centre > 12:
                n["midi"] -= 12
            while centre - n["midi"] > 12:
                n["midi"] += 12
    return kept


def extract(song_id: str) -> dict:
    """Compute and save melody.json for a separated song. Returns a short summary."""
    f0, conf, db = _pitch_track(cache_manager.song_file(song_id, VOCALS_FILE))
    voiced = (conf > VOICED) & (f0 > 0)
    midi = np.where(voiced, 69 + 12 * np.log2(np.maximum(f0, 1.0) / 440.0), 0.0)
    # Smooth wobble inside voiced stretches (vibrato stays, CREPE jitter goes)
    smooth = np.convolve(midi, np.ones(3) / 3, mode="same")
    midi = np.where(voiced & (np.convolve(voiced, np.ones(3), mode="same") == 3), smooth, midi)
    peak = float(np.percentile(db, 95))
    energy = np.clip((db - (peak - 40.0)) / 40.0, 0.0, 1.0)
    notes = _notes(midi, voiced)
    _hold_words(song_id, midi)
    _tag_words(notes, song_id)
    notes = _clean(notes, song_id)
    melody = {"hop": HOP, "pitch": [round(float(m), 2) for m in midi],
              "energy": [round(float(e), 2) for e in energy], "notes": notes}
    target = cache_manager.song_file(song_id, MELODY_FILE)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(melody, separators=(",", ":")), encoding="utf-8")
    tmp.replace(target)
    span = [n["midi"] for n in notes]
    summary = {"notes": len(notes), "voiced": round(float(voiced.mean()), 2),
               "range": [min(span), max(span)] if span else None}
    cache_manager.update_meta(song_id, melody=summary)
    log.info("Melody for %s: %d notes, %s%% voiced, range %s", song_id, summary["notes"],
             int(summary["voiced"] * 100), summary["range"])
    return summary
