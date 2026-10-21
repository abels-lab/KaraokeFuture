"""WebSocket connection hub: tracks TV / phone clients and fans messages out to them."""
import asyncio
import logging

from fastapi import WebSocket

log = logging.getLogger(__name__)


class Hub:
    def __init__(self) -> None:
        # websocket -> "tv" (control panel, plays the audio) | "screen" (projector) | "remote" (phones)
        self.clients: dict[WebSocket, str] = {}

    def tv_connected(self) -> bool:
        return "tv" in self.clients.values()

    def count(self, role: str) -> int:
        return sum(r == role for r in self.clients.values())

    async def connect(self, ws: WebSocket, role: str) -> None:
        await ws.accept()
        self.clients[ws] = role
        log.info("%s client connected (%d total)", role, len(self.clients))

    def disconnect(self, ws: WebSocket) -> None:
        if (role := self.clients.pop(ws, None)) is not None:
            log.info("%s client disconnected (%d left)", role, len(self.clients))

    async def send(self, ws: WebSocket, message: dict) -> None:
        try:
            await ws.send_json(message)
        except Exception:  # closed / broken socket
            self.disconnect(ws)

    async def broadcast(self, message: dict, *roles: str) -> None:
        """To every client, or only to the given roles."""
        targets = [ws for ws, r in list(self.clients.items()) if not roles or r in roles]
        await asyncio.gather(*(self.send(ws, message) for ws in targets))


hub = Hub()
