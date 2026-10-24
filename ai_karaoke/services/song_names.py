"""Song-name cleanup shared by the lyrics lookup and the search: one set of noise rules.

The lyrics search (build_query) and the search de-duplication (song_key) must agree on what
"the same song" is, so the noise words and channel suffixes live here once.
"""
import re

TITLE_NOISE = re.compile(r"\([^)]*\)|\[[^\]]*\]|\|.*$|\b(official|music|video|lyrics?|audio|hd|4k|mv|"
                         r"karaoke|remaster(ed)?|visualizer|live)\b", re.IGNORECASE)
_CHANNEL_SUFFIX = re.compile(r"\s*-\s*Topic$|VEVO$")
# Extra rules for comparing names only (never used for the lyrics query, which stays as it was)
_DASHES = re.compile(r"\s+[‐‑‒–—―−]\s+")   # every dash look-alike separates artist and title
_TRAILING_REMASTER = re.compile(r"\s+-\s+(\d{4}\s+)?(digital(ly)?\s+)?remaster(ed)?\b.*$", re.IGNORECASE)
_FEAT = re.compile(r"\b(feat|ft|featuring)\b\.?[^-()\[\]]*", re.IGNORECASE)
_KEY_NOISE = re.compile(r"\b(official|topic|vevo|remaster(ed)?)\b", re.IGNORECASE)
_PUNCT = re.compile(r"[^\w\s]|_")
# A karaoke, live or remixed take is different audio: never merge it with the original song
_VARIANT = re.compile(r"\b(karaoke|instrumental|live|cover|remix|acoustic|slowed|sped[ -]?up|nightcore|"
                      r"8d|reverb|bass ?boosted|unplugged|demo|piano version|backing track)\b", re.IGNORECASE)
_OFFICIAL_CHANNEL = re.compile(r"-\s*Topic$|VEVO$|\bofficial\b", re.IGNORECASE)


def clean_channel(name: str) -> str:
    """"Oasis - Topic" / "OasisVEVO" -> "Oasis"."""
    return _CHANNEL_SUFFIX.sub("", name or "").strip()


def build_query(title: str, channel: str = "") -> str:
    """Lyrics search text: the title without video noise, prefixed by the channel when the
    title doesn't already say "Artist - Title"."""
    clean = re.sub(r"\s{2,}", " ", TITLE_NOISE.sub(" ", title or "")).strip(" -–_")
    return clean if " - " in clean or not channel else f"{channel} {clean}"


def _words(text: str) -> set[str]:
    return set(_PUNCT.sub(" ", _KEY_NOISE.sub(" ", text).lower()).split())


def song_key(title: str, channel: str = "") -> str:
    """Normalised artist + title, the same for every upload of one recording.

    Word order and punctuation are ignored ("Du Hast - Rammstein" == "Rammstein: Du hast"),
    so are "(Official Video)", "[Lyrics]", "Remastered", "feat. X", "Topic" and "VEVO".
    Variant markers (live, karaoke, remix...) are kept apart after a "|".
    """
    title = _DASHES.sub(" - ", title or "")
    variants = sorted({m.group(0).lower() for m in _VARIANT.finditer(title)})
    title = _FEAT.sub(" ", _TRAILING_REMASTER.sub("", title))
    words = _words(build_query(title, clean_channel(channel)))
    return " ".join(sorted(words)) + (f"|{','.join(variants)}" if variants else "")


def same_song(a: dict, b: dict) -> bool:
    """Keys match, or one upload's key matches the other's title-only key. A bare title gets
    its channel as artist ("Wonderwall" by "Oasis" -> oasis wonderwall), which is right for an
    artist's own upload but adds a fan's channel name to "ABBA Dancing Queen" — its title-only
    key "abba dancing queen" still finds the official upload."""
    return a["key"] == b["key"] or a["key"] == b.get("title_key") or a.get("title_key") == b["key"]


def officialness(title: str, raw_channel: str) -> int:
    """2 = the artist's own upload (Topic / VEVO / "official" channel, or the channel is the
    artist named in the title), 1 = a bare title (usually the artist's channel), 0 = others."""
    if _OFFICIAL_CHANNEL.search(raw_channel or ""):
        return 2
    title = _DASHES.sub(" - ", title or "")
    if " - " not in title:
        return 1
    artist = _words(_FEAT.sub(" ", title.split(" - ", 1)[0]))   # "Dirty Palm feat. CRVN" is Dirty Palm's own
    channel = _words(clean_channel(raw_channel))
    return 2 if channel and channel == artist else 0
