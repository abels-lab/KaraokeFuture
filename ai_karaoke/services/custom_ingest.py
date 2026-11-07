"""Ingestion of custom / unofficial songs: file uploads (MP3, WAV, FLAC, M4A, etc.)
and arbitrary external links (YouTube, SoundCloud, Bandcamp, Vimeo, direct audio URLs).

Both flows normalize audio to 44.1 kHz 16-bit stereo PCM `cache/<song_id>/original.wav`
with deterministic IDs prefixed with `u_` (e.g. `u_a1b2c3d4e5f67890`), so the standard
background worker immediately skips the download step and runs stem separation,
lyrics alignment, and pitch extraction.
"""
import asyncio
import json
import logging
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

from yt_dlp import YoutubeDL

from config import ORIGINAL_FILE
from core import cache_manager, source_ids, source_links
from services import lyrics_source, metadata_enricher, search_filter, sources
from services.song_names import clean_channel

log = logging.getLogger(__name__)

MAX_FILE_BYTES = 100 * 1024 * 1024  # 100 MB limit for uploaded audio


class IngestError(ValueError):
    """Raised when an uploaded file or link fails validation or ingestion."""


def _probe_audio_file(file_path: Path) -> tuple[float, str, str]:
    """Runs ffprobe on an audio file to extract duration, title, and artist.
    Returns (duration_seconds, title, artist)."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(file_path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=15)
        data = json.loads(proc.stdout)
    except Exception as exc:
        raise IngestError(f"Could not read audio format: {exc}") from exc

    streams = data.get("streams") or []
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if not audio_stream:
        raise IngestError("The uploaded file does not contain a valid audio stream.")

    fmt = data.get("format") or {}
    duration = float(fmt.get("duration") or audio_stream.get("duration") or 0.0)
    tags = {k.lower(): v for k, v in (fmt.get("tags") or {}).items()}
    title = tags.get("title") or ""
    artist = tags.get("artist") or tags.get("album_artist") or tags.get("author") or ""
    return duration, title.strip(), artist.strip()


def _convert_to_wav(input_path: Path, output_path: Path) -> None:
    """Converts any audio file to 16-bit 44.1kHz stereo PCM WAV via FFmpeg."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_out = output_path.with_suffix(".tmp.wav")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "44100",
        "-ac", "2",
        str(tmp_out),
    ]
    try:
        subprocess.run(cmd, capture_output=True, check=True, timeout=120)
        tmp_out.replace(output_path)
    except subprocess.CalledProcessError as exc:
        tmp_out.unlink(missing_ok=True)
        err_msg = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else str(exc)
        raise IngestError(f"Audio conversion failed: {err_msg[:200]}") from exc
    except Exception as exc:
        tmp_out.unlink(missing_ok=True)
        raise IngestError(f"Audio conversion failed: {exc}") from exc


def probe_url(url: str) -> dict:
    """Validates and inspects an external URL (YouTube, SoundCloud, Bandcamp, direct audio, etc.).
    Returns preview metadata: {url, title, artist, duration, thumbnail}."""
    url = (url or "").strip()
    if not url:
        raise IngestError("URL is required")

    # SSRF check: verifies scheme and public DNS resolution
    try:
        clean_url = source_links.check_url(url, resolve=True)
    except Exception as exc:
        raise IngestError(str(exc)) from exc

    opts = {
        **sources.BASE_OPTS,
        "format": "bestaudio/best",
        "skip_download": True,
    }
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(clean_url, download=False)
    except Exception as exc:
        raise IngestError(f"Could not load media from link: {exc}") from exc

    if not info:
        raise IngestError("No playable media found at that link.")

    duration = int(round(info.get("duration") or 0))
    if problem := search_filter.duration_problem(duration):
        raise IngestError(problem)

    raw_channel = info.get("channel") or info.get("uploader") or ""
    return {
        "url": clean_url,
        "title": info.get("title") or "Custom Track",
        "artist": clean_channel(raw_channel),
        "duration": duration if duration > 0 else None,
        "thumbnail": info.get("thumbnail"),
    }


