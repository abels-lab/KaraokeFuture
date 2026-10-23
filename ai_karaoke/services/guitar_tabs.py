"""Fallback lyric source from guitar chord & tab sites (Ultimate Guitar, AmDm.ru).

When synced lyrics (LRCLIB, Musixmatch, NetEase) and Genius have no lyrics for a song,
guitar sites often have community-submitted chord sheets that contain the full lyrics.
Because Ultimate Guitar embeds its frontend store as structured JSON, we extract the
raw wiki text without DOM scraping, strip chord markup ([ch]...[/ch], chord lines, tab
diagrams), and pass the clean lyrics to forced alignment (MMS / stable-ts).
"""
import html
import json
import logging
import re
import urllib.parse
import requests

from core import settings

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}
TIMEOUT = 7.0

_JS_STORE = re.compile(r'class="js-store"\s+data-content="([^"]+)"')
_CHORD_TAG = re.compile(r"\[ch\][^\[]*?\[/ch\]", re.IGNORECASE)
_TAB_TAG = re.compile(r"\[/?(?:tab|toptab|headline|closetab)\]", re.IGNORECASE)
_FRET_DIAGRAM = re.compile(r"^[A-H][b#]?[a-z0-9]*\s+[\dxX\s-]{5,}$")
_TAB_STAFF = re.compile(r"^[eBGDAE]\s*\|")
_CHART_META = re.compile(r"^(tuning|capo|strumming|bpm|key|tempo|tone)\s*[:=]", re.IGNORECASE)
_CHORD_TOKEN = re.compile(r"^[A-H][b#]?(?:m|maj|min|dim|aug|sus|add)?[0-9]*(?:/[A-H][b#]?)?$", re.IGNORECASE)


def _is_chord_or_noise(line: str) -> bool:
    """True if line contains guitar fret diagrams, tuning info, tab staves, or only chord names."""
    trimmed = line.strip()
    if not trimmed:
        return True
    if _FRET_DIAGRAM.match(trimmed) or _TAB_STAFF.match(trimmed) or _CHART_META.match(trimmed):
        return True
    # Tab staff or divider lines: mostly ASCII dashes/pipes/slashes
    if len(trimmed) >= 5 and sum(ch in "-|~/\\x*=_" for ch in trimmed) / len(trimmed) > 0.4:
        return True
    # Lines where every word is a chord symbol (e.g. "Em D C G" or "Am7/G Dsus4 Cmaj7")
    tokens = [t.strip(".,;:()[]{}|/\\-") for t in trimmed.split() if t.strip(".,;:()[]{}|/\\-")]
    if tokens and all(_CHORD_TOKEN.match(t) for t in tokens):
        return True
    return False


def _clean_ug_content(raw: str) -> str:
    """Strip [ch]...[/ch] tags, tab wrappers, chord fret diagrams, and ASCII tab staves."""
    text = _CHORD_TAG.sub("", raw or "")
    text = _TAB_TAG.sub("", text)
    lines = []
    for line in text.splitlines():
        trimmed = line.strip()
        if not _is_chord_or_noise(trimmed):
            lines.append(trimmed)
    return "\n".join(lines)


def _score_ug_hit(query: str, hit: dict) -> float:
    q_tokens = set(re.findall(r"\w+", query.lower().replace("ё", "е")))
    artist_tokens = set(re.findall(r"\w+", (hit.get("artist_name") or "").lower().replace("ё", "е")))
    title_tokens = set(re.findall(r"\w+", (hit.get("song_name") or "").lower().replace("ё", "е")))

    if not artist_tokens or not title_tokens:
        return 0.0

    artist_overlap = len(artist_tokens & q_tokens) / len(artist_tokens)
    if artist_overlap < 0.5:
        return 0.0

    title_overlap = len(title_tokens & q_tokens) / len(title_tokens)
    if title_overlap < 0.5:
        return 0.0

    votes = int(hit.get("votes") or 0)
    is_chords = 1.0 if hit.get("type") == "Chords" else 0.5
    return (artist_overlap + title_overlap) * 10 + (1.0 if votes > 0 else 0.0) + is_chords


