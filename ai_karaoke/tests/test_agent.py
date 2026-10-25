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

    def tearDown(self):
        self.tmp_dir.cleanup()

    async def test_get_party_status(self):
        res = await agent.execute_tool("get_party_status", {})
        self.assertIn("theme", res)
        self.assertIn("accent", res)
        self.assertIn("queue_count", res)

    async def test_change_setting(self):
        res = await agent.execute_tool("change_setting", {"key": "accent", "value": "neon"})
        self.assertEqual(res.get("status"), "ok")
        self.assertEqual(settings.get("accent"), "neon")

    @patch("services.search.run")
    async def test_search_and_queue(self, mock_search):
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

            # Undo restores backup
            undo_res = await agent.execute_tool("undo_frontend_edit", {"path": "static/test.css"})
            self.assertEqual(undo_res.get("status"), "undone")
            self.assertEqual(css_file.read_text(encoding="utf-8"), "body { color: red; }")

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


if __name__ == "__main__":
    unittest.main()
