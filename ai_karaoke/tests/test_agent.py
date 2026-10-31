import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from core import settings
from services import agent


class TestAgentTools(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.tmp_dir.name).resolve()
        self.queue_patcher = patch("config.QUEUE_FILE", self.base_path / "queue.json")
        self.queue_patcher.start()
        from core.queue_manager import queue
        self._orig_queue_state = {
            "entries": list(queue.entries),
            "current": dict(queue.current) if queue.current else None,
            "played": list(queue.played),
            "playback": dict(queue.playback),
        }

    def tearDown(self):
        from core.queue_manager import queue
        queue.entries = self._orig_queue_state["entries"]
        queue.current = self._orig_queue_state["current"]
        queue.played = self._orig_queue_state["played"]
        queue.playback = self._orig_queue_state["playback"]
        self.queue_patcher.stop()
        self.tmp_dir.cleanup()

    async def test_get_party_status(self):
        res = await agent.execute_tool("get_party_status", {})
        self.assertIn("theme", res)
        self.assertIn("accent", res)
        self.assertIn("queue_count", res)

    @patch("core.cache_manager.list_songs")
    async def test_get_library_songs(self, mock_list):
        mock_list.return_value = [
            {"id": "s1", "title": "99 Luftballons", "channel": "Nena", "ready": True},
            {"id": "s2", "title": "Major Tom", "channel": "Peter Schilling", "ready": True},
            {"id": "s3", "title": "Du Hast", "channel": "Rammstein", "ready": False},
        ]
        res = await agent.execute_tool("get_library_songs", {"limit": 2})
        self.assertEqual(res["total_cached"], 3)
        self.assertEqual(len(res["songs"]), 2)
        self.assertEqual(res["songs"][0]["title"], "99 Luftballons")

        # Test search filter
        res_search = await agent.execute_tool("get_library_songs", {"search": "rammstein"})
        self.assertEqual(res_search["matched_count"], 1)
        self.assertEqual(res_search["songs"][0]["title"], "Du Hast")

    async def test_change_setting(self):
        res = await agent.execute_tool("change_setting", {"key": "accent", "value": "neon"})
        self.assertEqual(res.get("status"), "ok")
        self.assertEqual(settings.get("accent"), "neon")

        # Test drawer position setting
        res = await agent.execute_tool("change_setting", {"key": "agent_drawer_position", "value": "left"})
        self.assertEqual(res.get("status"), "ok")
        self.assertEqual(settings.get("agent_drawer_position"), "left")

        # Test layout mode setting
        res = await agent.execute_tool("change_setting", {"key": "agent_layout_mode", "value": "drawer"})
        self.assertEqual(res.get("status"), "ok")
        self.assertEqual(settings.get("agent_layout_mode"), "drawer")

    @patch("core.worker.worker.submit", new_callable=AsyncMock)
    @patch("services.search.run")
    async def test_search_and_queue(self, mock_search, mock_submit):
        mock_search.return_value = ([{
            "id": "test_123",
            "title": "Bohemian Rhapsody",
            "channel": "Queen",
            "duration": 354,
            "thumbnail": "http://example.com/thumb.jpg",
        }], {})
        res = await agent.execute_tool("search_and_queue", {"query": "Bohemian Rhapsody", "singer": "Alice"})
        self.assertEqual(res.get("status"), "queued")
        self.assertEqual(res.get("singer"), "Alice")
        self.assertEqual(res.get("title"), "Bohemian Rhapsody")
        mock_submit.assert_called_once_with("test_123")

    async def test_record_improvement_request(self):
        test_file = self.base_path / "test_improvements.jsonl"
        with patch("services.agent.IMPROVEMENTS_FILE", test_file):
            res = await agent.execute_tool("record_improvement_request", {
                "topic": "custom_playlists",
                "description": "Host asked for custom playlist folders",
                "safe_alternative": "Offered to queue rock songs directly",
            })
            self.assertEqual(res.get("status"), "recorded")
            self.assertEqual(res.get("topic"), "custom_playlists")

            improvements = agent.list_improvements(limit=10)
            self.assertGreaterEqual(len(improvements), 1)
            last = improvements[-1]
            self.assertEqual(last["category"], "feature_request")
            self.assertIn("custom_playlists", last["summary"])
            self.assertEqual(last["details"]["topic"], "custom_playlists")

    async def test_turn_limit_exhaustion_friendly_reply(self):
        # Simulate gemini returning function calls continuously
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{"functionCall": {"name": "get_party_status", "args": {}}}]
                }
            }]
        }
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        test_file = self.base_path / "test_improvements.jsonl"
        with patch("httpx.AsyncClient") as mock_http, patch("services.agent.IMPROVEMENTS_FILE", test_file):
            mock_http.return_value.__aenter__.return_value = mock_client
            res = await agent._chat_gemini("do an impossible task", [], "gemini-3.8-flash", "test-key")
            self.assertIn("hit my DJ turn limit", res.get("reply", ""))
            self.assertIn("get_party_status", res.get("reply", ""))

            # Verify improvement was logged
            improvements = agent.list_improvements(limit=10)
            exhausted = [i for i in improvements if i["category"] == "turn_limit_exhausted"]
            self.assertGreaterEqual(len(exhausted), 1)

    async def test_read_code_file_safety(self):
        # Path traversal outside project root should be rejected
        res = await agent.execute_tool("read_code_file", {"path": "../../etc/passwd"})
        self.assertIn("error", res)

    async def test_edit_frontend_file_and_undo(self):
        static_dir = self.base_path / "static"
        static_dir.mkdir(parents=True, exist_ok=True)
        css_file = static_dir / "test.css"
        css_file.write_text("body { color: red; }", encoding="utf-8")

        with patch("services.agent.BASE_DIR", self.base_path):
            # Non-static file edit rejected
            res = await agent.execute_tool("edit_frontend_file", {
                "path": "core/worker.py",
                "content": "# malicious",
                "summary": "edit",
            })
            self.assertIn("error", res)

            # Static file edit accepted and backed up
            res = await agent.execute_tool("edit_frontend_file", {
                "path": "static/test.css",
                "content": "body { color: blue; }",
                "summary": "make blue",
            })
            self.assertEqual(res.get("status"), "applied")
            self.assertEqual(css_file.read_text(encoding="utf-8"), "body { color: blue; }")
            self.assertTrue((static_dir / "test.css.bak").is_file())

            # Surgical snippet edit
            snippet_res = await agent.execute_tool("edit_frontend_file", {
                "path": "static/test.css",
                "old_snippet": "color: blue;",
                "new_snippet": "color: green;",
                "summary": "make green",
            })
            self.assertEqual(snippet_res.get("status"), "applied")
            self.assertEqual(css_file.read_text(encoding="utf-8"), "body { color: green; }")

            # Undo restores backup
            undo_res = await agent.execute_tool("undo_frontend_edit", {"path": "static/test.css"})
            self.assertEqual(undo_res.get("status"), "undone")
            self.assertEqual(css_file.read_text(encoding="utf-8"), "body { color: blue; }")

    async def test_customize_control_panel(self):
        test_file = self.base_path / "ui_config.json"
        with patch("services.agent.UI_CONFIG_FILE", test_file), patch("core.hub.hub.broadcast", new_callable=AsyncMock) as mock_broadcast:
            # 1. Update layout, columns, hidden elements, guide slider width & thumb
            res = await agent.execute_tool("customize_control_panel", {
                "action": "update",
                "column_order": ["right", "center", "left"],
                "hide_elements": ["qr-card", "nav-panel"],
                "guide_width": "50%",
                "guide_thumb": "smiley",
                "custom_css": "body { opacity: 0.95; }",
            })
            self.assertEqual(res.get("status"), "ok")
            cfg = res.get("config", {})
            self.assertEqual(cfg["column_order"], ["right", "center", "left"])
            self.assertIn("qr-card", cfg["hidden_elements"])
            self.assertIn("nav-panel", cfg["hidden_elements"])
            self.assertEqual(cfg["guide_width"], "50%")
            self.assertEqual(cfg["guide_thumb"], "smiley")
            self.assertEqual(cfg["custom_css"], "body { opacity: 0.95; }")
            mock_broadcast.assert_called_with({"type": "ui_config", "config": cfg})

            # Unhide nav-panel
            res_show = await agent.execute_tool("customize_control_panel", {
                "action": "update",
                "show_elements": ["nav-panel"],
            })
            self.assertNotIn("nav-panel", res_show["config"]["hidden_elements"])
            self.assertIn("qr-card", res_show["config"]["hidden_elements"])

            # 2. Add button
            res_add = await agent.execute_tool("customize_control_panel", {
                "action": "add_button",
                "button": {
                    "id": "btn-airhorn",
                    "label": "Airhorn",
                    "icon": "📢",
                    "action": "sfx",
                    "value": "airhorn",
                    "target": "display",
                },
            })
            self.assertEqual(res_add.get("status"), "ok")
            btn_ids = [b["id"] for b in res_add["config"]["custom_buttons"]]
            self.assertIn("btn-airhorn", btn_ids)

            # 3. Remove button
            res_rm = await agent.execute_tool("customize_control_panel", {
                "action": "remove_button",
                "button_id": "btn-airhorn",
            })
            self.assertEqual(res_rm.get("status"), "ok")
            btn_ids_after = [b["id"] for b in res_rm["config"]["custom_buttons"]]
            self.assertNotIn("btn-airhorn", btn_ids_after)

            # 4. Reset
            res_reset = await agent.execute_tool("customize_control_panel", {"action": "reset"})
            self.assertEqual(res_reset.get("status"), "ok")
            self.assertEqual(res_reset["config"]["column_order"], ["left", "center", "right"])
            self.assertEqual(res_reset["config"]["hidden_elements"], [])
            self.assertEqual(res_reset["config"]["custom_buttons"], [])

    @patch("services.agent.lyrics_source.load_user", return_value="Line one\nLine two\nLine three")
    @patch("services.agent.lyrics_source.current_text", return_value="Line one\nLine two\nLine three")
    @patch("services.agent._resolve_song", return_value=("song_123", "Sweet Caroline", {"lyrics_source": "lrc"}))
    async def test_get_song_lyrics(self, mock_resolve, mock_text, mock_load):
        res = await agent.execute_tool("get_song_lyrics", {"query": "Sweet Caroline"})
        self.assertEqual(res.get("song_id"), "song_123")
        self.assertEqual(res.get("title"), "Sweet Caroline")
        self.assertEqual(res.get("line_count"), 3)
        self.assertTrue(res.get("has_user_lyrics"))
        self.assertIn("Line one", res.get("text"))

    @patch("core.worker.worker.submit_lyrics", new_callable=AsyncMock)
    @patch("services.agent.lyrics_source.save_user", return_value=4)
    @patch("services.agent.lyrics_source.current_text", return_value="Line one\nThis is wrong\nLine three\nLine four")
    @patch("services.agent._resolve_song", return_value=("song_123", "Sweet Caroline", {}))
    async def test_edit_song_lyrics_surgical(self, mock_resolve, mock_text, mock_save, mock_submit):
        res = await agent.execute_tool("edit_song_lyrics", {
            "query": "Sweet Caroline",
            "old_snippet": "This is wrong",
            "new_snippet": "This is right",
        })
        self.assertEqual(res.get("status"), "updated")
        self.assertEqual(res.get("song_id"), "song_123")
        mock_save.assert_called_once_with("song_123", "Line one\nThis is right\nLine three\nLine four")
        mock_submit.assert_called_once_with("song_123")

    @patch("core.worker.worker.submit_lyrics", new_callable=AsyncMock)
    @patch("services.agent.ultrastar_source.forget")
    @patch("services.agent.lyrics_source.forget_online")
    @patch("services.agent.lyrics_source.delete_user")
    @patch("services.agent._resolve_song", return_value=("song_123", "Sweet Caroline", {}))
    async def test_edit_song_lyrics_reset(self, mock_resolve, mock_del, mock_forget_online, mock_forget_ultra, mock_submit):
        res = await agent.execute_tool("edit_song_lyrics", {"query": "Sweet Caroline", "reset": True})
        self.assertEqual(res.get("status"), "reset")
        mock_del.assert_called_once_with("song_123")
        mock_forget_online.assert_called_once_with("song_123")
        mock_forget_ultra.assert_called_once_with("song_123")
        mock_submit.assert_called_once_with("song_123")

    @patch("services.agent.lyrics_source.current_text", return_value="Line one\nLine two\nLine three\nLine four")
    @patch("services.agent._resolve_song", return_value=("song_123", "Sweet Caroline", {}))
    async def test_edit_song_lyrics_snippet_not_found(self, mock_resolve, mock_text):
        res = await agent.execute_tool("edit_song_lyrics", {
            "query": "Sweet Caroline",
            "old_snippet": "Nonexistent snippet",
            "new_snippet": "New line",
        })
        self.assertIn("error", res)
        self.assertIn("Could not find snippet", res["error"])

    async def test_edit_frontend_file_broadcasts_hot_css_and_reload(self):
        static_dir = self.base_path / "static"
        static_dir.mkdir(parents=True, exist_ok=True)
        css_file = static_dir / "style.css"
        css_file.write_text("body { margin: 0; }", encoding="utf-8")
        html_file = static_dir / "page.html"
        html_file.write_text("<div>test</div>", encoding="utf-8")

        with patch("services.agent.BASE_DIR", self.base_path), patch("core.hub.hub.broadcast", new_callable=AsyncMock) as mock_broadcast:
            # Edit CSS -> hot_css
            await agent.execute_tool("edit_frontend_file", {
                "path": "static/style.css",
                "content": "body { margin: 10px; }",
                "summary": "change margin",
            })
            mock_broadcast.assert_called_with({"type": "hot_css"})

            # Undo CSS -> hot_css
            await agent.execute_tool("undo_frontend_edit", {"path": "static/style.css"})
            mock_broadcast.assert_called_with({"type": "hot_css"})

            # Edit HTML -> reload
            await agent.execute_tool("edit_frontend_file", {
                "path": "static/page.html",
                "content": "<div>updated</div>",
                "summary": "update page",
            })
            mock_broadcast.assert_called_with({"type": "reload"})

            # Undo HTML -> reload
            await agent.execute_tool("undo_frontend_edit", {"path": "static/page.html"})
            mock_broadcast.assert_called_with({"type": "reload"})

    async def test_backend_diff_proposal_apply_and_cancel(self):
        core_dir = self.base_path / "core"
        core_dir.mkdir(parents=True, exist_ok=True)
        py_file = core_dir / "sample.py"
        py_file.write_text("val = 10\n", encoding="utf-8")

        with patch("services.agent.BASE_DIR", self.base_path):
            # Propose diff
            prop_res = await agent.execute_tool("propose_backend_diff", {
                "path": "core/sample.py",
                "old_snippet": "val = 10",
                "new_snippet": "val = 20",
                "summary": "update val",
            })
            self.assertEqual(prop_res.get("status"), "proposed")
            prop_id = prop_res.get("proposal_id")
            self.assertIn(prop_id, agent.PENDING_PROPOSALS)

            # Cancel proposal
            cancel_res = agent.cancel_proposal(prop_id)
            self.assertEqual(cancel_res.get("status"), "cancelled")
            self.assertNotIn(prop_id, agent.PENDING_PROPOSALS)

            # Re-propose and Apply
            prop_res2 = await agent.execute_tool("propose_backend_diff", {
                "path": "core/sample.py",
                "old_snippet": "val = 10",
                "new_snippet": "val = 30",
                "summary": "update val to 30",
            })
            prop_id2 = prop_res2.get("proposal_id")
            apply_res = agent.apply_proposal(prop_id2)
            self.assertEqual(apply_res.get("status"), "applied")
            self.assertEqual(py_file.read_text(encoding="utf-8"), "val = 30\n")


