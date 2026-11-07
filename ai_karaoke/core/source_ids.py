"""Song ids for uploads found through the host's own song links (Settings › Sources).

YouTube and SoundCloud ids encode their page, but an upload on any other yt-dlp site needs a
stable short id that is safe as a cache folder name and URL part: "x_" + 16 hex characters of
the page URL's hash (18 characters, never a YouTube or "sc_" id). The id → page URL map lives in
DATA_DIR/source_ids.json (newest kept, oldest dropped past MAX_IDS); once a song is downloaded
its meta.json also keeps the URL, so a cached song never loses its page.
"""
import hashlib
import json
import logging
import os
import re
import threading

from config import DATA_DIR

log = logging.getLogger(__name__)
ID_FILE = DATA_DIR / "source_ids.json"
MAX_IDS = 3000
PATTERN = re.compile(r"^[xu]_[0-9a-f]{16}$")
_lock = threading.Lock()
_ids: dict[str, str] | None = None


def _map() -> dict[str, str]:
    global _ids
    if _ids is None:
        try:
            raw = json.loads(ID_FILE.read_text(encoding="utf-8"))
            _ids = {k: v for k, v in raw.items() if PATTERN.match(k) and isinstance(v, str)} if isinstance(raw, dict) else {}
        except FileNotFoundError:
            _ids = {}
        except (OSError, ValueError) as exc:
            log.warning("%s is unreadable (%s): starting a new one", ID_FILE.name, exc)
            _ids = {}
    return _ids


def make_id(url: str) -> str:
    return "x_" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


def make_upload_id(seed: str | bytes) -> str:
    raw = seed if isinstance(seed, bytes) else seed.encode("utf-8")
    return "u_" + hashlib.sha1(raw).hexdigest()[:16]


def remember(urls: list[str]) -> list[str]:
    """Ids for these page URLs, stored so a later download can find the page again."""
    with _lock:
        ids = _map()
        out = []
        for url in urls:
            sid = make_id(url)
            ids.pop(sid, None)
            ids[sid] = url   # re-inserted: newest last
            out.append(sid)
        for old in list(ids)[:max(0, len(ids) - MAX_IDS)]:
            del ids[old]
        tmp = ID_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(ids, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, ID_FILE)
    return out


def url_for(song_id: str) -> str | None:
    with _lock:
        url = _map().get(song_id)
    if url:
        return url
    from core import cache_manager   # late: cache_manager pulls in much of core
    meta = cache_manager.read_meta(song_id)
    return meta.get("source_url") if meta.get("source_id") in (None, song_id) else None


def reload() -> None:
    global _ids
    with _lock:
        _ids = None
