"""Vocal / instrumental separation via audio-separator, with strict VRAM cleanup."""
import logging
import os
from pathlib import Path

from config import (
    INSTRUMENTAL_FILE,
    MODELS_DIR,
    ORIGINAL_FILE,
    VOCALS_FILE,
    free_vram,
)
from core import cache_manager, settings

log = logging.getLogger(__name__)


class SeparationError(RuntimeError):
    """Raised when stems could not be produced."""


def _resolve(folder: Path, name: str) -> Path:
    path = Path(name)
    return path if path.is_absolute() else folder / path.name


def _mix_stems(stems: list[Path], target: Path) -> None:
    """Sum non-vocal stems (e.g. 4-stem Demucs: drums+bass+other) into one file."""
    import numpy as np
    import soundfile as sf

    mix, rate = None, None
    for stem in stems:
        data, rate = sf.read(str(stem), dtype="float32", always_2d=True)
        if mix is None:
            mix = data
        else:
            length = min(len(mix), len(data))
            mix = mix[:length] + data[:length]
    sf.write(str(target), np.clip(mix, -1.0, 1.0), rate, subtype="PCM_16")


def _organise_outputs(folder: Path, outputs: list[str]) -> None:
    """Rename audio-separator's long output names to vocals.wav / instrumental.wav."""
    files = [_resolve(folder, name) for name in outputs]
    vocals = [f for f in files if "(vocals)" in f.name.lower()]
    others = [f for f in files if f not in vocals]
    if not vocals or not others:
        raise SeparationError(f"Unexpected separator outputs: {[f.name for f in files]}")

    os.replace(vocals[0], folder / VOCALS_FILE)
    instrumental = [f for f in others if "(instrumental)" in f.name.lower()]
    if instrumental:
        os.replace(instrumental[0], folder / INSTRUMENTAL_FILE)
        leftovers = [f for f in others if f != instrumental[0]]
    else:
        _mix_stems(others, folder / INSTRUMENTAL_FILE)
        leftovers = others
    for extra in leftovers + vocals[1:]:
        extra.unlink(missing_ok=True)


def separate(song_id: str) -> tuple[Path, Path]:
    """Create vocals.wav + instrumental.wav for a downloaded song.

    The model is loaded, used once, then deleted and VRAM is released so the
    Whisper step afterwards gets the whole 6 GB.
    """
    folder = cache_manager.song_dir(song_id)
    vocals, instrumental = folder / VOCALS_FILE, folder / INSTRUMENTAL_FILE
    if vocals.is_file() and instrumental.is_file():
        return vocals, instrumental

    source = folder / ORIGINAL_FILE
    if not source.is_file():
        raise SeparationError(f"Missing {ORIGINAL_FILE} for {song_id}")

    from audio_separator.separator import Separator  # heavy import, keep lazy

    separator = None
    try:
        separator = Separator(
            output_dir=str(folder),
            output_format="WAV",
            model_file_dir=str(MODELS_DIR),
            log_level=logging.WARNING,
            use_autocast=settings.get("separator_fp16"),
            mdxc_params={"segment_size": 256, "override_model_segment_size": False,
                         "batch_size": 1, "overlap": settings.get("separator_overlap"), "pitch_shift": 0},
        )
        separator.load_model(model_filename=(model := settings.get("separator_model")))
        log.info("Separating %s with %s", song_id, model)
        outputs = separator.separate(str(source))
    except Exception as exc:
        raise SeparationError(f"Separation failed: {exc}") from exc
    finally:
        del separator
        free_vram()

    _organise_outputs(folder, outputs)
    if not settings.get("keep_original"):
        source.unlink(missing_ok=True)

    cache_manager.update_meta(song_id, status="separated")
    log.info("Separated %s", song_id)
    return vocals, instrumental
