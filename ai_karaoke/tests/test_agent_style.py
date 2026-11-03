"""set_style and the custom CSS check (core/css_guard.py). Run with KARAOKE_SETTINGS_FILE pointing
at a temp file: these tests change settings."""
import unittest
from unittest.mock import AsyncMock, patch

from core import css_guard, settings
from core.auth import Who
from services import agent
from services.agent import tools_style

HOST = Who(laptop=True, admin=True)
ANN = Who(guest_id=7, name="Ann")


class TestCssGuard(unittest.TestCase):
    def test_plain_css_passes(self):
        css = "body { letter-spacing: .05em; }\n.panel { border: 2px dashed hotpink; }"
        self.assertEqual(css_guard.check(css), css)

    def test_anything_that_loads_or_escapes_is_refused(self):
        for bad in ("body{background:url(https://evil.example/x)}", "body{background:URL ( x )}",
                    "@import 'x.css';", "</style><script>alert(1)</script>", "a{b:\\75 rl(x)}",
                    "a{b:u/**/rl(x)}", "a{b:image-set('x' 1x)}", "a{behavior:x}", "a{-moz-binding:x}",
                    "a{", "x" * 5000):
            with self.assertRaises(ValueError, msg=bad):
                css_guard.check(bad)

    def test_settings_refuse_bad_css_and_keep_line_breaks(self):
        with self.assertRaises(ValueError):
            settings.update({"custom_css": "body{background:url(x)}"})
        settings.update({"custom_css": "body {\n  color: red;\n}"})
        self.assertEqual(settings.get("custom_css"), "body {\n  color: red;\n}")
        settings.reset(["custom_css"])

    def test_colour_must_be_hex(self):
        with self.assertRaises(ValueError):
            settings.update({"style_accent_hex": "red; x"})
        settings.update({"style_accent_hex": "#ff00aa"})
        settings.reset(["style_accent_hex"])


class TestSetStyle(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        patcher = patch("services.agent.tools_style.hub.broadcast", new_callable=AsyncMock)
        self.broadcast = patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(lambda: settings.reset([*tools_style.STYLE_KEYS, "theme", "agent_guest_style"]))
        tools_style._last_by_guest.clear()

    async def test_host_restyles_in_one_call_and_resets(self):
        res = await agent.execute_tool("set_style", {"theme": "club", "font": "rounded", "glow": 60,
                                                     "title_effect": "rainbow", "custom_css": ".panel{opacity:.9}"}, HOST)
        self.assertEqual(res["status"], "ok")
        self.assertEqual((settings.get("style_font"), settings.get("style_glow")), ("rounded", 60))
        self.broadcast.assert_awaited_with({"type": "settings"})
        await agent.execute_tool("set_style", {"reset": True}, HOST)
        self.assertEqual((settings.get("style_font"), settings.get("custom_css")), ("theme", ""))

    async def test_all_or_nothing(self):
        res = await agent.execute_tool("set_style", {"font": "mono", "custom_css": "@import 'x';"}, HOST)
        self.assertIn("error", res)
        self.assertEqual(settings.get("style_font"), "theme")

    async def test_guests_only_when_allowed_and_once_a_minute(self):
        self.assertIn("Only the host", (await agent.execute_tool("set_style", {"glow": 40}, ANN))["error"])
        settings.update({"agent_guest_style": True})
        self.assertIn("set_style", {t["name"] for t in agent.tools_for(ANN)})
        self.assertEqual((await agent.execute_tool("set_style", {"glow": 40}, ANN))["status"], "ok")
        self.assertIn("a minute", (await agent.execute_tool("set_style", {"glow": 80}, ANN))["error"])
        self.assertEqual(settings.get("style_glow"), 40)


if __name__ == "__main__":
    unittest.main()
