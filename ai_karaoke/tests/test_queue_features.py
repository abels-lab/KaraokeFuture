"""Test new queue features:
- Previous and next song navigation with history preservation
- Drag & drop reordering (move_to arbitrary index)
- Already played songs tracking
- Re-queueing played songs back into upcoming queue
- Selecting and immediately playing any played song
- Worker and JobQueue enqueuing & processing when empty
"""
import unittest
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch, AsyncMock
from core.queue_manager import QueueManager
from core.jobs import JobQueue, HIGH, LOW
from core.worker import Worker


class TestQueueFeatures(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.queue_patcher = patch("config.QUEUE_FILE", Path(self.tmp_dir.name) / "queue.json")
        self.queue_patcher.start()
        self.q = QueueManager()

    def tearDown(self):
        self.queue_patcher.stop()
        self.tmp_dir.cleanup()

    def test_drag_reorder_move_to(self):
        async def run():
            e1 = await self.q.add("id111111111", "Song 1", "Artist 1", 200, "Singer 1")
            e2 = await self.q.add("id222222222", "Song 2", "Artist 2", 200, "Singer 2")
            e3 = await self.q.add("id333333333", "Song 3", "Artist 3", 200, "Singer 3")
            e4 = await self.q.add("id444444444", "Song 4", "Artist 4", 200, "Singer 4")

            # Move e4 to top (index 0)
            res = await self.q.move_to(e4["uid"], 0)
            self.assertTrue(res)
            self.assertEqual([e["uid"] for e in self.q.entries], [e4["uid"], e1["uid"], e2["uid"], e3["uid"]])

            # Move e4 from index 0 to index 2
            res = await self.q.move_to(e4["uid"], 2)
            self.assertTrue(res)
            self.assertEqual([e["uid"] for e in self.q.entries], [e1["uid"], e2["uid"], e4["uid"], e3["uid"]])

            # Move e1 from index 0 to last position (index 3)
            res = await self.q.move_to(e1["uid"], 3)
            self.assertTrue(res)
            self.assertEqual([e["uid"] for e in self.q.entries], [e2["uid"], e4["uid"], e3["uid"], e1["uid"]])

        asyncio.run(run())

    def test_played_history_and_previous_navigation(self):
        async def run():
            e1 = await self.q.add("id111111111", "Song A", "Artist A", 200, "Singer A")
            e2 = await self.q.add("id222222222", "Song B", "Artist B", 200, "Singer B")
            e3 = await self.q.add("id333333333", "Song C", "Artist C", 200, "Singer C")
            for e in self.q.entries:
                e["status"] = "ready"

            # 1. Play first song
            n1 = await self.q.next()
            self.assertEqual(n1["uid"], e1["uid"])
            self.assertEqual(self.q.current["uid"], e1["uid"])
            self.assertEqual(len(self.q.played), 0)

            # 2. Advance to second song: first song saved to played
            n2 = await self.q.next()
            self.assertEqual(n2["uid"], e2["uid"])
            self.assertEqual(self.q.current["uid"], e2["uid"])
            self.assertEqual(len(self.q.played), 1)
            self.assertEqual(self.q.played[0]["uid"], e1["uid"])

            # 3. Mistakenly skipped! Hit previous to go back to Song A
            prev = await self.q.previous()
            self.assertEqual(prev["uid"], e1["uid"])
            self.assertEqual(self.q.current["uid"], e1["uid"])
            self.assertEqual(len(self.q.played), 0)
            # Song B is safely placed back at the beginning of the queue
            self.assertEqual(self.q.entries[0]["uid"], e2["uid"])

            # 4. Advance through B and C
            await self.q.next() # plays B, A goes to played
            await self.q.next() # plays C, B goes to played
            self.assertEqual(self.q.current["uid"], e3["uid"])
            self.assertEqual([p["uid"] for p in self.q.played], [e1["uid"], e2["uid"]])

            # 5. Host selects Song A from history to play now
            res = await self.q.play_played(e1["uid"])
            self.assertEqual(res["uid"], e1["uid"])
            self.assertEqual(self.q.current["uid"], e1["uid"])
            self.assertEqual([p["uid"] for p in self.q.played], [e2["uid"]])
            # Current (C) was pushed back to entries[0]
            self.assertEqual(self.q.entries[0]["uid"], e3["uid"])

            # 6. Requeue Song B back to upcoming queue
            req = await self.q.requeue(e2["uid"])
            self.assertEqual(req["uid"], e2["uid"])
            self.assertEqual(len(self.q.played), 0)
            self.assertTrue(any(e["uid"] == e2["uid"] for e in self.q.entries))

        asyncio.run(run())

    def test_snapshot_structure(self):
        snap = self.q.snapshot()
        self.assertIn("now_playing", snap)
        self.assertIn("queue", snap)
        self.assertIn("played", snap)
        self.assertIn("tv_connected", snap)
        self.assertIn("screens", snap)

    def test_worker_enqueues_and_processes_when_jobqueue_starts_empty(self):
        async def run():
            jq = JobQueue()
            self.assertEqual(len(jq), 0)
            self.assertTrue(bool(jq))

            w = Worker()
            w.start()
            try:
                with patch("core.cache_manager.is_ready", return_value=False), \
                     patch("core.worker_jobs.dispatch", new_callable=AsyncMock, return_value=True) as mock_dispatch:
                    await w.submit("test_song_1")
                    await w.submit("test_song_2")
                    await asyncio.sleep(0.05)
                    self.assertEqual(mock_dispatch.call_count, 2)
                    self.assertEqual(w.backlog(), {"high": 0, "low": 0})
                    self.assertEqual(w.stages, {})
            finally:
                await w.stop()

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