class TestAgentChat(unittest.IsolatedAsyncioTestCase):
    async def test_chat_without_api_key_warns(self):
        with patch.object(agent, "_get_api_key", return_value=""):
            settings.update({"agent_provider": "gemini"})
            res = await agent.chat_with_agent("hello")
            self.assertIn("Please configure your **Google AI Studio API key**", res.get("reply", ""))

    async def test_gemini_model_strip_and_404_tip(self):
        # Verify models/ prefix is stripped and 404 includes helpful tip
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = '{"error": {"message": "models/gemini-2.5-flash is not found"}}'

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        with patch("httpx.AsyncClient") as mock_http:
            mock_http.return_value.__aenter__.return_value = mock_client
            res = await agent._chat_gemini("hello", [], "models/gemini-2.5-flash", "test-key")
            call_url = mock_client.post.call_args[0][0]
            self.assertIn("models/gemini-2.5-flash:generateContent", call_url)
            self.assertNotIn("models/models", call_url)
            self.assertIn("Tip: Model 'gemini-2.5-flash' was not found", res["reply"])

    async def test_openai_schema_lowercase_normalization(self):
        schema = {
            "type": "OBJECT",
            "properties": {
                "name": {"type": "STRING"},
                "count": {"type": "INTEGER"},
            },
            "required": ["name"],
        }
        normalized = agent._normalize_openai_schema(schema)
        self.assertEqual(normalized["type"], "object")
        self.assertEqual(normalized["properties"]["name"]["type"], "string")
        self.assertEqual(normalized["properties"]["count"]["type"], "integer")


    @patch("routers.agent.hub.broadcast", new_callable=AsyncMock)
    @patch("routers.agent.agent.chat_with_agent", new_callable=AsyncMock)
    async def test_chat_endpoint_broadcasts_to_screen(self, mock_chat, mock_broadcast):
        from routers.agent import ChatRequest, chat
        from core.auth import Who

        mock_chat.return_value = {"reply": "Playing Bohemian Rhapsody!", "tool_calls": []}
        who = Who(name="HostAdmin", admin=True)
        req = ChatRequest(message="Play Queen")

        res = await chat(req, who=who)
        self.assertEqual(res["reply"], "Playing Bohemian Rhapsody!")

        # Check broadcast was called twice: once for user message, once for agent response
        self.assertEqual(mock_broadcast.call_count, 2)

        # Call 1: user message
        user_call = mock_broadcast.call_args_list[0]
        user_msg = user_call[0][0]
        self.assertEqual(user_msg["type"], "chat")
        self.assertEqual(user_msg["sender"], "user")
        self.assertEqual(user_msg["text"], "Play Queen")
        self.assertEqual(user_msg["name"], "HostAdmin")
        self.assertIn("screen", user_call[0][1:])

        # Call 2: agent response
        agent_call = mock_broadcast.call_args_list[1]
        agent_msg = agent_call[0][0]
        self.assertEqual(agent_msg["type"], "chat")
        self.assertEqual(agent_msg["sender"], "agent")
        self.assertEqual(agent_msg["text"], "Playing Bohemian Rhapsody!")
        self.assertEqual(agent_msg["name"], "DJ Co-Pilot")
        self.assertIn("screen", agent_call[0][1:])

if __name__ == "__main__":
    unittest.main()
