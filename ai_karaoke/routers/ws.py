"""WebSocket endpoint keeping the control panel, projector screens and phones in sync.

Connect with  /ws?role=tv (control panel, plays the audio) | screen (projector) | remote (phones)
Server -> client:  {"type": "state", "data": {...}}
                   {"type": "media", "song_id"}                             (lyrics/video changed)
                   {"type": "control", "action", "value"}                   (control panel only)
                   {"type": "playback", "uid", "time", "duration", "paused"} (screens + phones, 4 Hz)
                   {"type": "game" | "game_result", ...}                    (screens: singing game)
Client -> server:  {"type": "ping"}
                   {"type": "control", "action": "play|pause|restart|skip|seek|seek_by", "value"}
                   {"type": "ended", "uid": "..."}                         (TV only)
                   {"type": "playback", "uid", "time", "duration", "paused"} (TV only)
"""
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.hub import hub
from core.queue_manager import queue

log = logging.getLogger(__name__)
router = APIRouter()

ROLES = {"tv", "screen", "remote"}
TV_ACTIONS = {"play", "pause", "restart", "seek", "seek_by"}


def _num(value) -> float:
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return 0.0


async def _handle(ws: WebSocket, role: str, msg: dict) -> None:
    kind = msg.get("type")
    if kind == "ping":
        await ws.send_json({"type": "pong"})
    elif kind == "control":
        action = msg.get("action")
        if action == "skip":
            await queue.next()
        elif action in TV_ACTIONS:
            await queue.control(action, _num(msg.get("value")))
    elif role != "tv":
        return
    elif kind == "ended":
        await queue.finish(str(msg.get("uid", "")))
    elif kind == "playback":
        await hub.broadcast({
            "type": "playback",
            "uid": str(msg.get("uid", "")),
            "time": _num(msg.get("time")),
            "duration": _num(msg.get("duration")),
            "paused": bool(msg.get("paused")),
        }, "remote", "screen")
    elif kind in ("game", "game_result") and len(json.dumps(msg)) < 16_000:
        await hub.broadcast(msg, "screen")  # singing game: live state 25 Hz + results, for projectors


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, role: str = "remote"):
    role = role if role in ROLES else "remote"
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
