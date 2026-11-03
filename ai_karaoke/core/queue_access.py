"""Who sings a new queue entry, queueing it within the limits, and who may change an entry.

Shared by routers/queue.py, routers/playlists.py and the DJ Co-Pilot (services/agent/tools_party.py),
so a song queued by chat follows the same rules as one queued from the remote.
"""
from fastapi import HTTPException, Request

from config import MELODY_FILE
from core import auth, cache_manager, settings
from core.queue_manager import queue
from core.worker import worker


def singer_for(who: auth.Who, wanted: str) -> tuple[str, int | None]:
    """(singer name, owner guest id) for a new entry."""
    wanted = " ".join(wanted.split())
    if who.admin and wanted and (who.name is None or wanted.casefold() != who.name.casefold()):
        return wanted, None   # the host queues for someone without a login
    if who.guest_id is not None:
        return who.name, who.guest_id
    if who.admin:
        raise HTTPException(422, "Singer name is required")
    raise HTTPException(401, "Log in with your name on the remote page first")


def promote_singer(who: auth.Who, wanted: str | None) -> tuple[str, int | None]:
    """(singer name, owner guest id) for a song promoted from the active playlist."""
    if who.guest_id is not None:
        return who.name, who.guest_id
    if who.admin:
        return (wanted.strip() if wanted and wanted.strip() else "Host"), None
    raise HTTPException(401, "Please log in on remote to add songs")


async def enqueue(song_id: str, title: str, channel: str, duration, singer: str, owner: int | None,
                  guide: int | None = None, mode: str | None = None, thumbnail: str | None = None) -> dict:
    if len(queue.entries) >= settings.get("max_queue"):
        raise HTTPException(429, "The queue is full — try again later")
    entry = await queue.add(song_id, title, channel, duration, singer, thumbnail, owner, guide, mode)
    await worker.submit(song_id)
    if cache_manager.is_ready(song_id) and not cache_manager.song_file(song_id, MELODY_FILE).is_file():
        await worker.submit_melody(song_id)  # cached before the singing game existed
    return entry


def entry_for(request: Request, uid: str) -> tuple[auth.Who, dict]:
    who, entry = auth.identify(request), queue.find_any(uid)
    if entry is None:
        raise HTTPException(404, "Queue entry not found")
    if not auth.may_manage(who, entry):
        raise HTTPException(403, "That's someone else's song — only they or the host can change it")
    return who, entry
