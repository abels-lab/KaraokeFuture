"""UltraStar txt files: parse, sanity-check and convert to lyrics.json / melody notes.

Format: "#KEY:value" headers, then one line per syllable ": start length pitch text"
(":" normal, "*" golden, "F" freestyle, "R"/"G" rap), "- start" line breaks, "P1"/"P2"
duet parts and "E" at the end. Beats become seconds as GAP/1000 + beat * 60 / (BPM * 4);
pitch 0 is middle C (MIDI 60). A syllable starting with a space begins a new word; "~"
continues the previous syllable (a melisma).
"""
import re

from core import settings

_NOTE = re.compile(r"^([:*FRG])\s+(-?\d+)\s+(\d+)\s+(-?\d+)\s?(.*)$")
_YOUTUBE = re.compile(r"(?:^|[,\s])(?:v|a)=([A-Za-z0-9_-]{11})(?:[,\s]|$)")
MIN_NOTES = 20


def _number(value: str) -> float:
    return float(value.strip().replace(",", "."))


def parse(text: str) -> dict:
    """{"headers": {KEY: value}, "players": {"P1": [lines]}} where a line is a list of syllables
    {"beat", "length", "pitch", "text", "kind"}. Raises ValueError for unreadable files."""
    headers, players, player, line = {}, {}, "P1", None
    for raw in (text or "").replace("﻿", "").splitlines():
        if raw.startswith("#"):
            key, _, value = raw[1:].partition(":")
            headers[key.strip().upper()] = value.strip()
            continue
        stripped = raw.strip()
        if stripped in ("P1", "P2", "P3"):
            player, line = stripped, None
        elif stripped.startswith("E"):
            break
        elif stripped.startswith("-"):
            line = None
        elif match := _NOTE.match(raw.rstrip("\r")):
            kind, beat, length, pitch, syllable = match.groups()
            if line is None:
                line = []
                players.setdefault(player, []).append(line)
            line.append({"beat": int(beat), "length": int(length), "pitch": int(pitch), "text": syllable, "kind": kind})
    return {"headers": headers, "players": players}


def video_ids(song: dict) -> set[str]:
    """YouTube ids the file was timed to (#VIDEO meta-tags "v=" / "a=", or a plain URL)."""
    video = song["headers"].get("VIDEO", "")
    found = set(_YOUTUBE.findall(video))
    found.update(re.findall(r"(?:youtu\.be/|watch\?v=)([A-Za-z0-9_-]{11})", video))
    return found


def seconds(song: dict, beat: float) -> float:
    h = song["headers"]
    return _number(h.get("GAP", "0")) / 1000 + beat * 60 / (_number(h["BPM"]) * 4)


def span(song: dict) -> tuple[float, float]:
    syllables = [s for lines in song["players"].values() for line in lines for s in line]
    return (seconds(song, min(s["beat"] for s in syllables)),
            seconds(song, max(s["beat"] + s["length"] for s in syllables)))


def problems(song: dict, duration: float | None = None) -> list[str]:
    """Why this file can't be used as is ([] = fine). Timing vs our audio is checked later."""
    h, issues = song["headers"], []
    for key in ("TITLE", "ARTIST", "BPM"):
        if not h.get(key):
            issues.append(f"missing #{key}")
    try:
        if _number(h.get("BPM", "0")) <= 0:
            issues.append("BPM not positive")
    except ValueError:
        issues.append("unreadable BPM")
    if h.get("RELATIVE", "").lower() in ("yes", "true", "1"):
        issues.append("relative timing not supported")
    lines = [line for lines in song["players"].values() for line in lines]
    notes = sum(len(line) for line in lines)
    if notes < MIN_NOTES or len(lines) < settings.get("min_lyric_lines"):
        issues.append(f"too short ({len(lines)} lines, {notes} notes)")
    for part in song["players"].values():  # a slip or two is common and harmless, a mess is not
        beats = [s["beat"] for line in part for s in line]
        if sum(b < a for a, b in zip(beats, beats[1:])) > 0.02 * max(len(beats), 1):
            issues.append("notes out of order")
            break
    if not issues and duration:
        first, last = span(song)
        if last - first > duration + 1:
            issues.append(f"sung part ({last - first:.0f} s) longer than our audio ({duration:.0f} s)")
    return issues


def to_lyrics(song: dict, offset: float = 0.0) -> list[dict]:
    """lyrics.json lines; duets add "singer": "P1"/"P2"/"both" (a line both parts sing once)."""
    out = []
    for player, lines in song["players"].items():
        for line in lines:
            words, previous = [], " "
            for s in line:
                start = round(seconds(song, s["beat"]) + offset, 3)
                end = round(seconds(song, s["beat"] + s["length"]) + offset, 3)
                text = s["text"]
                melisma = text.strip().startswith("~")
                if words and (melisma or not (text.startswith(" ") or previous.endswith(" "))):
                    words[-1]["word"] += text.strip().lstrip("~")  # next syllable of the same word
                    words[-1]["end"] = end
                elif text.strip():
                    words.append({"word": (" " if words else "") + text.strip(), "start": start, "end": end})
                previous = text
            if words:
                out.append({"start": words[0]["start"], "end": words[-1]["end"], "singer": player,
                            "text": "".join(w["word"] for w in words).strip(), "words": words})
    out.sort(key=lambda s: s["start"])
    merged = []  # a line both duet parts sing at the same time is shown once
    for seg in out:
        twin = next((m for m in merged[-3:] if m["text"] == seg["text"] and m["singer"] != seg["singer"]
                     and abs(m["start"] - seg["start"]) < 0.3), None)
        if twin:
            twin["singer"] = "both"
        else:
            merged.append(seg)
    if len(song["players"]) == 1:
        for seg in merged:
            seg.pop("singer")
    return merged


def to_notes(song: dict, offset: float = 0.0) -> list[dict]:
    """Pitched notes for the singing game (freestyle and rap syllables have no pitch to score)."""
    notes = []
    for player, lines in song["players"].items():
        for line in lines:
            for s in line:
                if s["kind"] in ("F", "R", "G") or s["length"] <= 0:
                    continue
                notes.append({"start": round(seconds(song, s["beat"]) + offset, 2),
                              "end": round(seconds(song, s["beat"] + s["length"]) + offset, 2),
                              "midi": 60 + s["pitch"], "golden": s["kind"] == "*", "singer": player})
    return sorted(notes, key=lambda n: n["start"])