def _search_ug(search_term: str) -> list[dict]:
    url = f"https://www.ultimate-guitar.com/search.php?search_type=title&value={urllib.parse.quote(search_term)}"
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    if r.status_code != 200:
        return []
    m = _JS_STORE.search(r.text)
    if not m:
        return []
    data = json.loads(html.unescape(m.group(1)))
    results = data.get("store", {}).get("page", {}).get("data", {}).get("results", [])
    return [res for res in results if res.get("tab_url") and res.get("type") in ("Chords", "Tabs", "Ukulele Chords")]


def _fetch_ug_tab(tab_url: str) -> str | None:
    r = requests.get(tab_url, headers=HEADERS, timeout=TIMEOUT)
    if r.status_code != 200:
        return None
    m = _JS_STORE.search(r.text)
    if not m:
        return None
    data = json.loads(html.unescape(m.group(1)))
    wiki = data.get("store", {}).get("page", {}).get("data", {}).get("tab_view", {}).get("wiki_tab", {})
    return wiki.get("content")


def fetch_ultimate_guitar(query: str, title: str = "") -> str | None:
    for term in [query, title]:
        if not term:
            continue
        try:
            hits = _search_ug(term)
            scored = [(_score_ug_hit(query, h), h) for h in hits]
            scored = [s for s in scored if s[0] > 0]
            scored.sort(key=lambda s: s[0], reverse=True)
            if scored:
                best = scored[0][1]
                content = _fetch_ug_tab(best["tab_url"])
                if content:
                    cleaned = _clean_ug_content(content)
                    log.info("Ultimate Guitar: found %r (%s - %s)", term, best.get("artist_name"), best.get("song_name"))
                    return cleaned
        except Exception as exc:
            log.debug("Ultimate Guitar search failed for %r: %s", term, exc)
    return None


def fetch_amdm(query: str, title: str = "") -> str | None:
    """Fallback for Russian indie/rock songs: AmDm.ru."""
    if not any("\u0400" <= ch <= "\u04ff" for ch in query + title):
        return None

    for term in [query, title]:
        if not term:
            continue
        try:
            url = f"https://amdm.ru/search/?q={urllib.parse.quote(term)}"
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            if r.status_code != 200:
                continue
            links = re.findall(r'<a[^>]+href=["\'](/akkordi/[^"\']+)["\'][^>]*>([^<]+)</a>', r.text)
            q_tokens = set(re.findall(r"\w+", query.lower().replace("ё", "е")))
            best_link = None
            for link, text in links:
                t_tokens = set(re.findall(r"\w+", text.lower().replace("ё", "е")))
                if t_tokens and len(t_tokens & q_tokens) / len(t_tokens) >= 0.5:
                    best_link = link
                    break
            if not best_link:
                continue

            song_url = f"https://amdm.ru{best_link}" if best_link.startswith("/") else best_link
            r_song = requests.get(song_url, headers=HEADERS, timeout=TIMEOUT)
            if r_song.status_code != 200:
                continue
            pre = re.search(r'<pre[^>]*>(.*?)</pre>', r_song.text, re.DOTALL)
            if not pre:
                continue

            no_chords = re.sub(r'<div[^>]*class="podbor__chord"[^>]*>.*?</div>', '', pre.group(1))
            clean = re.sub(r'<[^>]+>', '', no_chords)
            lines = [l.strip() for l in clean.splitlines() if not _is_chord_or_noise(l)]
            log.info("AmDm: found %r via %s", term, song_url)
            return "\n".join(lines)
        except Exception as exc:
            log.debug("AmDm search failed for %r: %s", term, exc)
    return None


def fetch(query: str, title: str = "") -> str | None:
    """Fetch clean lyrics without chords from Ultimate Guitar or AmDm.ru. Never raises."""
    if not settings.get("use_chords_lyrics"):
        return None
    return fetch_ultimate_guitar(query, title) or fetch_amdm(query, title)
