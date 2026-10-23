"""Battle / Duet: a second guest joins someone's battle song as the singer on mic 2.

- Joining needs a guest login, and only works on another guest's song whose mode is
  "battle" and that has no partner yet (409 otherwise): first come, first sings. A song
  that already plays can still be joined while its intro card counts down, not after.
- Leaving (freeing mic 2): the partner themselves, the song's owner, or the host.
- A partner never manages the entry: removing, moving and tuning stay with the owner and
  the host (routers/queue.py checks auth.may_manage, which ignores partners).
"""
from fastapi import APIRouter, HTTPException, Request

from core import auth
from core.queue_manager import queue

router = APIRouter(prefix="/api/queue")


def _found(uid: str) -> dict:
    entry = queue.find_any(uid)
    if entry is None:
        raise HTTPException(404, "Queue entry not found")
    return entry


@router.post("/{uid}/join")
async def join_battle(uid: str, request: Request):
    who, entry = auth.identify(request), _found(uid)
    if who.guest_id is None:
        raise HTTPException(401, "Log in with your name on the remote page first")
    if auth.owns(who, entry):
        raise HTTPException(409, "That's your own song — a friend has to join you")
    if entry.get("mode") != "battle":
        raise HTTPException(409, "Only Battle / Duet songs take a second singer")
    if entry.get("partner"):
        raise HTTPException(409, f"{entry['partner']['name']} already joined this song")
    if queue.current is entry and not queue.in_intro(uid):
        raise HTTPException(409, "This song has already started")
    return await queue.set_partner(uid, {"id": who.guest_id, "name": who.name})


@router.delete("/{uid}/partner")
async def leave_battle(uid: str, request: Request):
    who, entry = auth.identify(request), _found(uid)
    partner = entry.get("partner") or {}
    is_partner = who.guest_id is not None and partner.get("id") == who.guest_id
    if not (is_partner or auth.may_manage(who, entry)):
        raise HTTPException(403, "Only the second singer, the song's owner or the host can do that")
    return await queue.set_partner(uid, None)
