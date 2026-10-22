"""Where lyric TEXT comes from: guest-pasted store, online search, or the cached result.

Timing is done separately by lyrics_aligner; this module never touches the GPU.
"""
import json
import logging
import re

import syncedlyrics

from config import LYRICS_FILE, LYRICS_STORE_DIR, MIN_LYRIC_LINES, ONLINE_LYRICS_FILE
from core import cache_manager
from services import genius, lrclib

log = logging.getLogger(__name__)

_LRC_TAGS = re.compile(r"\[[^\]]*\]|<[^>]*>")
_TITLE_NOISE = re.compile(r"\([^)]*\)|\[[^\]]*\]|\|.*$|\b(official|music|video|lyrics?|audio|hd|4k|mv|"
                          r"karaoke|remaster(ed)?|visualizer|live)\b", re.IGNORECASE)
# Provider credit lines such as "作词 : Noel Gallagher", "主人声 : Ed Sheeran" or "Composed by: ..."
# are not sung. Any short CJK label before a colon is a credit (NetEase lists many roles).
_CREDITS = re.compile(r"^([぀-ヿ一-鿿]{1,6}|(lyrics?|music|composer|composed|written|"
                      r"arranger|arranged|producer|produced|vocals?|mix(ed|ing)?|master(ed|ing)?|"
                      r"recorded|engineer(ed)?)(\s+by)?)\s*[:：]", re.IGNORECASE)
# Section labels some providers keep as lines ("CHORUS:", "(Verse 2)", "Припев:", "x2"): not sung
_SECTION = re.compile(r"^[(\[]?\s*((pre-?)?chorus|verse|bridge|refrain|hook|intro|outro|interlude|instrumental|"
                      r"solo|strophe|припев|куплет|бридж)?\s*\d*\s*[:.]?\s*(\(?[x×]\s*\d+\)?)?\s*[)\]]?$", re.IGNORECASE)


def build_query(title: str, channel: str = "") -> str:
    clean = re.sub(r"\s{2,}", " ", _TITLE_NOISE.sub(" ", title or "")).strip(" -–_")
    return clean if " - " in clean or not channel else f"{channel} {clean}"


_STAMP = re.compile(r"\[(\d{1,3}):(\d{1,2}(?:[.:]\d{1,3})?)\]")


def parse_lines(raw: str) -> list[tuple[float | None, str]]:
    """(start in seconds or None, text) per sung line, without credits or blank lines.

    LRC line timestamps are kept: they anchor the word alignment. A line tagged with
    several timestamps (LRC's shorthand for a repeated chorus) becomes one line per time.
    """
    lines: list[tuple[float | None, str]] = []
    for raw_line in (raw or "").splitlines():
        stamps = [int(m) * 60 + float(s.replace(":", ".")) for m, s in _STAMP.findall(raw_line)]
        text = _LRC_TAGS.sub("", raw_line).strip()
        if text and not _CREDITS.match(text) and not _SECTION.match(text):
            lines += [(t, text) for t in stamps] if stamps else [(None, text)]
    if lines and all(t is not None for t, _ in lines):
        lines.sort(key=lambda line: line[0])
    return lines


def timed(lines: list[tuple[float | None, str]]) -> bool:
    return bool(lines) and all(t is not None for t, _ in lines)


def _format(lines) -> str:
    return "\n".join(f"[{int(t // 60):02d}:{t % 60:05.2f}] {text}" if t is not None else text for t, text in lines)


def fetch_online(title: str, channel: str = "", duration: float | None = None) -> str | None:
    """Lyrics for this exact version from LRCLIB (matched by duration), else from syncedlyrics
    (Musixmatch, LRCLIB, NetEase, Megalobiz, Genius), else plain text from the Genius API.
    LRC timestamps kept."""
    query = build_query(title, channel)
    raw = lrclib.search(query, duration) if duration else None
    try:
        raw = raw or syncedlyrics.search(query)
    except Exception as exc:  # providers fail in many ways; never block the pipeline
        log.warning("syncedlyrics failed for %r: %s", query, exc)
        raw = None
    lines = parse_lines(raw)
    if len(lines) < MIN_LYRIC_LINES:
        lines = parse_lines(genius.fetch(query))
    if len(lines) < MIN_LYRIC_LINES:
        return None
    log.info("Found %d lyric lines for %r (%s)", len(lines), query, "timed" if timed(lines) else "plain")
    return _format(lines)


def online_for(song_id: str, title: str, channel: str = "", duration: float | None = None) -> str | None:
    """Online lyrics for a cached song: searched once (with one retry, providers often miss
    a request at random), then reused so a re-sync never silently swaps the lyrics.
    A cached LRC timed past the end of the audio (another version) is searched again."""
    path = cache_manager.song_file(song_id, ONLINE_LYRICS_FILE)
    cached = path.read_text(encoding="utf-8") if path.is_file() else None
    if cached and lrclib.fits(cached, duration):
        return cached
    if cached:
        log.info("Cached lyrics for %s run past the audio (%.0f s): searching this version", song_id, duration)
    for _ in range(2):
        if raw := fetch_online(title, channel, duration):
            if cached and not lrclib.fits(raw, duration):
                return cached  # nothing better found: keep the text, the aligner drops its timestamps
            path.write_text(raw, encoding="utf-8")
            return raw
    return cached


def forget_online(song_id: str) -> None:
    cache_manager.song_file(song_id, ONLINE_LYRICS_FILE).unlink(missing_ok=True)


def detect_language(text: str) -> str | None:
    try:
        from langdetect import DetectorFactory, detect
        DetectorFactory.seed = 0
        return detect(text).split("-")[0]  # "zh-cn" -> "zh"
    except Exception:
        return None


# ── Guest-pasted / edited lyrics: outside ./cache, so they survive LRU eviction ──
def _user_path(song_id: str):
    return LYRICS_STORE_DIR / f"{song_id}.txt"


def save_user(song_id: str, raw: str) -> int:
    """Plain text or LRC; LRC timestamps are kept as alignment anchors."""
    lines = parse_lines(raw)
    if len(lines) < MIN_LYRIC_LINES:
        raise ValueError(f"Please paste at least {MIN_LYRIC_LINES} lines of lyrics")
    _user_path(song_id).write_text(_format(lines), encoding="utf-8")
    return len(lines)


def load_user(song_id: str) -> str | None:
    path = _user_path(song_id)
    return path.read_text(encoding="utf-8") if path.is_file() else None


def delete_user(song_id: str) -> bool:
    path = _user_path(song_id)
    existed = path.is_file()
    path.unlink(missing_ok=True)
    return existed


def current_text(song_id: str) -> str:
    """Text to show in the editor: the saved/pasted text, else the lines on screen now."""
    if (text := load_user(song_id)) is not None:
        return text
    try:
        segments = json.loads(cache_manager.song_file(song_id, LYRICS_FILE).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return ""
    return "\n".join(seg["text"] for seg in segments)
