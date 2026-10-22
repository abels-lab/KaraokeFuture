"""Minimal client for USDB (usdb.animux.de), the community UltraStar database.

USDB has no public API and needs a (free) account even to search, so this logs in with the
owner's credentials from the environment (USDB_USER / USDB_PASSWORD) and reads the same
pages a browser does: the song list and the txt download. Requests are few and spaced out.
Every failure (no account, site down, layout change) returns empty results: the karaoke
pipeline then times the lyrics itself, as before.
"""
import html
import logging
import os
import re
import threading
import time

import requests

log = logging.getLogger(__name__)

BASE = "https://usdb.animux.de/"
NOT_LOGGED_IN = "You are not logged in"
MIN_INTERVAL = 1.0          # seconds between requests: be a polite guest on a community site
MAX_RESULTS = 25
_ROW = re.compile(r'<tr class="list_tr\d"[^>]*data-songid="(\d+)"')
_TEXTAREA = re.compile(r"<textarea[^>]*>(.*?)</textarea>", re.DOTALL | re.IGNORECASE)

_session: requests.Session | None = None
_lock = threading.Lock()
_last = 0.0


def configured() -> bool:
    return bool(os.getenv("USDB_USER") and os.getenv("USDB_PASSWORD"))


def _request(method: str, params: dict, data: dict | None = None) -> str:
    global _last
    wait = MIN_INTERVAL - (time.monotonic() - _last)
    if wait > 0:
        time.sleep(wait)
    _last = time.monotonic()
    response = _session.request(method, BASE + "index.php", params=params, data=data, timeout=15,
                                headers={"User-Agent": "ai-karaoke (private party app)"})
    response.raise_for_status()
    response.encoding = "utf-8"
    return response.text


def _login() -> bool:
    global _session
    _session = requests.Session()
    response = _session.post(BASE, data={"user": os.environ["USDB_USER"], "pass": os.environ["USDB_PASSWORD"],
                                         "login": "Login"}, timeout=15)
    response.encoding = "utf-8"
    profile = _request("GET", {"link": "profil"})
    if NOT_LOGGED_IN in profile or "Please login" in profile:
        log.warning("USDB login failed: check USDB_USER / USDB_PASSWORD")
        _session = None
        return False
    log.info("Logged in to USDB")
    return True


def _page(method: str, params: dict, data: dict | None = None) -> str | None:
    """A page as a logged-in user (one re-login if the session expired), or None."""
    if not configured():
        return None
    with _lock:
        try:
            for attempt in range(2):
                if _session is None and not _login():
                    return None
                text = _request(method, params, data)
                if NOT_LOGGED_IN not in text:
                    return text
                _session_reset()
        except requests.RequestException as exc:
            log.warning("USDB request failed: %s", exc)
            _session_reset()
    return None


def _session_reset() -> None:
    global _session
    _session = None


def search(artist: str, title: str) -> list[int]:
    """USDB song ids for an artist/title search (newest first), [] when nothing or no access."""
    text = _page("POST", {"link": "list"}, {"interpret": artist, "title": title, "order": "id", "ud": "desc",
                                             "limit": str(MAX_RESULTS), "details": "1", "start": "0"})
    return [int(i) for i in _ROW.findall(text or "")]


def fetch_txt(song_id: int) -> str | None:
    """The UltraStar txt of one USDB song, or None."""
    text = _page("POST", {"link": "gettxt", "id": str(song_id)}, {"wd": "1"})
    match = _TEXTAREA.search(text or "")
    return html.unescape(match.group(1)).replace("\r\n", "\n").strip() if match else None
