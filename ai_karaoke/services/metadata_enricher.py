"""Song metadata enrichment: artist, clean title, genre, year, decade, language and tags.

Queries the iTunes Search API (free, fast, keyless) to accurately resolve release year,
clean artist/track names, and primary genre. Falls back to local regex and heuristic
parsing. Updates cache meta.json so the library and search UI can filter by genre,
decade, and mood.
"""
import logging
import re
import urllib.parse
import requests

from core import cache_manager
from services.song_names import build_query, clean_channel

log = logging.getLogger(__name__)

ITUNES_URL = "https://itunes.apple.com/search"
HEADERS = {"User-Agent": "ai-karaoke/1.0 (local party app)"}
TIMEOUT = 4.0

_YEAR_RE = re.compile(r"\b(19\d\d|20\d\d)\b")
_DASH_SPLIT = re.compile(r"\s+[-–—]\s+")

GENRE_MAP = {
    "rock": "Rock",
    "classic rock": "Rock",
    "hard rock": "Rock",
    "punk rock": "Rock",
    "alternative rock": "Rock",
    "rock & roll": "Rock",
    "indie rock": "Indie",
    "indie pop": "Indie",
    "indie": "Indie",
    "alternative": "Indie",
    "pop": "Pop",
    "teen pop": "Pop",
    "dance-pop": "Pop",
    "electropop": "Pop",
    "synth-pop": "Pop",
    "adult contemporary": "Pop",
    "mandopop": "Pop",
    "cantopop": "Pop",
    "k-pop": "Pop",
    "j-pop": "Pop",
    "dance": "Dance / Electronic",
    "electronic": "Dance / Electronic",
    "house": "Dance / Electronic",
    "techno": "Dance / Electronic",
    "disco": "Dance / Electronic",
    "edm": "Dance / Electronic",
    "hip-hop/rap": "Hip-Hop",
    "hip-hop": "Hip-Hop",
    "rap": "Hip-Hop",
    "trap": "Hip-Hop",
    "r&b/soul": "R&B / Soul",
    "r&b": "R&B / Soul",
    "soul": "R&B / Soul",
    "funk": "R&B / Soul",
    "heavy metal": "Metal",
    "metal": "Metal",
    "soundtrack": "Soundtrack",
    "musicals": "Soundtrack",
    "anime": "Soundtrack",
    "singer/songwriter": "Acoustic / Ballads",
    "country": "Country",
    "latin": "Latin",
    "reggae": "Reggae",
}


def normalize_genre(raw_genre: str | None) -> str:
    if not raw_genre:
        return "Pop"
    cleaned = raw_genre.strip().lower()
    return GENRE_MAP.get(cleaned, raw_genre.title())


