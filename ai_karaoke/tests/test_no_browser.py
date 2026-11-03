"""Background fetching (cache warmer -> search -> download) must never open a browser window.

Everything network-facing is mocked: no real search, download or cache is touched.
"""
import asyncio
import os
import unittest
import webbrowser
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from core import no_browser, warmer
from services import downloader, sources

START_SCRIPT = Path(__file__).resolve().parents[2] / "start-karaoke.ps1"


class WarmerOpensNoBrowser(unittest.TestCase):
    def test_warm_round_and_download_never_launch_anything(self):
        hit = {"id": "dQw4w9WgXcQ", "key": "rick astley never gonna give you up"}
        fake_ydl = MagicMock()
        fake_ydl.__enter__.return_value = fake_ydl
        fake_ydl.extract_info.return_value = {"duration": 200, "title": "t"}
        with patch("webbrowser.open") as wb_open, patch("webbrowser.open_new_tab") as wb_tab, \
                patch("subprocess.Popen") as popen, \
                patch.object(warmer, "load_hits", return_value=["Rick Astley - Never Gonna Give You Up"]), \
                patch.object(warmer.search, "search", return_value=[hit]), \
                patch.object(warmer.worker, "submit_warm", AsyncMock()) as submit, \
                patch.object(warmer.asyncio, "sleep", AsyncMock()), \
                patch.object(downloader, "YoutubeDL", return_value=fake_ydl) as ydl_cls, \
                patch.object(downloader.search_filter, "duration_problem", return_value=None):
            handed = asyncio.run(warmer.run_once(count=1))
            with self.assertRaises(downloader.DownloadError):   # no FFmpeg output in a temp dir
                downloader._fetch("dQw4w9WgXcQ", Path(os.environ.get("TEMP", ".")) / "no_browser_test")
        self.assertEqual(handed, ["dQw4w9WgXcQ"])
        submit.assert_awaited_once()
        opts = ydl_cls.call_args.args[0]
        self.assertNotIn("cookiesfrombrowser", opts)
        self.assertNotIn("cookiefile", opts)
        wb_open.assert_not_called()
        wb_tab.assert_not_called()
        popen.assert_not_called()

    def test_ytdlp_base_options_never_read_browser_cookies(self):
        self.assertNotIn("cookiesfrombrowser", sources.BASE_OPTS)
        self.assertNotIn("cookiefile", sources.BASE_OPTS)


class GuardBlocksAndLogs(unittest.TestCase):
    def test_install_refuses_webbrowser_and_url_startfile(self):
        saved = (webbrowser.open, webbrowser.open_new, webbrowser.open_new_tab,
                 getattr(os, "startfile", None), no_browser._installed)
        real_startfile = MagicMock()
        try:
            no_browser._installed = False
            os.startfile = real_startfile
            no_browser.install()
            with self.assertLogs("core.no_browser", "WARNING") as logs:
                self.assertFalse(webbrowser.open("https://example.com"))
                self.assertFalse(webbrowser.open_new_tab("https://example.com"))
                os.startfile("https://example.com")
            self.assertEqual(len(logs.records), 3)
            self.assertIn("Called from", logs.output[0])
            real_startfile.assert_not_called()
            os.startfile(r"C:\some\file.txt")   # plain files still work
            real_startfile.assert_called_once()
        finally:
            webbrowser.open, webbrowser.open_new, webbrowser.open_new_tab = saved[:3]
            if saved[3] is None:
                del os.startfile
            else:
                os.startfile = saved[3]
            no_browser._installed = saved[4]


class StartScriptOpensOnlyWhenAnswered(unittest.TestCase):
    def test_tab_opens_only_after_the_server_answered(self):
        text = START_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("if (-not $answered) { return }", text)
        self.assertEqual(text.count("Start-Process"), 1)
        self.assertLess(text.index("if (-not $answered) { return }"), text.index("Start-Process"))


if __name__ == "__main__":
    unittest.main()
