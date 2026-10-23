"""Audio download to original.wav (with automatic fallback) and the muted video track.

The cache folder is always named after the id the guest picked, even when the audio comes
from a mirror or SoundCloud (see services.fallback), so the queue, TV, screen and library
keep using one stable id. meta.json records which upload was really used.
"""
import logging
from pathlib import Path
import time

from yt_dlp import YoutubeDL

from config import ORIGINAL_FILE, VIDEO_STEM
from core import cache_manager, settings
from services import fallback, metadata_enricher, search_filter, search_memory, sources, sponsorblock
from services.song_names import clean_channel, song_key

log = logging.getLogger(__name__)
is_valid_id = sources.is_valid_id   # YouTube ids and "sc_<digits>" SoundCloud ids


class DownloadError(RuntimeError):
    """Raised when a track can't be fetched or is rejected."""


class LengthError(DownloadError):
    """Too long or too short: every mirror has the same length, so don't try them."""


def _remove_partial(folder: Path) -> None:
    """Leftovers of a failed attempt (meta.json stays for the next one)."""
    for leftover in folder.glob("original.*"):
        leftover.unlink(missing_ok=True)


def _fetch(upload_id: str, folder: Path) -> dict:
    """Download one upload's audio into folder/original.wav. Returns yt-dlp's info."""
    opts = {
        **sources.BASE_OPTS,
        "format": sources.audio_format(upload_id),
        "outtmpl": str(folder / "original.%(ext)s"),
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "wav"}],
    }
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(sources.page_url(upload_id), download=False)
            if problem := search_filter.duration_problem(info.get("duration") or 0):
                raise LengthError(problem)
            ydl.process_ie_result(info, download=True)
    except DownloadError:
        raise
    except Exception as exc:  # yt-dlp raises many types; normalise them
        raise DownloadError(f"Download failed: {exc}") from exc
    if not (folder / ORIGINAL_FILE).is_file():
        raise DownloadError("FFmpeg did not produce original.wav (is FFmpeg on PATH?)")
    return info


def download(song_id: str, protect: set[str] | None = None) -> Path:
    """Download best audio as WAV, trying mirrors and SoundCloud if the pick fails.
    Evicts old cache entries first if needed."""
    if not is_valid_id(song_id):
        raise DownloadError(f"Invalid song id: {song_id!r}")

    target = cache_manager.song_file(song_id, ORIGINAL_FILE)
    if target.is_file():
        return target

    cache_manager.ensure_space(protect=(protect or set()) | {song_id})
    folder = cache_manager.song_dir(song_id)
    folder.mkdir(parents=True, exist_ok=True)

    errors: list[str] = []
    info, used = None, song_id
    for used in fallback.candidates(song_id):
        try:
            info = _fetch(used, folder)
            break
        except DownloadError as exc:
            log.warning("Download of %s failed: %s", used, exc)
            errors.append(str(exc))
            _remove_partial(folder)
            if isinstance(exc, LengthError):
                break
            time.sleep(1.0)  # pause before trying next mirror if rate-limited
    if info is None:
        cache_manager.evict(song_id)
        raise DownloadError(errors[0] if len(errors) == 1 else f"{errors[0]} (and {len(errors) - 1} backup(s) failed)")

    duration = info.get("duration") or 0
    mirrors = (search_memory.hint(song_id) or {}).get("mirrors") or []
    raw_channel = info.get("channel") or info.get("uploader") or ""
    intro_end = sponsorblock.get_intro_end(song_id)
    cache_manager.update_meta(
        song_id,
        title=info.get("title") or "Unknown title",
        channel=clean_channel(raw_channel),
        duration=int(round(duration)) if duration else None,
        thumbnail=sources.thumbnail(used, info.get("thumbnail")) or sources.thumbnail(song_id),
        status="downloaded",
        source=sources.source_of(used), source_id=used,
        source_url=info.get("webpage_url") or sources.page_url(used),
        key=song_key(info.get("title") or "", raw_channel),
        mirrors=[m for m in mirrors if m != used],   # backups for a later re-download
        fallback_used=used != song_id,
        intro_end=intro_end,
    )
    metadata_enricher.enrich_metadata(song_id, info.get("title") or "Unknown title", raw_channel, save=True)
    log.info("Downloaded %s from %s (%s)%s", song_id, sources.source_of(used), info.get("title"),
             f" via backup {used}" if used != song_id else "")
    return target


def find_video(song_id: str) -> Path | None:
    """Finished video file only (never yt-dlp's half-written .part leftovers)."""
    files = cache_manager.song_dir(song_id).glob(f"{VIDEO_STEM}.*")
    return next((f for f in sorted(files) if f.suffix in (".mp4", ".webm", ".mkv")), None)


def download_video(song_id: str) -> Path | None:
    """Video-only stream of the SAME upload the audio came from, so they share one timeline
    (no sound, no merge, no FFmpeg needed). SoundCloud audio has no video: skipped.

    H.264 MP4 first because every browser and smart TV plays it. Failures are
    logged and return None: a song without video still works.
    """
    if (existing := find_video(song_id)) is not None:
        return existing
    upload_id = cache_manager.read_meta(song_id).get("source_id") or song_id
    if not sources.has_video(upload_id):
        log.info("No video for %s: %s audio has none", song_id, sources.source_of(upload_id))
        return None
    h = settings.get("video_max_height")
    opts = {
        **sources.BASE_OPTS,
        "format": f"bv*[height<={h}][vcodec^=avc1]/bv*[height<={h}][ext=mp4]/bv*[height<={h}]/bv*",
        "outtmpl": str(cache_manager.song_dir(song_id) / f"{VIDEO_STEM}.%(ext)s"),
    }
    try:
        with YoutubeDL(opts) as ydl:
            ydl.download([sources.page_url(upload_id)])
    except Exception as exc:
        log.warning("No video for %s: %s", song_id, exc)
        return None
    if (video := find_video(song_id)) is not None:
        cache_manager.update_meta(song_id, video=video.name)
        log.info("Video for %s: %s (%.0f MB)", song_id, video.name, video.stat().st_size / 1024**2)
    return video