def ingest_file(
    file_bytes: bytes,
    filename: str,
    title: str | None = None,
    artist: str | None = None,
    lyrics: str | None = None,
) -> dict:
    """Synchronous file ingestion: converts audio to original.wav, saves lyrics, and sets up metadata."""
    if len(file_bytes) > MAX_FILE_BYTES:
        raise IngestError(f"File too large: max allowed is {MAX_FILE_BYTES // 1024**2} MB")
    if len(file_bytes) < 1000:
        raise IngestError("File is empty or too small to be audio.")

    song_id = source_ids.make_upload_id(file_bytes)
    folder = cache_manager.song_dir(song_id)
    folder.mkdir(parents=True, exist_ok=True)
    target_wav = folder / ORIGINAL_FILE

    with tempfile.NamedTemporaryFile(suffix=Path(filename).suffix or ".audio", delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = Path(tmp.name)

    try:
        duration, tag_title, tag_artist = _probe_audio_file(tmp_path)
        int_dur = int(round(duration))
        if problem := search_filter.duration_problem(int_dur):
            raise IngestError(problem)

        cache_manager.ensure_space(protect={song_id})
        _convert_to_wav(tmp_path, target_wav)
    finally:
        tmp_path.unlink(missing_ok=True)

    final_title = (title or "").strip() or tag_title or Path(filename).stem.replace("_", " ") or "Uploaded Song"
    final_artist = (artist or "").strip() or tag_artist or "Custom Artist"

    has_lyrics = False
    if lyrics and lyrics.strip():
        try:
            lyrics_source.save_user(song_id, lyrics.strip())
            has_lyrics = True
        except Exception as exc:
            log.warning("Could not save initial custom lyrics for %s: %s", song_id, exc)

    meta = cache_manager.update_meta(
        song_id,
        title=final_title,
        channel=final_artist,
        duration=int_dur if int_dur > 0 else None,
        status="downloaded",
        source="upload",
        custom=True,
        pinned=True,
        has_user_lyrics=has_lyrics,
    )
    metadata_enricher.enrich_metadata(song_id, final_title, final_artist, save=True)
    log.info("Ingested custom file %s -> %s (%s - %s)", filename, song_id, final_artist, final_title)
    return meta


def ingest_link(
    url: str,
    title: str | None = None,
    artist: str | None = None,
    lyrics: str | None = None,
) -> dict:
    """Downloads audio from a URL, saves to cache/<song_id>/original.wav, and sets up metadata."""
    probe = probe_url(url)
    clean_url = probe["url"]
    song_id = source_ids.make_upload_id(clean_url)
    source_ids.remember([clean_url])

    folder = cache_manager.song_dir(song_id)
    folder.mkdir(parents=True, exist_ok=True)
    target_wav = folder / ORIGINAL_FILE

    if not target_wav.is_file():
        cache_manager.ensure_space(protect={song_id})
        opts = {
            **sources.BASE_OPTS,
            "format": "bestaudio/best",
            "outtmpl": str(folder / "original.%(ext)s"),
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "wav"}],
        }
        with YoutubeDL(opts) as ydl:
            ydl.download([clean_url])

        if not target_wav.is_file():
            # Check if any original.* was generated
            for cand in folder.glob("original.*"):
                if cand.suffix != ".wav":
                    _convert_to_wav(cand, target_wav)
                    cand.unlink(missing_ok=True)
                    break
        if not target_wav.is_file():
            raise IngestError("Failed to extract audio from link into WAV format.")

    final_title = (title or "").strip() or probe["title"]
    final_artist = (artist or "").strip() or probe["artist"]
    duration = probe["duration"]
    thumbnail = probe["thumbnail"]

    has_lyrics = False
    if lyrics and lyrics.strip():
        try:
            lyrics_source.save_user(song_id, lyrics.strip())
            has_lyrics = True
        except Exception as exc:
            log.warning("Could not save initial custom lyrics for %s: %s", song_id, exc)

    meta = cache_manager.update_meta(
        song_id,
        title=final_title,
        channel=final_artist,
        duration=duration,
        thumbnail=thumbnail,
        status="downloaded",
        source="custom_link",
        source_url=clean_url,
        custom=True,
        pinned=True,
        has_user_lyrics=has_lyrics,
    )
    metadata_enricher.enrich_metadata(song_id, final_title, final_artist, save=True)
    log.info("Ingested custom link %s -> %s (%s - %s)", clean_url, song_id, final_artist, final_title)
    return meta
