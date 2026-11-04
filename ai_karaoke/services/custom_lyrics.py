"""Lyrics from the host's own links: a page URL template with {artist}, {title} or {query}.

e.g. https://www.example-lyrics.com/{artist_slug}/{title_slug}.html. The page is fetched with a
short time limit and a size cap, following at most a few redirects, each one checked against the
link rules (core/source_links.py: public http(s) hosts only, never this laptop or the LAN).
No browser is opened and no script on the page runs; services/page_text.py picks the lyrics.
Never raises from fetch(): a failing link just means "not found here".
"""
import logging
import urllib.parse

import requests

from core.source_links import LinkError, check_url, fill
from services import page_text

log = logging.getLogger(__name__)
TIMEOUT = (4, 8)            # connect, read (seconds)
MAX_BYTES = 2 * 1024 ** 2   # a lyrics page is far smaller; stop reading past this
MAX_REDIRECTS = 3
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ai-karaoke/1.0",
           "Accept": "text/html,text/plain;q=0.9,*/*;q=0.1"}


def split_query(query: str, channel: str = "") -> tuple[str, str]:
    """("Oasis", "Wonderwall") from "Oasis - Wonderwall", else (channel, query)."""
    artist, sep, title = query.partition(" - ")
    return (artist.strip(), title.strip()) if sep else (channel.strip(), query.strip())


def get_page(url: str) -> tuple[str, bool]:
    """(text, is_html) of a public page. Raises LinkError / requests errors / ValueError."""
    with requests.Session() as session:
        for _ in range(MAX_REDIRECTS + 1):
            check_url(url)
            with session.get(url, headers=HEADERS, timeout=TIMEOUT, stream=True, allow_redirects=False) as r:
                if r.is_redirect:
                    url = urllib.parse.urljoin(url, r.headers.get("location", ""))
                    continue
                r.raise_for_status()
                kind = r.headers.get("content-type", "text/html").lower()
                if not kind.startswith(("text/html", "text/plain", "application/xhtml")):
                    raise ValueError(f"not a web page ({kind.split(';')[0]})")
                body = b""
                for chunk in r.iter_content(64 * 1024):
                    body += chunk
                    if len(body) > MAX_BYTES:
                        raise ValueError("page too large")
                return body.decode(r.encoding if "charset" in kind else "utf-8", errors="replace"), "plain" not in kind
    raise ValueError("too many redirects")


def fetch(link: dict, query: str, channel: str = "") -> str | None:
    """Lyric text found through one custom link, or None."""
    artist, title = split_query(query, channel)
    url = fill(link["template"], artist=artist, title=title, query=query)
    try:
        page, is_html = get_page(url)
    except (LinkError, requests.RequestException, ValueError) as exc:
        log.info("Lyrics link %s skipped for %r: %s", link["name"], query, exc)
        return None
    found = page_text.lyrics(page, title or query, is_html)
    log.info("Lyrics link %s: %s for %r", link["name"], f"{found.count(chr(10)) + 1} lines" if found else "nothing", query)
    return found
