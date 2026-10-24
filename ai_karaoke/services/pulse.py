"""The music's pulse for the adaptive theme: how loud the backing track is and where its beats fall.

The screens light up with the music, but the projector has no audio of its own to listen to,
so both screens read the same timeline from here and follow their own clock (no extra network
traffic, always in sync). CPU only (numpy, about a second per song, no model, no VRAM); the
result is kept in the song's folder as pulse.json.
- level: loudness every HOP seconds, 0..1 (1 = the song's loud parts)
- beats: moments where the bass suddenly gets louder (kick drum, bass hits), in seconds
"""
import json

import numpy as np
import soundfile as sf

from config import INSTRUMENTAL_FILE
from core import cache_manager

PULSE_FILE = "pulse.json"
HOP = 0.05            # seconds per level value (20 per second: smooth enough for lights)
BASS_HZ = 150         # kick drum and bass live below this
MIN_BEAT_GAP = 0.25   # seconds: at most 4 beats a second (240 BPM)


def _beats(flux: np.ndarray) -> list[float]:
    """Bass onsets clearly above the surrounding second's average."""
    window = int(1 / HOP)
    local = np.convolve(flux, np.ones(window) / window, mode="same")
    threshold = local + 1.5 * flux.std()
    beats, last = [], -MIN_BEAT_GAP
    for i in range(1, len(flux) - 1):
        t = i * HOP
        if flux[i] > threshold[i] and flux[i] >= flux[i - 1] and flux[i] >= flux[i + 1] and t - last >= MIN_BEAT_GAP:
            beats.append(round(t, 2))
            last = t
    return beats


def compute(song_id: str) -> dict:
    out = cache_manager.song_file(song_id, PULSE_FILE)
    if out.is_file():
        return json.loads(out.read_text(encoding="utf-8"))
    audio, sr = sf.read(str(cache_manager.song_file(song_id, INSTRUMENTAL_FILE)), dtype="float32", always_2d=True)
    mono = audio.mean(axis=1)
    hop = int(sr * HOP)
    frames = mono[: len(mono) // hop * hop].reshape(-1, hop)
    rms = np.sqrt((frames ** 2).mean(axis=1))
    level = np.clip(rms / (np.percentile(rms, 98) + 1e-9), 0, 1)
    spectrum = np.abs(np.fft.rfft(frames * np.hanning(hop), axis=1))
    bass = np.log1p(spectrum[:, np.fft.rfftfreq(hop, 1 / sr) < BASS_HZ].sum(axis=1))
    flux = np.maximum(0, np.diff(bass, prepend=bass[0]))   # only rises: a hit, not its fade
    result = {"hop": HOP, "level": [round(float(v), 2) for v in level], "beats": _beats(flux)}
    out.write_text(json.dumps(result, separators=(",", ":")), encoding="utf-8")
    return result
