"""Central configuration: paths, limits, model names and small runtime helpers."""
import gc
import logging
import os
import socket
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = Path(os.getenv("KARAOKE_CACHE_DIR", BASE_DIR / "cache"))
MODELS_DIR = Path(os.getenv("KARAOKE_MODELS_DIR", BASE_DIR / "models"))
STATIC_DIR = BASE_DIR / "static"
# Guest-pasted lyrics, one <song_id>.txt each. Outside CACHE_DIR: never evicted.
LYRICS_STORE_DIR = Path(os.getenv("KARAOKE_LYRICS_DIR", BASE_DIR / "lyrics_store"))

for _dir in (CACHE_DIR, MODELS_DIR, STATIC_DIR, LYRICS_STORE_DIR):
    _dir.mkdir(parents=True, exist_ok=True)

# Files stored inside ./cache/<song_id>/
ORIGINAL_FILE = "original.wav"
VOCALS_FILE = "vocals.wav"
INSTRUMENTAL_FILE = "instrumental.wav"
LYRICS_FILE = "lyrics.json"
META_FILE = "meta.json"
VOCAL_MAP_FILE = "vocals.json"   # where singing actually happens: {"regions": [[start, end], ...]}
ONLINE_LYRICS_FILE = "online.lrc"  # lyrics found online, kept so re-syncs don't depend on flaky providers
VIDEO_STEM = "video"             # muted video track: video.mp4 / video.webm

# ── Server ───────────────────────────────────────────────────────────────────
HOST = os.getenv("KARAOKE_HOST", "0.0.0.0")
PORT = int(os.getenv("KARAOKE_PORT", "8000"))

# ── Cache ────────────────────────────────────────────────────────────────────
CACHE_LIMIT_BYTES = 5 * 1024**3          # hard 5 GB ceiling for ./cache
CACHE_HEADROOM_BYTES = 300 * 1024**2     # room reserved for the incoming song

# ── Downloading ──────────────────────────────────────────────────────────────
SEARCH_RESULTS = 5
MAX_QUEUE_LENGTH = 50
MAX_DURATION_SEC = int(os.getenv("KARAOKE_MAX_DURATION", "600"))  # skip >10 min
# Muted video stream from the same upload, so it shares the audio's timeline exactly.
DOWNLOAD_VIDEO = os.getenv("KARAOKE_VIDEO", "1") == "1"
VIDEO_MAX_HEIGHT = int(os.getenv("KARAOKE_VIDEO_HEIGHT", "720"))   # ~30-60 MB per song

# ── Vocal separation ─────────────────────────────────────────────────────────
# 2-stem BS-Roformer: excellent vocal isolation and fits in 6 GB VRAM.
# Lighter alternatives: "UVR-MDX-NET-Inst_HQ_3.onnx", "htdemucs_ft.yaml".
SEPARATOR_MODEL = os.getenv(
    "KARAOKE_SEPARATOR_MODEL", "model_bs_roformer_ep_317_sdr_12.9755.ckpt"
)
KEEP_ORIGINAL = os.getenv("KARAOKE_KEEP_ORIGINAL", "0") == "1"
# Roformer/MDXC chunk overlap: 2 is ~4x faster than the model default with
# near-identical quality. fp16 autocast roughly halves time on RTX tensor cores.
SEPARATOR_OVERLAP = int(os.getenv("KARAOKE_SEPARATOR_OVERLAP", "2"))
SEPARATOR_FP16 = os.getenv("KARAOKE_SEPARATOR_FP16", "1") == "1"

# ── Lyrics / Whisper ─────────────────────────────────────────────────────────
WHISPER_MODEL = os.getenv("KARAOKE_WHISPER_MODEL", "large-v3-turbo")
WHISPER_COMPUTE_TYPE = "float16"
# Measured on sung Russian (WER vs. reference): turbo without text conditioning 28.5%,
# large-v3 30%, any model WITH conditioning 37-47% (locks in mishearings, loops).
CONDITION_ON_PREVIOUS_TEXT = False
MAX_CHARS_PER_SEC = 35          # transcribed lines denser than this are hallucinations
ALIGN_FAILURE_THRESHOLD = 0.4   # abort align() if >40% of words get zero duration
MIN_LYRIC_LINES = 4             # fewer fetched lines => treat as "not found"


def setup_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def get_local_ip() -> str:
    """Return this machine's LAN IP (the one guests' phones can reach)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # UDP connect sends no packets; it just selects the outbound interface.
        sock.connect(("10.255.255.255", 1))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def remote_url() -> str:
    return f"http://{get_local_ip()}:{PORT}/remote"


def qr_svg_data_uri(url: str | None = None) -> str:
    """QR code for the guest remote page as an SVG data URI (<img src=...>)."""
    import segno

    qr = segno.make(url or remote_url(), error="m")
    return qr.svg_data_uri(scale=8, border=2, dark="#000000", light="#ffffff")


def free_vram() -> None:
    """Release cached CUDA memory. Call AFTER `del model` in the caller."""
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.synchronize()
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
    except ImportError:
        pass
