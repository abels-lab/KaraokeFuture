"""Cache overflow edge cases and lyrics that outlive the cache:
- the next Auto-DJ songs are protected like queued ones;
- a nearly full disk makes eviction go below the limit, and downloads / warm-ups refuse;
- "stuck" (over the limit with only protected songs) is reported, not fought;
- lyrics found online live outside the cache, survive eviction, and old copies move out.
Each test uses its own temporary cache and lyrics folders, never the real ones."""
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from config import MIN_FREE_DISK_BYTES, ONLINE_LYRICS_FILE, ULTRASTAR_FILE
from core import cache_admin, cache_files, cache_heal, cache_manager, warm_budget
from core.queue_store import QueueStore
from test_cache_store import CacheTestCase, make_song


class TestAutoDJProtected(unittest.TestCase):
    def test_next_playlist_songs_are_protected(self):
        store = QueueStore.__new__(QueueStore)
        store.entries, store.current, store.played = [{"song_id": "queued00000"}], None, []
        store.active_playlist = {"queue": [{"song_id": "next0000000"}, "Unresolved - Song",
                                           {"song_id": "later000000"}]}
        self.assertEqual(store.protected_ids(), {"queued00000", "next0000000"})
        store.active_playlist = None
        self.assertEqual(store.protected_ids(), {"queued00000"})


class TestDiskRoom(CacheTestCase):
    def _disk(self, base: int):
        """Fake disk: `base` bytes free when the cache is empty."""
        return patch("core.cache_files.disk_free", side_effect=lambda _p: base - cache_manager.total_size())

    def test_low_disk_evicts_below_the_limit(self):
        now = time.time()
        for i, sid in enumerate(("old00000000", "new00000000")):
            make_song(self.root, sid, size=100_000, last_accessed=now + i)
        song = cache_manager.folder_size(self.root / "old00000000")
        with self._disk(MIN_FREE_DISK_BYTES + 2 * song + 10), patch("core.cache_manager.settings.get", return_value=100):
            self.assertEqual(cache_manager.ensure_space(headroom=song), ["old00000000"])
            self.assertTrue(cache_manager.disk_room(song))

    def test_stuck_when_only_protected_songs_are_left(self):
        make_song(self.root, "queued00000")
        with patch("core.cache_manager.settings.get", return_value=0.0), \
                patch("core.cache_admin.protected", return_value={"queued00000"}):
            with self.assertLogs("core.cache_manager", "WARNING"):
                self.assertEqual(cache_manager.ensure_space(protect={"queued00000"}, headroom=0), [])
            self.assertTrue(cache_admin.stats()["stuck"])
        self.assertEqual(cache_manager.song_ids(), {"queued00000"})

    def test_download_refused_when_disk_is_full(self):
        from services import downloader
        with patch("core.cache_files.disk_free", return_value=0), \
                patch("core.cache_manager.ensure_space", return_value=[]):
            with self.assertRaisesRegex(downloader.DownloadError, "disk is almost full"):
                downloader.download("aaaaaaaaaaa")
            self.assertFalse(warm_budget.make_room(set()))
            self.assertTrue(cache_admin.stats()["disk_low"])


class TestKeptLyrics(CacheTestCase):
    def setUp(self):
        super().setUp()
        self._lyrics = tempfile.TemporaryDirectory()
        self.store = Path(self._lyrics.name)
        self._lp = patch("core.cache_files.LYRICS_STORE_DIR", self.store)
        self._lp.start()

    def tearDown(self):
        self._lp.stop()
        self._lyrics.cleanup()
        super().tearDown()

    def test_found_lyrics_survive_eviction_and_clear(self):
        from services import lyrics_source
        make_song(self.root, "aaaaaaaaaaa", warmed_at=time.time())
        with patch("services.lyrics_source.fetch_online", return_value="[00:01.00] la la"), \
                patch("services.lyrics_source.lrclib.fits", return_value=True):
            self.assertEqual(lyrics_source.online_for("aaaaaaaaaaa", "Song", "Artist", 200), "[00:01.00] la la")
        self.assertFalse((self.root / "aaaaaaaaaaa" / ONLINE_LYRICS_FILE).exists())   # not in the cache
        with patch("core.cache_admin.protected", return_value=set()):
            cache_admin.clear("all")
        self.assertEqual(cache_manager.song_ids(), set())
        with patch("services.lyrics_source.fetch_online", side_effect=AssertionError("searched again")), \
                patch("services.lyrics_source.lrclib.fits", return_value=True):   # the same version is found
            self.assertEqual(lyrics_source.online_for("aaaaaaaaaaa", "Song", "Artist", 200), "[00:01.00] la la")
        lyrics_source.forget_found("aaaaaaaaaaa")
        self.assertFalse(cache_files.kept_file("aaaaaaaaaaa", ONLINE_LYRICS_FILE).exists())

    def test_heal_moves_old_copies_out_of_the_cache(self):
        folder = make_song(self.root, "bbbbbbbbbbb")
        (folder / ONLINE_LYRICS_FILE).write_text("old lrc", encoding="utf-8")
        (folder / ULTRASTAR_FILE).write_text("#TITLE:x", encoding="utf-8")
        cache_files.write_atomic(cache_files.kept_file("bbbbbbbbbbb", ULTRASTAR_FILE), "#TITLE:newer")
        self.assertEqual(cache_heal.heal()["lyrics_kept"], 2)
        self.assertFalse((folder / ONLINE_LYRICS_FILE).exists() or (folder / ULTRASTAR_FILE).exists())
        self.assertEqual(cache_files.kept_file("bbbbbbbbbbb", ONLINE_LYRICS_FILE).read_text("utf-8"), "old lrc")
        self.assertEqual(cache_files.kept_file("bbbbbbbbbbb", ULTRASTAR_FILE).read_text("utf-8"), "#TITLE:newer")
        self.assertTrue(cache_manager.is_ready("bbbbbbbbbbb"))


if __name__ == "__main__":
    unittest.main()
