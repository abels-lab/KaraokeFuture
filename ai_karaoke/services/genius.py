"""Genius as the last online lyrics TEXT source: plain text, no timestamps.

Needs a free API token in GENIUS_ACCESS_TOKEN (see config.GENIUS_TOKEN); skipped without one.
Only a hit whose artist AND title both match the query is used: wrong-song lyrics are worse
than none (Genius also lists translation pages such as "Genius Türkçe Çeviriler").
"""
import difflib
import logging
import re
import unicodedata

from config import GENIUS_TOKEN

log = logging.getLogger(__name__)

# Page chrome that the scraper can leave in the text, often glued onto a sung line
_EMBED = re.compile(r"(\d+(\.\d+)?K?)?\s*Embed\s*$")  # "...last line123Embed", "1.2KEmbed"
_ADS = re.compile(r"You might also like|See [^\n]{1,80}? Live(Get tickets as low as \$[\d.]+)?")
_HEADER = re.compile(r"^(\d+\s*Contributors?\b.*|Translations\b.*|.*\bLyrics)$", re.IGNORECASE)
_TITLE_EXTRA = re.compile(r"\([^)]*\)|\[[^\]]*\]|\s(ft|feat|featuring)\.?\s.*$", re.IGNORECASE)
_skip_logged = False


def clean(raw: str) -> str:
    """Genius page text -> lyric lines. Section headers like [Chorus] are left for
    lyrics_source.parse_lines, which drops bracket tags and section labels."""
    text = _EMBED.sub("", _ADS.sub("\n", raw or ""))
    lines = text.splitlines()
    while lines and (not lines[0].strip() or _HEADER.match(lines[0].strip())):
        lines.pop(0)  # "123 Contributors", "Translations", "Wonderwall Lyrics"
    return "\n".join(lines).strip()


# Russian -> Latin, so YouTube's "Vintazh" matches Genius's "Винтаж (Vintage)"
_CYR = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя", "a b v g d e e zh z i y k l m n o p r s t u f kh ts ch sh "
                "shch _ y _ e yu ya".split()))


def _tokens(text: str) -> list[str]:
    text = re.sub(r"['’`]", "", (text or "").lower().replace("&", " and "))
    text = unicodedata.normalize("NFKD", "".join(_CYR.get(ch, ch).strip("_") for ch in text))
    return re.findall(r"\w+", "".join(ch for ch in text if not unicodedata.combining(ch)))


def _has(word: str, query: set[str]) -> bool:
    """Exact, or a close spelling of a longer word (kh/h, yu/iu transliterations)."""
    return word in query or len(word) >= 4 and any(
        difflib.SequenceMatcher(None, word, q).ratio() >= 0.8 for q in query if len(q) >= 4)


def _covered(part: str, query: set[str], share: float) -> bool:
    words = _tokens(part)
    return bool(words) and sum(_has(w, query) for w in words) / len(words) >= share


def matches(query: str, song: dict) -> bool:
    """Every title word (minus "(Remastered)", "ft. X") and most of the artist's name
    must appear in the query, e.g. "Bubble Guppies Cast" for "Bubble guppies - ...".
    Genius artists may carry an alias in brackets, "Винтаж (Vintage)": either name counts."""
    words = set(_tokens(query))
    artist = (song.get("primary_artist") or {}).get("name", "")
    names = [re.sub(r"\([^)]*\)", "", artist)] + re.findall(r"\(([^)]*)\)", artist)
    return (_covered(_TITLE_EXTRA.sub("", song.get("title", "")), words, 1.0)
            and any(_covered(name, words, 0.6) for name in names))


def _find(genius, query: str, search: str) -> dict | None:
    hits = genius.search_songs(search, per_page=20)["hits"]
    return next((h["result"] for h in hits if h.get("type") == "song" and matches(query, h["result"])
                 and h["result"].get("lyrics_state") == "complete"
                 and not h["result"].get("instrumental")), None)


def fetch(query: str, title: str = "") -> str | None:
    """Plain lyrics for the best matching Genius song, or None. Never raises.
    `title` (cleaned video title) is searched alone when the full query finds no match:
    Genius search often misses mixed or transliterated queries like "Vintazh Спичка"."""
    global _skip_logged
    if not GENIUS_TOKEN:
        if not _skip_logged:
            log.info("GENIUS_ACCESS_TOKEN not set: skipping Genius lyrics")
            _skip_logged = True
        return None
    try:
        from lyricsgenius import Genius

        genius = Genius(GENIUS_TOKEN, timeout=10, retries=1, verbose=False)
        alone = title.split(" - ", 1)[-1].strip()  # "Oasis - Wonderwall" -> "Wonderwall"
        song = _find(genius, query, query)
        if song is None and alone and alone.lower() != query.lower():
            song = _find(genius, query, alone)
        if song is None:
            log.info("Genius: no confident match for %r", query)
            return None
        raw = genius.lyrics(song_url=song["url"])
    except Exception as exc:  # 401/403, Cloudflare pages, timeouts: never block the pipeline
        log.warning("Genius failed for %r: %s", query, exc)
        return None
    log.info("Genius: using %r by %s", song.get("title"), song.get("artist_names"))
    return clean(raw) if raw else None
