"""Unit tests for playlist management, low-priority queue playback, promotion, and agent tools."""
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from core.playlist_manager import PlaylistManager, normalize_song, parse_song_text
from core.queue_manager import QueueManager, queue
from core import auth, settings
from main import app
from services import agent


class TestPlaylistManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.pm = PlaylistManager(directory=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_normalize_and_parse(self):
        t, a = parse_song_text("Queen - Bohemian Rhapsody")
        self.assertEqual(t, "Bohemian Rhapsody")
        self.assertEqual(a, "Queen")

        s1 = normalize_song("Oasis - Wonderwall")
        self.assertEqual(s1["title"], "Wonderwall")
        self.assertEqual(s1["artist"], "Oasis")
        self.assertEqual(s1["query"], "Oasis - Wonderwall")

        s2 = normalize_song({"title": "Yellow", "channel": "Coldplay", "id": "12345"})
        self.assertEqual(s2["title"], "Yellow")
        self.assertEqual(s2["artist"], "Coldplay")
        self.assertEqual(s2["song_id"], "12345")

    def test_builtin_playlists(self):
        weekly = self.pm.get_weekly_hits()
        self.assertEqual(weekly["id"], "weekly_hits")
        self.assertTrue(weekly["is_built_in"])
        self.assertGreater(len(weekly["songs"]), 0)

        top = self.pm.get_top_hits()
        self.assertEqual(top["id"], "top_hits")
        self.assertTrue(top["is_built_in"])
        self.assertGreater(len(top["songs"]), 0)

        playlists = self.pm.list_playlists()
        ids = [p["id"] for p in playlists]
        self.assertIn("weekly_hits", ids)
        self.assertIn("top_hits", ids)

    def test_custom_playlist_crud(self):
        created = self.pm.create_playlist(
            name="Rock Anthems",
            songs=["Queen - Don't Stop Me Now", "Bon Jovi - Livin' On A Prayer"],
            description="High energy rock",
            playlist_id="rock_anthems",
        )
        self.assertEqual(created["id"], "rock_anthems")
        self.assertEqual(created["name"], "Rock Anthems")
        self.assertEqual(len(created["songs"]), 2)

        # Get
        fetched = self.pm.get_playlist("rock_anthems")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["name"], "Rock Anthems")
        self.assertEqual(len(fetched["songs"]), 2)

        # Update - append song
        updated = self.pm.update_playlist(
            "rock_anthems",
            songs=["The Killers - Mr. Brightside"],
            action="add_songs",
        )
        self.assertEqual(len(updated["songs"]), 3)

        # Update - remove song
        updated2 = self.pm.update_playlist(
            "rock_anthems",
            songs=["Bon Jovi - Livin' On A Prayer"],
            action="remove_songs",
        )
        self.assertEqual(len(updated2["songs"]), 2)
        queries = [s["query"] for s in updated2["songs"]]
        self.assertNotIn("Bon Jovi - Livin' On A Prayer", queries)

        # Delete
        ok = self.pm.delete_playlist("rock_anthems")
        self.assertTrue(ok)
        self.assertIsNone(self.pm.get_playlist("rock_anthems"))

    def test_cannot_modify_or_delete_builtins(self):
        with self.assertRaises(ValueError):
            self.pm.create_playlist("Weekly", ["a - b"], playlist_id="weekly_hits")
        with self.assertRaises(ValueError):
            self.pm.update_playlist("weekly_hits", name="New Name")
        with self.assertRaises(ValueError):
            self.pm.delete_playlist("weekly_hits")


