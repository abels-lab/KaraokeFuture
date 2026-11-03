"""DJ Co-Pilot tools, run as the host or as a guest: what each may do (services/agent/registry.py).
Run with KARAOKE_SETTINGS_FILE / KARAOKE_DATA_DIR / KARAOKE_PARTY_DB pointing at a temp folder."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from core import settings
from core.auth import HOST_ONLY, Who
from core.queue_manager import queue
from services import agent

HOST = Who(laptop=True, admin=True)
ANN = Who(guest_id=1, name="Ann")
BEN = Who(guest_id=2, name="Ben")


class QueueTestCase(unittest.IsolatedAsyncioTestCase):
    """Starts every test with Ann's and Ben's songs queued and Ben singing; puts the queue back after."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.saved = (list(queue.entries), queue.current, list(queue.played))
        queue.entries = [{"uid": "u_ann", "title": "Wonderwall", "channel": "Oasis", "singer": "Ann", "owner": 1},
                         {"uid": "u_ben", "title": "Shape of You", "channel": "Ed Sheeran", "singer": "Ben", "owner": 2}]
        queue.current = {"uid": "u_cur", "title": "Bohemian Rhapsody", "channel": "Queen", "singer": "Ben", "owner": 2}
        for name in ("broadcast_state", "_save"):
            patcher = patch.object(type(queue), name, new_callable=AsyncMock) if name == "broadcast_state" else \
                patch.object(type(queue), name, lambda self: None)
            patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self):
        queue.entries, queue.current, queue.played = self.saved
        self.tmp.cleanup()


class TestWhoMayUseWhat(QueueTestCase):
    def test_guests_are_offered_only_party_tools(self):
        guest_tools = {t["name"] for t in agent.tools_for(ANN)}
        host_tools = {t["name"] for t in agent.tools_for(HOST)}
        self.assertIn("search_and_queue", guest_tools)
        self.assertNotIn("change_setting", guest_tools)
        self.assertNotIn("set_style", guest_tools)   # agent_guest_style is off by default
        self.assertTrue({"change_setting", "set_style", "customize_control_panel"} <= host_tools)
        for gone in ("read_code_file", "edit_frontend_file", "propose_backend_diff", "undo_frontend_edit"):
            self.assertNotIn(gone, host_tools)

    async def test_host_tools_refused_for_guests_even_if_called(self):
        for name in ("change_setting", "customize_control_panel", "edit_song_lyrics", "delete_playlist"):
            res = await agent.execute_tool(name, {"key": "theme", "value": "rock", "playlist_id": "x"}, ANN)
            self.assertEqual(res.get("error"), HOST_ONLY, name)

    async def test_file_tools_are_gone(self):
        res = await agent.execute_tool("read_code_file", {"path": "settings.json"}, HOST)
        self.assertIn("Unknown tool", res["error"])

    async def test_locked_settings_cannot_be_changed_from_chat(self):
        for key in ("agent_base_url", "agent_api_key", "agent_guest_chat"):
            res = await agent.execute_tool("change_setting", {"key": key, "value": "x"}, HOST)
            self.assertIn("Settings page", res["error"])


class TestQueueActions(QueueTestCase):
    async def test_guest_cannot_skip_or_remove_someone_elses_song(self):
        with patch.object(type(queue), "next", new_callable=AsyncMock) as nxt:
            self.assertIn("someone else", (await agent.execute_tool("queue_action", {"action": "skip"}, ANN))["error"])
            nxt.assert_not_awaited()
        res = await agent.execute_tool("queue_action", {"action": "remove", "song": "Shape of You"}, ANN)
        self.assertIn("someone else", res["error"])
        self.assertEqual(len(queue.entries), 2)
        res = await agent.execute_tool("queue_action", {"action": "clear"}, ANN)
        self.assertEqual(res["error"], HOST_ONLY)

    async def test_guest_removes_own_song_and_singer_skips_own(self):
        res = await agent.execute_tool("queue_action", {"action": "remove", "song": "Wonderwall"}, ANN)
        self.assertEqual(res["status"], "removed")
        with patch.object(type(queue), "next", new_callable=AsyncMock, return_value={"title": "Next"}):
            res = await agent.execute_tool("queue_action", {"action": "skip"}, BEN)
        self.assertEqual(res["status"], "skipped")

    async def test_host_removes_by_index_and_current(self):
        res = await agent.execute_tool("queue_action", {"action": "delete", "index": 2}, HOST)
        self.assertEqual((res["status"], len(queue.entries)), ("removed", 1))
        with patch.object(type(queue), "next", new_callable=AsyncMock) as nxt:
            res = await agent.execute_tool("queue_action", {"action": "remove", "song": "current"}, HOST)
            nxt.assert_awaited_once()
        self.assertEqual(res["status"], "removed")


