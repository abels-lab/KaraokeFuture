"""The host single-page app: its addresses, and the one server change it relies on.

- /host, /tv, /library and /settings all serve static/host.html (the page picks the view or popup
  from the address itself); /screen and /remote stay their own pages.
- A host app in controller mode (a phone or tablet) offers to play the audio itself when no
  player is connected, so the "state" broadcast's tv_connected must also go out when the
  player (role "tv") disconnects, not only when a projector screen does.
"""
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import WebSocketDisconnect

import routers.ws as ws_router

STATIC = Path(__file__).resolve().parent.parent / "static"


class TestHostRoutes(unittest.TestCase):
    def test_host_addresses_serve_the_host_app(self):
        import main
        for page in ("host", "tv", "library", "settings"):
            self.assertEqual(main.PAGES[page], "host.html", page)
        self.assertEqual(main.PAGES["screen"], "screen.html")
        self.assertEqual(main.PAGES["remote"], "remote.html")
        for name in set(main.PAGES.values()):
            self.assertTrue((STATIC / name).is_file(), name)

    def test_pages_respond(self):
        from fastapi.testclient import TestClient
        import main
        client = TestClient(main.app)   # no "with": the worker and warmer don't start
        host = client.get("/host")
        self.assertEqual(host.status_code, 200)
        self.assertIn('id="tv-layout"', host.text)
        for page in ("tv", "library", "settings"):
            self.assertEqual(client.get(f"/{page}").text, host.text, page)
        self.assertNotEqual(client.get("/screen").text, host.text)
        self.assertEqual(client.get("/nope").status_code, 404)


class TestPlayerDisconnectBroadcast(unittest.IsolatedAsyncioTestCase):
    async def _connect_and_drop(self, role: str, admin: bool = True) -> AsyncMock:
        ws = MagicMock()
        ws.client.host = "127.0.0.1"
        ws.receive_text = AsyncMock(side_effect=WebSocketDisconnect())
        who = MagicMock(admin=admin)
        with patch.object(ws_router.auth, "identify", return_value=who), \
             patch.object(ws_router.hub, "connect", new_callable=AsyncMock), \
             patch.object(ws_router.hub, "disconnect"), \
             patch.object(ws_router.queue, "client_joined", new_callable=AsyncMock), \
             patch.object(ws_router.queue, "broadcast_state", new_callable=AsyncMock) as broadcast:
            await ws_router.websocket_endpoint(ws, role)
        return broadcast

    async def test_player_leaving_broadcasts_state(self):
        broadcast = await self._connect_and_drop("tv")
        broadcast.assert_awaited_once()

    async def test_screen_still_broadcasts_on_join_and_leave(self):
        broadcast = await self._connect_and_drop("screen")
        self.assertEqual(broadcast.await_count, 2)

    async def test_phone_leaving_stays_quiet(self):
        broadcast = await self._connect_and_drop("remote")
        broadcast.assert_not_awaited()

    async def test_non_host_asking_for_tv_is_a_remote(self):
        broadcast = await self._connect_and_drop("tv", admin=False)
        broadcast.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