def compute_decade(year: int | None) -> str | None:
    if not year or year < 1920 or year > 2035:
        return None
    d = (year // 10) * 10
    if d >= 2000:
        return f"{d}s"
    return f"{d % 100}s"


def detect_language(text: str) -> str:
    if any("\u0400" <= ch <= "\u04ff" for ch in text):
        return "ru"
    if any("\u4e00" <= ch <= "\u9fff" or "\u3040" <= ch <= "\u30ff" for ch in text):
        return "ja"
    if any("\uac00" <= ch <= "\ud7af" for ch in text):
        return "ko"
    if any("\u00e0" <= ch <= "\u00ff" or "\u0153" <= ch <= "\u0153" for ch in text):
        return "fr"
    return "en"


def _query_itunes(term: str) -> dict | None:
    try:
        url = f"{ITUNES_URL}?term={urllib.parse.quote(term)}&entity=song&limit=1"
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code == 200:
            results = r.json().get("results", [])
            if results:
                hit = results[0]
                year = int(hit["releaseDate"][:4]) if "releaseDate" in hit else None
                return {
                    "artist": hit.get("artistName"),
                    "title": hit.get("trackName"),
                    "genre": hit.get("primaryGenreName"),
                    "year": year,
                }
    except Exception as exc:
        log.debug("iTunes search failed for %r: %s", term, exc)
    return None


def enrich_metadata(song_id: str, raw_title: str, channel: str = "", save: bool = True) -> dict:
    """Enrich a song's metadata with artist, title, year, decade, genre, and tags."""
    channel_clean = clean_channel(channel)
    q = build_query(raw_title, channel_clean)

    # 1. Try iTunes search with cleaned query, then fallback to artist+title split
    hit = _query_itunes(q)
    if not hit and _DASH_SPLIT.search(raw_title):
        parts = _DASH_SPLIT.split(raw_title, 1)
        artist_part = parts[0].strip()
        title_part = re.sub(r"\([^)]*\)|\[[^\]]*\]|\|.*$", "", parts[1]).strip()
        hit = _query_itunes(f"{artist_part} {title_part}")

    if hit:
        artist = hit.get("artist") or channel_clean
        title = hit.get("title") or raw_title
        genre = normalize_genre(hit.get("genre"))
        year = hit.get("year")
    else:
        # Fallback: parse from raw title / channel
        if _DASH_SPLIT.search(raw_title):
            parts = _DASH_SPLIT.split(raw_title, 1)
            artist = parts[0].strip()
            title = re.sub(r"\([^)]*\)|\[[^\]]*\]|\|.*$", "", parts[1]).strip()
        else:
            artist = channel_clean or "Unknown Artist"
            title = re.sub(r"\([^)]*\)|\[[^\]]*\]|\|.*$", "", raw_title).strip()

        # Try to find year in title
        year_match = _YEAR_RE.search(raw_title)
        year = int(year_match.group(1)) if year_match else None

        # Heuristic genre keywords
        lower = (raw_title + " " + channel).lower()
        if any(w in lower for w in ("rap", "рэп", "hip hop", "hip-hop")):
            genre = "Hip-Hop"
        elif any(w in lower for w in ("rock", "рок", "metal", "метал")):
            genre = "Rock"
        elif any(w in lower for w in ("house", "edm", "dance", "remix", "club")):
            genre = "Dance / Electronic"
        else:
            genre = "Pop"

    decade = compute_decade(year)
    lang = detect_language(f"{artist} {title} {raw_title}")

    # Build search/filter tags
    tags = set()
    if genre:
        tags.add(genre.lower())
        for g_part in genre.lower().split("/"):
            tags.add(g_part.strip())
    if decade:
        tags.add(decade.lower())
    if lang:
        tags.add(lang.lower())
        if lang == "ru":
            tags.add("russian")
            tags.add("русское")
            if genre in ("Rock", "Indie"):
                tags.add("russian rock")
                tags.add("русский рок")

    if year and year <= 1999:
        tags.add("classic")
        tags.add("retro")

    lower_full = raw_title.lower()
    if "feat" in lower_full or "ft." in lower_full:
        tags.add("duet")

    enriched = {
        "artist": artist,
        "clean_title": title,
        "genre": genre,
        "genres": [genre],
        "year": year,
        "decade": decade,
        "language": lang,
        "tags": sorted(tags),
    }

    if save:
        cache_manager.update_meta(song_id, **enriched)
        log.info("Enriched %s: %s - %s [%s, %s]", song_id, artist, title, genre, decade or "?")

    return enriched


def migrate_all() -> dict:
    """Migrate all cached songs, populating metadata tags."""
    songs = cache_manager.list_songs()
    enriched_count = 0
    genres_count: dict[str, int] = {}
    decades_count: dict[str, int] = {}

    for s in songs:
        song_id = s.get("id")
        if not song_id:
            continue
        res = enrich_metadata(song_id, s.get("title", ""), s.get("channel", ""), save=True)
        enriched_count += 1
        g = res.get("genre", "Unknown")
        genres_count[g] = genres_count.get(g, 0) + 1
        d = res.get("decade") or "Unknown"
        decades_count[d] = decades_count.get(d, 0) + 1

    return {
        "total": len(songs),
        "enriched": enriched_count,
        "genres": dict(sorted(genres_count.items(), key=lambda x: x[1], reverse=True)),
        "decades": dict(sorted(decades_count.items(), key=lambda x: x[1], reverse=True)),
    }
