"""DJ Co-Pilot chat turns: the model loop, who may chat, and the projector overlay. No network:
httpx is mocked. Run with KARAOKE_SETTINGS_FILE / KARAOKE_DATA_DIR pointing at a temp folder."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from core import settings
from core.auth import Who
from services import agent
from services.agent import llm_openai

HOST = Who(laptop=True, admin=True, name="Hosty")
ANN = Who(guest_id=3, name="Ann")


def gemini_reply(status=200, body=None, text=""):
    res = MagicMock(status_code=status, text=text)
    res.json.return_value = body or {}
    client = AsyncMock()
    client.post.return_value = res
    return client


class TestChatTurn(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        patcher = patch("services.agent.store.IMPROVEMENTS_FILE", Path(self.tmp.name) / "imp.jsonl")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)
        settings.update({"agent_provider": "gemini", "agent_api_key": "test-key"})
        self.addCleanup(lambda: settings.reset(["agent_provider", "agent_api_key"]))

    async def _chat(self, client, who=HOST, message="hello"):
        with patch("httpx.AsyncClient") as http:
            http.return_value.__aenter__.return_value = client
            return await agent.chat_with_agent(message, [{"role": "model", "content": "hi"}, {"bad": 1}], who)

    async def test_no_key_warns(self):
        settings.reset(["agent_api_key"])
        with patch.dict("os.environ", {"GEMINI_API_KEY": "", "OPENAI_API_KEY": ""}):
            res = await agent.chat_with_agent("hello", [], HOST)
        self.assertIn("API key", res["reply"])

    async def test_key_goes_in_a_header_and_guest_sees_only_guest_tools(self):
        client = gemini_reply(body={"candidates": [{"content": {"parts": [{"text": "Hi Ann!"}]}}]})
        res = await self._chat(client, ANN)
        self.assertEqual(res["reply"], "Hi Ann!")
        url, kwargs = client.post.call_args[0][0], client.post.call_args[1]
        self.assertNotIn("test-key", url)
        self.assertEqual(kwargs["headers"]["x-goog-api-key"], "test-key")
        offered = {f["name"] for f in kwargs["json"]["tools"][0]["functionDeclarations"]}
        self.assertNotIn("change_setting", offered)
        self.assertIn("guest Ann", kwargs["json"]["systemInstruction"]["parts"][0]["text"])
        self.assertEqual(len(kwargs["json"]["contents"]), 2)   # the malformed history entry was dropped

    async def test_404_tip_and_models_prefix(self):
        settings.update({"agent_model": "models/gemini-3.5-flash"})
        self.addCleanup(lambda: settings.reset(["agent_model"]))
        client = gemini_reply(404, text="not found")
        res = await self._chat(client)
        self.assertIn("models/gemini-3.5-flash:generateContent", client.post.call_args[0][0])
        self.assertNotIn("models/models", client.post.call_args[0][0])
        self.assertIn("was not found", res["reply"])

    async def test_round_limit_gives_a_friendly_reply_and_logs_it(self):
        call = {"candidates": [{"content": {"parts": [{"functionCall": {"name": "get_party_status", "args": {}}}]}}]}
        res = await self._chat(gemini_reply(body=call))
        self.assertIn("more steps than I'm allowed", res["reply"])
        self.assertEqual(len(res["tool_calls"]), 8)
        self.assertTrue(any(i["category"] == "turn_limit_exhausted" for i in agent.list_improvements()))

    def test_openai_types_are_lowercased(self):
        out = llm_openai._lower_types({"type": "OBJECT", "properties": {"n": {"type": "INTEGER"}}})
        self.assertEqual((out["type"], out["properties"]["n"]["type"]), ("object", "integer"))


class TestChatEndpoint(unittest.IsolatedAsyncioTestCase):
    @patch("routers.agent.hub.broadcast", new_callable=AsyncMock)
    @patch("routers.agent.agent.chat_with_agent", new_callable=AsyncMock)
    async def test_both_messages_reach_the_projector(self, chat, broadcast):
        from routers.agent import ChatRequest, chat as endpoint
        chat.return_value = {"reply": "Playing Queen!", "tool_calls": []}
        res = await endpoint(ChatRequest(message="Play Queen"), who=HOST)
        self.assertEqual(res["reply"], "Playing Queen!")
        self.assertIs(chat.call_args[0][2], HOST)   # the tools run as the asker
        sent = [c[0] for c in broadcast.call_args_list]
        self.assertEqual([(m["sender"], m["name"], role) for m, role in sent],
                         [("user", "Hosty", "screen"), ("agent", "DJ Co-Pilot", "screen")])

    def test_guests_need_the_host_to_open_the_chat(self):
        from routers import agent as router
        request = MagicMock()
        with patch("routers.agent.auth.identify", return_value=ANN):
            with self.assertRaises(HTTPException) as closed:
                router._chatter(request)
            self.assertEqual(closed.exception.status_code, 403)
            settings.update({"agent_guest_chat": True})
            try:
                router._last_by_guest.clear()
                self.assertIs(router._chatter(request), ANN)
                with self.assertRaises(HTTPException) as fast:
                    router._chatter(request)
                self.assertEqual(fast.exception.status_code, 429)
            finally:
                settings.reset(["agent_guest_chat"])
        with patch("routers.agent.auth.identify", return_value=Who()):
            with self.assertRaises(HTTPException) as anon:
                router._chatter(request)
            self.assertEqual(anon.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