class TestQueuePlaylistIntegration(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.qm = QueueManager()
        self.qm.entries = []
        self.qm.current = None
        self.qm.played = []
        self.qm.active_playlist = None

    async def test_start_and_stop_playlist(self):
        with patch.object(self.qm, "broadcast_state", new=AsyncMock()), \
             patch.object(self.qm, "_changed", new=AsyncMock()):
            snap = await self.qm.start_playlist("weekly_hits")
            self.assertIsNotNone(self.qm.active_playlist)
            self.assertEqual(self.qm.active_playlist["id"], "weekly_hits")
            self.assertGreater(len(self.qm.active_playlist["queue"]), 0)

            stopped = await self.qm.stop_playlist()
            self.assertTrue(stopped)
            self.assertIsNone(self.qm.active_playlist)

    async def test_less_priority_queue_playback(self):
        """User queue songs always play before active playlist songs."""
        with patch.object(self.qm, "broadcast_state", new=AsyncMock()), \
             patch.object(self.qm, "_changed", new=AsyncMock()):
            await self.qm.start_playlist("weekly_hits")

            # Add a ready user song
            user_entry = {
                "uid": "u1",
                "song_id": "sid_user",
                "title": "User Song",
                "singer": "Alice",
                "status": "ready",
                "is_playlist": False,
            }
            self.qm.entries.append(user_entry)

            # queue.next() should pick user song first
            picked = await self.qm.next()
            self.assertEqual(picked["uid"], "u1")
            self.assertEqual(picked["title"], "User Song")
            self.assertFalse(picked.get("is_playlist", False))

            # Now user queue is empty: queue.next() should pick from active playlist
            # Mock _resolve_playlist_item to return a ready track
            mock_resolved = {
                "song_id": "sid_pl",
                "title": "Bohemian Rhapsody",
                "channel": "Queen",
                "duration": 350,
                "thumbnail": "",
                "ready": True,
            }
            with patch.object(self.qm, "_resolve_playlist_item", new=AsyncMock(return_value=mock_resolved)):
                pl_picked = await self.qm.next()
                self.assertIsNotNone(pl_picked)
                self.assertTrue(pl_picked.get("is_playlist"))
                self.assertEqual(pl_picked["song_id"], "sid_pl")

    async def test_promote_song_on_user_queue(self):
        """If user adds a song in the currently playing playlist, it gets added to user queue
        and removed from its original position in the playlist queue."""
        with patch.object(self.qm, "broadcast_state", new=AsyncMock()), \
             patch.object(self.qm, "_changed", new=AsyncMock()):
            self.qm.active_playlist = {
                "id": "test_pl",
                "name": "Test Playlist",
                "queue": [
                    {"query": "Queen - Bohemian Rhapsody", "title": "Bohemian Rhapsody", "artist": "Queen", "song_id": "sid_queen"},
                    {"query": "Oasis - Wonderwall", "title": "Wonderwall", "artist": "Oasis", "song_id": "sid_oasis"},
                    {"query": "ABBA - Dancing Queen", "title": "Dancing Queen", "artist": "ABBA", "song_id": "sid_abba"},
                ],
                "played": [],
                "loop": False,
                "enabled": True,
            }

            # User queues "Oasis - Wonderwall" (position 1 in playlist)
            entry = await self.qm.add(
                song_id="sid_oasis",
                title="Wonderwall",
                channel="Oasis",
                duration=260,
                singer="Bob",
            )

            # 1. Added to user queue
            self.assertEqual(len(self.qm.entries), 1)
            self.assertEqual(self.qm.entries[0]["title"], "Wonderwall")
            self.assertEqual(self.qm.entries[0]["singer"], "Bob")
            self.assertFalse(self.qm.entries[0]["is_playlist"])

            # 2. Removed from playlist queue
            pl_remaining = [s["song_id"] for s in self.qm.active_playlist["queue"]]
            self.assertEqual(pl_remaining, ["sid_queen", "sid_abba"])
            self.assertNotIn("sid_oasis", pl_remaining)

    async def test_setting_disabled_does_not_remove_from_playlist(self):
        """When playlist_promote_on_user_queue is disabled, song is not removed from playlist."""
        with patch.object(self.qm, "broadcast_state", new=AsyncMock()), \
             patch.object(self.qm, "_changed", new=AsyncMock()), \
             patch.object(settings, "get", return_value=False):
            self.qm.active_playlist = {
                "id": "test_pl",
                "name": "Test Playlist",
                "queue": [
                    {"query": "Oasis - Wonderwall", "title": "Wonderwall", "artist": "Oasis", "song_id": "sid_oasis"},
                ],
                "played": [],
                "enabled": True,
            }

            await self.qm.add(
                song_id="sid_oasis",
                title="Wonderwall",
                channel="Oasis",
                duration=260,
                singer="Bob",
            )

            # Not removed because setting is False
            self.assertEqual(len(self.qm.active_playlist["queue"]), 1)


    async def test_autodj_auto_start_on_empty_queue(self):
        # When queue.next() is called with an empty queue, no active playlist, and autodj_auto_start=True
        with patch("core.settings.get", side_effect=lambda k, d=None: True if k == "autodj_auto_start" else ("weekly_hits" if k == "autodj_default_playlist" else d)):
            with patch.object(self.qm, "start_playlist", new=AsyncMock()) as mock_start:
                mock_start.side_effect = lambda pid: setattr(self.qm, "active_playlist", {"name": "Weekly Hits", "queue": [], "enabled": True})
                self.qm.entries = []
                self.qm.active_playlist = None
                self.qm._user_stopped_playlist = False
                await self.qm.next()
                mock_start.assert_awaited_once_with("weekly_hits")

    async def test_autodj_respects_user_stop(self):
        # If user explicitly stopped playlist, next() must not auto-start
        with patch("core.settings.get", side_effect=lambda k, d=None: True if k == "autodj_auto_start" else ("weekly_hits" if k == "autodj_default_playlist" else d)):
            with patch.object(self.qm, "start_playlist", new=AsyncMock()) as mock_start:
                self.qm.entries = []
                self.qm.active_playlist = None
                self.qm._user_stopped_playlist = True
                await self.qm.next()
                mock_start.assert_not_awaited()

    async def test_autodj_unready_song_not_skipped_by_worker(self):
        """When an unready Auto-DJ song is popped, it must be in current immediately
        so that queue.has_song(sid) is True and worker_jobs does not skip it."""
        from core import worker_jobs
        with patch.object(self.qm, "broadcast_state", new=AsyncMock()), \
             patch.object(self.qm, "_changed", new=AsyncMock()), \
             patch("core.cache_manager.is_ready", return_value=False), \
             patch("core.worker.worker.submit", new_callable=AsyncMock) as mock_submit:
            self.qm.active_playlist = {
                "id": "test_pl",
                "name": "Test Playlist",
                "queue": [{"query": "Queen - Radio Ga Ga", "title": "Radio Ga Ga", "artist": "Queen", "song_id": "sid_queen"}],
                "played": [],
                "loop": False,
                "enabled": True,
            }
            self.qm.entries = []
            mock_resolved = {
                "song_id": "sid_queen",
                "title": "Radio Ga Ga",
                "channel": "Queen",
                "duration": 340,
                "thumbnail": "",
                "ready": False,
            }
            with patch.object(self.qm, "_resolve_playlist_item", new=AsyncMock(return_value=mock_resolved)):
                pl_picked = await self.qm.next()
                self.assertIsNotNone(pl_picked)
                self.assertEqual(pl_picked["song_id"], "sid_queen")
                self.assertEqual(pl_picked["status"], "queued")
                # Crucial assertion: queue.has_song must return True
                self.assertTrue(self.qm.has_song("sid_queen"))
                # Crucial assertion: worker.submit was called
                mock_submit.assert_awaited_with("sid_queen")
                # dispatch must not skip it
                with patch("core.worker_jobs._process", new_callable=AsyncMock) as mock_proc, \
                     patch("core.worker_jobs.queue", self.qm):
                    res = await worker_jobs.dispatch(MagicMock(), "process", "sid_queen")
                    self.assertTrue(res)
                    mock_proc.assert_awaited_once()


class TestPlaylistsApi(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_list_and_get_playlists(self):
        res = self.client.get("/api/playlists")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("playlists", data)
        self.assertTrue(any(p["id"] == "weekly_hits" for p in data["playlists"]))

        # Get specific
        res_weekly = self.client.get("/api/playlists/weekly_hits")
        self.assertEqual(res_weekly.status_code, 200)
        self.assertIn("songs", res_weekly.json())

        # Nonexistent
        res_404 = self.client.get("/api/playlists/nonexistent_12345")
        self.assertEqual(res_404.status_code, 404)

    def test_crud_and_play_api(self):
        admin_who = auth.Who(admin=True, laptop=True, guest_id=None, name="Host")
        with patch("core.auth.identify", return_value=admin_who):
            # Create
            res_create = self.client.post("/api/playlists", json={
                "name": "Api Test Playlist",
                "songs": ["Queen - Radio Ga Ga", "A-ha - Take On Me"],
                "description": "Test playlist description",
            })
            self.assertEqual(res_create.status_code, 201)
            created = res_create.json()
            pid = created["id"]

            try:
                # Update
                res_up = self.client.put(f"/api/playlists/{pid}", json={
                    "name": "Api Test Playlist Updated",
                    "songs": ["Toto - Africa"],
                    "action": "add_songs",
                })
                self.assertEqual(res_up.status_code, 200)
                self.assertEqual(len(res_up.json()["songs"]), 3)

                # Play
                with patch("core.queue_manager.queue.start_playlist", new=AsyncMock(return_value={"id": pid})):
                    res_play = self.client.post(f"/api/playlists/{pid}/play")
                    self.assertEqual(res_play.status_code, 200)

                # Stop
                with patch("core.queue_manager.queue.stop_playlist", new=AsyncMock(return_value=True)):
                    res_stop = self.client.post("/api/playlists/stop")
                    self.assertEqual(res_stop.status_code, 200)
            finally:
                # Delete
                res_del = self.client.delete(f"/api/playlists/{pid}")
                self.assertEqual(res_del.status_code, 200)


class TestAgentPlaylistTools(unittest.IsolatedAsyncioTestCase):
    async def test_agent_tools(self):
        # 1. list_playlists
        res_list = await agent.execute_tool("list_playlists", {})
        self.assertIn("playlists", res_list)
        self.assertGreater(len(res_list["playlists"]), 0)

        # 2. create_playlist
        res_create = await agent.execute_tool("create_playlist", {
            "name": "Disco Night",
            "songs": ["ABBA - Dancing Queen", "Bee Gees - Stayin' Alive"],
            "description": "70s classics",
        })
        self.assertEqual(res_create.get("status"), "ok")
        created_id = res_create["playlist"]["id"]

        # 3. get_playlist
        res_get = await agent.execute_tool("get_playlist", {"playlist_id": created_id})
        self.assertEqual(res_get.get("name"), "Disco Night")
        self.assertEqual(len(res_get.get("songs", [])), 2)

        # 4. update_playlist
        res_up = await agent.execute_tool("update_playlist", {
            "playlist_id": created_id,
            "songs": ["Donna Summer - Hot Stuff"],
            "action": "add_songs",
        })
        self.assertEqual(res_up.get("status"), "ok")
        self.assertEqual(len(res_up["playlist"]["songs"]), 3)

        # 5. play_playlist
        with patch("core.queue_manager.queue.start_playlist", new=AsyncMock(return_value={"id": created_id})):
            res_play = await agent.execute_tool("play_playlist", {"playlist_id": created_id})
            self.assertEqual(res_play.get("status"), "ok")

        # 6. stop_playlist
        with patch("core.queue_manager.queue.stop_playlist", new=AsyncMock(return_value=True)):
            res_stop = await agent.execute_tool("stop_playlist", {})
            self.assertEqual(res_stop.get("status"), "ok")

        # 7. delete_playlist
        res_del = await agent.execute_tool("delete_playlist", {"playlist_id": created_id})
        self.assertEqual(res_del.get("status"), "ok")


if __name__ == "__main__":
    unittest.main()
