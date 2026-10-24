import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from core.queue_manager import QueueManager
import routers.ws as ws_router


class TestHostAuthority(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.qm = QueueManager()
        self.qm.current = {
            "uid": "test12345678",
            "song_id": "song_test_id",
            "singer": "Singer A",
            "title": "Title A",
            "channel": "Channel A",
            "duration": 180,
            "status": "ready",
        }

    def test_initial_playback_state(self):
        qm = QueueManager()
        self.assertEqual(qm.playback["time"], 0.0)
        self.assertEqual(qm.playback["duration"], 0.0)
        self.assertTrue(qm.playback["paused"])

    def test_update_playback_matching_uid(self):
        self.qm.update_playback("test12345678", 45.5, 180.0, False)
        self.assertEqual(self.qm.playback["uid"], "test12345678")
        self.assertEqual(self.qm.playback["time"], 45.5)
        self.assertEqual(self.qm.playback["duration"], 180.0)
        self.assertFalse(self.qm.playback["paused"])
        self.assertGreater(self.qm.playback["updated_at"], 0)

    def test_update_playback_ignores_stale_uid(self):
        self.qm.update_playback("other_uid", 50.0, 180.0, False)
        self.assertEqual(self.qm.playback["time"], 0.0)
        self.assertTrue(self.qm.playback["paused"])

    def test_update_playback_when_no_current(self):
        self.qm.current = None
        self.qm.update_playback("test12345678", 50.0, 180.0, False)
        self.assertEqual(self.qm.playback["time"], 0.0)

    def test_snapshot_includes_playback(self):
        self.qm.update_playback("test12345678", 22.4, 180.0, False)
        snap = self.qm.snapshot()
        self.assertIn("playback", snap)
        self.assertEqual(snap["playback"]["time"], 22.4)
        self.assertEqual(snap["now_playing"]["playback"]["time"], 22.4)

    def test_save_and_restore_playback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_file = Path(tmpdir) / "queue.json"
            with patch("config.QUEUE_FILE", queue_file):
                self.qm.update_playback("test12345678", 65.2, 180.0, False)
                self.qm._save()

                self.assertTrue(queue_file.exists())
                with open(queue_file, "r", encoding="utf-8") as fh:
                    saved = json.load(fh)
                self.assertIn("playback", saved)
                self.assertEqual(saved["playback"]["time"], 65.2)

                # Now restore into a fresh QueueManager
                new_qm = QueueManager()
                new_qm.restore()
                self.assertEqual(new_qm.current["uid"], "test12345678")
                self.assertEqual(new_qm.playback["time"], 65.2)
                self.assertEqual(new_qm.playback["uid"], "test12345678")

    def test_restore_without_playback_in_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_file = Path(tmpdir) / "queue.json"
            with open(queue_file, "w", encoding="utf-8") as fh:
                json.dump({"entries": [], "current": None}, fh)

            with patch("config.QUEUE_FILE", queue_file):
                new_qm = QueueManager()
                new_qm.restore()
                self.assertIsNone(new_qm.current)
                self.assertEqual(new_qm.playback["time"], 0.0)
                self.assertTrue(new_qm.playback["paused"])

    async def test_next_resets_playback(self):
        self.qm.entries = [{
            "uid": "next12345678",
            "song_id": "next_song_id",
            "singer": "Singer B",
            "title": "Title B",
            "channel": "Channel B",
            "duration": 200,
            "status": "ready",
        }]
        self.qm.update_playback("test12345678", 99.0, 180.0, False)
        self.assertEqual(self.qm.playback["time"], 99.0)

        with patch("core.cache_manager.touch"):
            with patch("core.hub.hub.broadcast", new_callable=AsyncMock):
                await self.qm.next()

        self.assertEqual(self.qm.current["uid"], "next12345678")
        self.assertEqual(self.qm.playback["uid"], "next12345678")
        self.assertEqual(self.qm.playback["time"], 0.0)
        self.assertTrue(self.qm.playback["paused"])

    async def test_previous_resets_playback(self):
        self.qm.played = [{
            "uid": "prev12345678",
            "song_id": "prev_song_id",
            "singer": "Singer Prev",
            "title": "Title Prev",
            "channel": "Channel Prev",
            "duration": 150,
            "status": "ready",
        }]
        with patch("core.hub.hub.broadcast", new_callable=AsyncMock):
            await self.qm.previous()

        self.assertEqual(self.qm.current["uid"], "prev12345678")
        self.assertEqual(self.qm.playback["uid"], "prev12345678")
        self.assertEqual(self.qm.playback["time"], 0.0)

    async def test_ws_playback_handler(self):
        mock_ws = AsyncMock()
        with patch.object(ws_router.queue, "update_playback") as mock_update:
            with patch.object(ws_router.hub, "broadcast", new_callable=AsyncMock) as mock_broadcast:
                await ws_router._handle(mock_ws, "tv", {
                    "type": "playback",
                    "uid": "uid123",
                    "time": 30.5,
                    "duration": 180.0,
                    "paused": False,
                })
                mock_update.assert_called_once_with("uid123", 30.5, 180.0, False)
                mock_broadcast.assert_called_once_with({
                    "type": "playback",
                    "uid": "uid123",
                    "time": 30.5,
                    "duration": 180.0,
                    "paused": False,
                }, "remote", "screen")

    async def test_ws_sync_playback_handler_duration_fallback(self):
        mock_ws = AsyncMock()
        with patch.object(ws_router.queue, "current", {"uid": "uid123", "duration": 210.0}):
            with patch.object(ws_router.queue, "update_playback") as mock_update:
                with patch.object(ws_router.hub, "broadcast", new_callable=AsyncMock) as mock_broadcast:
                    await ws_router._handle(mock_ws, "tv", {
                        "type": "sync_playback",
                        "uid": "uid123",
                        "time": 42.0,
                        "duration": 0,
                        "paused": False,
                    })
                    mock_update.assert_called_once_with("uid123", 42.0, 210.0, False)
                    mock_broadcast.assert_called_once_with({
                        "type": "playback",
                        "uid": "uid123",
                        "time": 42.0,
                        "duration": 210.0,
                        "paused": False,
                    }, "remote", "screen")


if __name__ == "__main__":
    unittest.main()
