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

from core import cache_manager, sources_registry
from services.metadata_tags import build_tags, compute_decade, detect_language, normalize_genre
from services.song_names import build_query, clean_channel

log = logging.getLogger(__name__)

ITUNES_URL = "https://itunes.apple.com/search"
HEADERS = {"User-Agent": "ai-karaoke/1.0 (local party app)"}
TIMEOUT = 4.0

_YEAR_RE = re.compile(r"\b(19\d\d|20\d\d)\b")
_DASH_SPLIT = re.compile(r"\s+[-–—]\s+")


def _query_itunes(term: str) -> dict | None:
    if not sources_registry.enabled("itunes"):   # Settings › Sources: local guesses only
        return None
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

    tags = build_tags(genre, decade, lang, year, raw_title)

    enriched = {
        "artist": artist,
        "clean_title": title,
        "genre": genre,
        "genres": [genre],
        "year": year,
        "decade": decade,
        "language": lang,
        "tags": tags,
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
