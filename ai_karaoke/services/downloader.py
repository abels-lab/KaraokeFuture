"""YouTube search (top N), audio extraction to original.wav, and the muted video track."""
import logging
import re
from pathlib import Path

from yt_dlp import YoutubeDL

from config import ORIGINAL_FILE, VIDEO_STEM
from core import cache_manager, settings

log = logging.getLogger(__name__)

_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_BASE_OPTS = {"quiet": True, "no_warnings": True, "noplaylist": True}


class DownloadError(RuntimeError):
    """Raised when a track can't be fetched or is rejected."""


def is_valid_id(song_id: str) -> bool:
    """YouTube ids double as cache folder names, so validate strictly."""
    return bool(song_id and _VIDEO_ID.match(song_id))


def _thumbnail(video_id: str) -> str:
    return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"


def _clean_channel(name: str) -> str:
    return re.sub(r"\s*-\s*Topic$|VEVO$", "", name or "").strip()


def search(query: str, limit: int | None = None) -> list[dict]:
    """Fast flat search: returns [{id, title, channel, duration, thumbnail}]."""
    query = (query or "").strip()
    if not query:
        return []
    opts = {**_BASE_OPTS, "extract_flat": "in_playlist", "skip_download": True}
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearch{limit or settings.get('search_results')}:{query}", download=False)

    results = []
    for entry in info.get("entries") or []:
        video_id = entry.get("id")
        if not is_valid_id(video_id):
            continue
        duration = entry.get("duration")
        results.append({
            "id": video_id,
            "title": entry.get("title") or "Unknown title",
            "channel": _clean_channel(entry.get("channel") or entry.get("uploader") or ""),
            "duration": int(duration) if duration else None,
            "thumbnail": _thumbnail(video_id),
        })
    return results


def download(song_id: str, protect: set[str] | None = None) -> Path:
    """Download best audio as WAV. Evicts old cache entries first if needed."""
    if not is_valid_id(song_id):
        raise DownloadError(f"Invalid video id: {song_id!r}")

    target = cache_manager.song_file(song_id, ORIGINAL_FILE)
    if target.is_file():
        return target

    cache_manager.ensure_space(protect=(protect or set()) | {song_id})
    folder = cache_manager.song_dir(song_id)
    folder.mkdir(parents=True, exist_ok=True)

    opts = {
        **_BASE_OPTS,
        "format": "bestaudio/best",
        "outtmpl": str(folder / "original.%(ext)s"),
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "wav"}],
    }
    url = f"https://www.youtube.com/watch?v={song_id}"
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            duration = info.get("duration") or 0
            max_seconds = settings.get("max_duration_min") * 60
            if duration > max_seconds:
                raise DownloadError(
                    f"Track is {duration // 60} min long (limit {max_seconds // 60:.0f} min)"
                )
            ydl.process_ie_result(info, download=True)
    except DownloadError:
        cache_manager.evict(song_id)
        raise
    except Exception as exc:  # yt-dlp raises many types; normalise them
        cache_manager.evict(song_id)
        raise DownloadError(f"Download failed: {exc}") from exc

    if not target.is_file():
        cache_manager.evict(song_id)
        raise DownloadError("FFmpeg did not produce original.wav (is FFmpeg on PATH?)")

    cache_manager.update_meta(
        song_id,
        title=info.get("title") or "Unknown title",
        channel=_clean_channel(info.get("channel") or info.get("uploader") or ""),
        duration=int(duration) if duration else None,
        thumbnail=_thumbnail(song_id),
        status="downloaded",
    )
    log.info("Downloaded %s (%s)", song_id, info.get("title"))
    return target


def find_video(song_id: str) -> Path | None:
    """Finished video file only (never yt-dlp's half-written .part leftovers)."""
    files = cache_manager.song_dir(song_id).glob(f"{VIDEO_STEM}.*")
    return next((f for f in sorted(files) if f.suffix in (".mp4", ".webm", ".mkv")), None)


def download_video(song_id: str) -> Path | None:
    """Video-only stream of the same upload (no sound, no merge, no FFmpeg needed).

    H.264 MP4 first because every browser and smart TV plays it. Failures are
    logged and return None: a song without video still works.
    """
    if (existing := find_video(song_id)) is not None:
        return existing
    h = settings.get("video_max_height")
    opts = {
        **_BASE_OPTS,
        "format": f"bv*[height<={h}][vcodec^=avc1]/bv*[height<={h}][ext=mp4]/bv*[height<={h}]/bv*",
        "outtmpl": str(cache_manager.song_dir(song_id) / f"{VIDEO_STEM}.%(ext)s"),
    }
    try:
        with YoutubeDL(opts) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={song_id}"])
    except Exception as exc:
        log.warning("No video for %s: %s", song_id, exc)
        return None
    if (video := find_video(song_id)) is not None:
        cache_manager.update_meta(song_id, video=video.name)
        log.info("Video for %s: %s (%.0f MB)", song_id, video.name, video.stat().st_size / 1024**2)
    return video
