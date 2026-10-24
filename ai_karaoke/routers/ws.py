"""WebSocket endpoint keeping the control panel, projector screens and phones in sync.

Connect with  /ws?role=tv (control panel, plays the audio) | screen (projector) | remote (phones)
Server -> client:  {"type": "state", "data": {...}}
                   {"type": "media", "song_id"}                             (lyrics/video changed)
                   {"type": "control", "action", "value"}                   (control panel only)
                   {"type": "playback", "uid", "time", "duration", "paused"} (screens + phones, 4 Hz)
                   {"type": "game" | "game_result", ...}                    (screens: singing game)
                   {"type": "intro", "uid", "left", "total", "mode", "names"} (screens + phones,
                        4 Hz while the pre-song countdown card is up; left 0 = it's gone)
                   {"type": "auth"}               (logins changed / party wiped: re-check who you are)
                   {"type": "denied", "message"}  (a control message this client may not send)
Client -> server:  {"type": "ping"}
                   {"type": "control", "action": "play|pause|restart|skip|next|previous|seek|seek_by", "value"}
                   {"type": "ended", "uid": "..."}                         (TV only)
                   {"type": "playback", "uid", "time", "duration", "paused"} (TV only)
                   {"type": "sync_playback", "uid", "time", "duration", "paused"} (TV only, reconnect handshake)
                   {"type": "intro", ...}  (TV only; the countdown is the TV's, screens just show it)

Security (core/auth.py): the client is identified from its session cookie and address on
every message. The "tv" role (which can end songs and drives every screen) is granted only
to the host — anyone else asking for it is connected as "remote". "control" is accepted
from the host, or from the guest who queued the song playing right now (their own song
only: pause/play/restart/seek and skip). Screens only listen, so anyone may open one.
"""
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core import auth, settings
from core.hub import hub
from core.queue_manager import queue

log = logging.getLogger(__name__)
router = APIRouter()

ROLES = {"tv", "screen", "remote"}
TV_ACTIONS = {"play", "pause", "restart", "seek", "seek_by", "previous", "next", "skip"}


def _num(value) -> float:
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return 0.0


async def _control(ws: WebSocket, msg: dict) -> None:
    action = msg.get("action")
    who = auth.identify(ws)
    if not auth.may_manage(who, queue.current) and action not in ("next", "skip", "previous"):
        await hub.send(ws, {"type": "denied", "message": "Only the host or the person singing can control this song"})
    elif str(action).startswith("seek") and not who.admin and not settings.get("guest_scrubbing"):
        await hub.send(ws, {"type": "denied", "message": "Timeline scrubbing is reserved for the host"})
    elif action in ("skip", "next"):
        await queue.next()
    elif action == "previous":
        if not who.admin:
            await hub.send(ws, {"type": "denied", "message": "Only the host can navigate to previous songs"})
        else:
            await queue.previous()
    elif action in TV_ACTIONS:
        await queue.control(action, _num(msg.get("value")))


async def _intro(msg: dict) -> None:
    """The control panel's countdown: remembered (a battle song can be joined until it ends)
    and passed on with only plain, short fields."""
    uid, left = str(msg.get("uid", ""))[:32], max(0.0, _num(msg.get("left")))
    playing = bool(queue.current and queue.current["uid"] == uid)
    queue.set_intro(uid, left if playing else 0)
    names = msg.get("names") if isinstance(msg.get("names"), list) else []
    await hub.broadcast({"type": "intro", "uid": uid, "left": left, "total": _num(msg.get("total")),
                         "mode": str(msg.get("mode", ""))[:12], "names": [str(n)[:32] for n in names[:2]]},
                        "remote", "screen")


async def _handle(ws: WebSocket, role: str, msg: dict) -> None:
    kind = msg.get("type")
    if kind == "ping":
        await ws.send_json({"type": "pong"})
    elif kind == "control":
        await _control(ws, msg)
    elif role != "tv":
        return
    elif kind == "ended":
        await queue.finish(str(msg.get("uid", "")))
    elif kind == "playback":
        uid = str(msg.get("uid", ""))
        t = _num(msg.get("time"))
        dur = _num(msg.get("duration"))
        paused = bool(msg.get("paused"))
        queue.update_playback(uid, t, dur, paused)
        await hub.broadcast({
            "type": "playback",
            "uid": uid,
            "time": t,
            "duration": dur,
            "paused": paused,
        }, "remote", "screen")
    elif kind == "sync_playback":
        uid = str(msg.get("uid", ""))
        t = _num(msg.get("time"))
        dur = _num(msg.get("duration"))
        if not dur and queue.current and queue.current.get("uid") == uid:
            dur = _num(queue.current.get("duration", 0))
        paused = bool(msg.get("paused"))
        queue.update_playback(uid, t, dur, paused)
        await hub.broadcast({
            "type": "playback",
            "uid": uid,
            "time": t,
            "duration": dur,
            "paused": paused,
        }, "remote", "screen")
    elif kind == "intro":
        await _intro(msg)
    elif kind in ("game", "game_result") and len(json.dumps(msg)) < 16_000:
        await hub.broadcast(msg, "screen")  # singing game: live state 25 Hz + results, for projectors


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, role: str = "remote"):
    role = role if role in ROLES else "remote"
    if role == "tv" and not auth.identify(ws).admin:
        log.warning("Refused the control-panel role to %s (not the host)", ws.client.host if ws.client else "?")
        role = "remote"
    await hub.connect(ws, role)
    try:
        await queue.client_joined(ws, role)
        if role == "screen":  # the control panel shows how many projectors are attached
            await queue.broadcast_state()
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            if isinstance(msg, dict):
                await _handle(ws, role, msg)
    except WebSocketDisconnect:
        pass
    finally:
        hub.disconnect(ws)
        if role == "screen":
            await queue.broadcast_state()