class TestSearchAndQueue(QueueTestCase):
    async def _queue(self, who, singer):
        hit = [{"id": "dQw4w9WgXcQ", "title": "Never Gonna Give You Up", "channel": "Rick", "duration": 200}]
        with patch("services.agent.tools_party.smart_search.run", return_value=(hit, None)), \
             patch("routers.queue.queue.add", new_callable=AsyncMock,
                   side_effect=lambda *a, **k: {"uid": "new", "title": a[1], "singer": a[4], "owner": a[6],
                                                "status": "queued"}) as add, \
             patch("routers.queue.worker.submit", new_callable=AsyncMock):
            res = await agent.execute_tool("search_and_queue", {"query": "rick", "singer": singer}, who)
        return res, add

    async def test_guest_always_sings_their_own_song(self):
        res, add = await self._queue(ANN, "Ben")
        self.assertEqual(res["singer"], "Ann")
        self.assertEqual(add.call_args[0][6], 1)   # owner = Ann's guest id

    async def test_host_queues_for_anyone(self):
        res, add = await self._queue(HOST, "Grandma")
        self.assertEqual(res["singer"], "Grandma")
        self.assertIsNone(add.call_args[0][6])

    async def test_anonymous_must_log_in(self):
        res, add = await self._queue(Who(), "Me")
        self.assertIn("Log in", res["error"])
        add.assert_not_awaited()


@patch("services.agent.tools_lyrics.resolve_song", return_value=("song_1", "Sweet Caroline", {}))
@patch("services.agent.tools_lyrics.lyrics_source.current_text", return_value="Line one\nThis is wrong\nLine three")
class TestLyrics(QueueTestCase):
    async def test_everyone_reads_only_the_host_edits(self, _text, _song):
        res = await agent.execute_tool("get_song_lyrics", {"query": "caroline"}, ANN)
        self.assertEqual(res["line_count"], 3)
        res = await agent.execute_tool("edit_song_lyrics", {"old_snippet": "wrong", "new_snippet": "right"}, ANN)
        self.assertEqual(res["error"], HOST_ONLY)

    async def test_host_fixes_a_line(self, _text, _song):
        with patch("services.agent.tools_lyrics.lyrics_source.save_user", return_value=3) as save, \
             patch("services.agent.tools_lyrics.worker.submit_lyrics", new_callable=AsyncMock):
            res = await agent.execute_tool("edit_song_lyrics", {"old_snippet": "wrong", "new_snippet": "right"}, HOST)
        self.assertEqual(res["status"], "updated")
        self.assertEqual(save.call_args[0][1], "Line one\nThis is right\nLine three")
        res = await agent.execute_tool("edit_song_lyrics", {"old_snippet": "absent", "new_snippet": "x"}, HOST)
        self.assertIn("Could not find", res["error"])


class TestControlPanel(QueueTestCase):
    async def test_buttons_are_cleaned_and_layout_saved(self):
        with patch("services.agent.store.UI_CONFIG_FILE", self.base / "ui.json"), \
             patch("services.agent.tools_host.hub.broadcast", new_callable=AsyncMock):
            res = await agent.execute_tool("customize_control_panel", {
                "column_order": ["right", "center", "left"], "hide_elements": ["qr-card", "bad id!"],
                "guide_width": "50%; background:red"}, HOST)
            self.assertEqual(res["config"]["column_order"], ["right", "center", "left"])
            self.assertEqual(res["config"]["hidden_elements"], ["qr-card"])
            self.assertEqual(res["config"]["guide_width"], "25%")   # the injected CSS was refused
            res = await agent.execute_tool("customize_control_panel", {"action": "add_button", "button": {
                "id": "horn", "label": "<img src=x onerror=alert(1)>", "action": "sfx", "style": "x"}}, HOST)
            button = res["config"]["custom_buttons"][0]
            self.assertNotIn("style", button)
            self.assertEqual(agent.get_ui_config()["custom_buttons"][0]["id"], "horn")
            self.assertNotIn("custom_css", agent.get_ui_config())


if __name__ == "__main__":
    unittest.main()
