"""Party logins, the host PIN and the party wipe.

A guest types a name and a password on /remote: a new name is registered on the spot, a
known name needs its password. The session token travels in an HttpOnly, SameSite=Lax
cookie (page scripts can't read it, other sites can't send it along with their forms).
Everything runs over plain HTTP on the home network, so the page tells guests not to reuse
a real password. Wrong passwords and PINs are rate-limited (core/passwords.py).
"""
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from core import auth, party_db, passwords
from core.hub import hub
from core.party_db import SESSION_SECONDS
from core.queue_manager import queue

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


class Login(BaseModel):
    name: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=4, max_length=64)


class Pin(BaseModel):
    pin: str = Field(pattern=r"^\d{4,12}$")   # digits only: easy to type on a phone


def _client(request: Request) -> str:
    return request.client.host if request.client else "?"


def _check_brake(key: str) -> None:
    if wait := passwords.brake.wait_seconds(key):
        raise HTTPException(429, f"Too many wrong tries — wait {wait} s and try again")


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(auth.COOKIE, token, max_age=SESSION_SECONDS, httponly=True, samesite="lax")


@router.get("/auth/me")
async def me(request: Request):
    return auth.identify(request).public()


@router.post("/auth/login")
async def login(req: Login, request: Request, response: Response):
    name = " ".join(req.name.split())
    if not name.isprintable() or not name:
        raise HTTPException(422, "Please use a plain name")
    key = f"login:{_client(request)}:{party_db.name_key(name)}"
    _check_brake(key)
    guest = party_db.find_guest(name)
    if guest is None:   # a new name: register it
        guest_id = party_db.add_guest(name, await asyncio.to_thread(passwords.hash_secret, req.password))
        if guest_id is None:   # registered by someone else a moment ago: never log in as them
            raise HTTPException(409, "Someone just took that name — try again")
        guest = party_db.find_guest(name)
        log.info("New guest %s", name)
    elif not await asyncio.to_thread(passwords.verify, req.password, guest["password"]):
        passwords.brake.failed(key)
        raise HTTPException(401, "That name is taken and the password doesn't match. "
                                 "Pick another name if it isn't you.")
    passwords.brake.succeeded(key)
    who = auth.identify(request)
    if who.token:   # same device: keep its host unlock, switch the guest
        party_db.update_session(who.token, guest_id=guest["id"])
    else:
        _set_cookie(response, party_db.new_session(guest["id"]))
    return {"admin": who.admin, "laptop": who.laptop, "guest": {"id": guest["id"], "name": guest["name"]},
            "pin_set": party_db.pin_hash() is not None}


@router.post("/auth/logout")
async def logout(request: Request, response: Response):
    """Leave the party on this device (also ends a PIN host unlock here)."""
    if token := request.cookies.get(auth.COOKIE):
        party_db.drop_session(token)
    response.delete_cookie(auth.COOKIE)
    return {"ok": True}


@router.post("/auth/admin")
async def unlock_host(req: Pin, request: Request, response: Response):
    """Become host on this device with the host PIN."""
    stored = party_db.pin_hash()
    if stored is None:
        raise HTTPException(409, "No host PIN yet — set one on the laptop's Settings page first")
    key = f"pin:{_client(request)}"
    _check_brake(key)
    if not await asyncio.to_thread(passwords.verify, req.pin, stored):
        passwords.brake.failed(key)
        log.warning("Wrong host PIN from %s", _client(request))
        raise HTTPException(401, "Wrong PIN")
    passwords.brake.succeeded(key)
    who = auth.identify(request)
    if who.token:
        party_db.update_session(who.token, admin=True)
    else:
        _set_cookie(response, party_db.new_session(None, admin=True))
    return {**who.public(), "admin": True}


@router.put("/auth/pin")
async def set_pin(req: Pin, request: Request):
    """Set or change the host PIN — on the laptop only (physical access). Ends every
    device's PIN unlock, so a changed PIN really locks old holders out."""
    if not auth.is_this_laptop(request):
        raise HTTPException(403, "The host PIN can only be set on the laptop running the karaoke")
    party_db.set_pin_hash(await asyncio.to_thread(passwords.hash_secret, req.pin))
    await hub.broadcast({"type": "auth"})
    return auth.identify(request).public()


@router.post("/party/wipe", dependencies=[Depends(auth.require_admin)])
async def wipe_party():
    """Fresh party: guests, sessions and their waiting songs go; cached songs, lyrics,
    settings and the host PIN stay."""
    guests = party_db.count_guests()
    party_db.wipe()
    removed = await queue.drop_guests()
    await hub.broadcast({"type": "auth"})   # open pages re-check who they are
    log.info("Party wiped: %d guest(s), %d queued song(s)", guests, removed)
    return {"ok": True, "guests": guests, "songs_removed": removed}
