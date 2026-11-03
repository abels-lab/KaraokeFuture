"""Song cache repair at startup (core/cache_heal.py) and the host cache tools (core/cache_admin.py,
routers/cache.py). Each test uses its own temporary cache folder, never the real cache."""
import time
import unittest
from unittest.mock import patch

from config import INSTRUMENTAL_FILE, LYRICS_FILE, MELODY_FILE, ORIGINAL_FILE, VOCALS_FILE
from core import auth, cache_admin, cache_heal, cache_manager
from test_cache_store import CacheTestCase, make_song


class TestHeal(CacheTestCase):
    def test_leftovers_are_removed_and_good_files_kept(self):
        folder = make_song(self.root, "aaaaaaaaaaa")
        junk = ["meta.json.123-456.tmp", "melody.tmp", "video.mp4.part", "video.mp4.ytdl", "original.webm",
                "original_(Vocals)_model_bs_roformer.wav", "original_(Instrumental)_model.wav", "original.temp.wav"]
        for name in junk:
            (folder / name).write_bytes(b"x" * 100)
        (folder / "video.mp4").write_bytes(b"v" * 100)
        report = cache_heal.heal()
        self.assertEqual(report["leftovers"], len(junk))
        self.assertGreaterEqual(report["freed"], 100 * len(junk))
        self.assertEqual({p.name for p in folder.iterdir()},
                         {VOCALS_FILE, INSTRUMENTAL_FILE, LYRICS_FILE, "meta.json", "video.mp4"})
        self.assertTrue(cache_manager.is_ready("aaaaaaaaaaa"))

    def test_corrupt_json_and_empty_wav_are_removed(self):
        folder = make_song(self.root, "bbbbbbbbbbb")
        (folder / MELODY_FILE).write_text('{"notes": [', encoding="utf-8")
        (folder / LYRICS_FILE).write_text('[{"text": "half', encoding="utf-8")
        (folder / VOCALS_FILE).write_bytes(b"")
        self.assertEqual(cache_heal.heal()["broken"], 3)
        self.assertFalse((folder / MELODY_FILE).exists())
        self.assertFalse(cache_manager.is_ready("bbbbbbbbbbb"))
        self.assertTrue((folder / INSTRUMENTAL_FILE).exists())

    def test_ready_song_with_lost_meta_is_kept(self):
        folder = make_song(self.root, "ccccccccccc")
        (folder / "meta.json").write_text("{not json", encoding="utf-8")
        self.assertEqual(cache_heal.heal()["meta_rebuilt"], 1)
        self.assertTrue(cache_manager.is_ready("ccccccccccc"))
        self.assertEqual(cache_heal.purge_incomplete(), [])

    def test_truncated_download_is_removed_finished_one_kept(self):
        for sid, status in (("ddddddddddd", None), ("eeeeeeeeeee", "downloaded")):
            (self.root / sid).mkdir()
            (self.root / sid / ORIGINAL_FILE).write_bytes(b"\0" * 1000)
            cache_manager.write_meta(sid, {"id": sid, **({"status": status} if status else {})})
        self.assertEqual(cache_heal.heal()["partial_downloads"], 1)
        self.assertFalse((self.root / "ddddddddddd" / ORIGINAL_FILE).exists())
        self.assertTrue((self.root / "eeeeeeeeeee" / ORIGINAL_FILE).exists())

    def test_purge_keeps_ready_and_protected(self):
        make_song(self.root, "fffffffffff")
        make_song(self.root, "ggggggggggg", ready=False)
        make_song(self.root, "hhhhhhhhhhh", ready=False)
        self.assertEqual(cache_heal.purge_incomplete(protect={"hhhhhhhhhhh"}), ["ggggggggggg"])
        self.assertEqual(cache_manager.song_ids(), {"fffffffffff", "hhhhhhhhhhh"})


class TestCacheAdmin(CacheTestCase):
    def setUp(self):
        super().setUp()
        now = time.time()
        make_song(self.root, "played00000", last_accessed=now, played_at=now)
        make_song(self.root, "warm0000000", warmed_at=now, rotation="r1")
        make_song(self.root, "queued00000", warmed_at=now, rotation="r1")
        self._protect = patch("core.cache_admin.protected", return_value={"queued00000"})
        self._protect.start()

    def tearDown(self):
        self._protect.stop()
        super().tearDown()

    def test_stats(self):
        s = cache_admin.stats()
        self.assertEqual((s["songs"], s["ready"], s["warm_songs"], s["protected"]), (3, 3, 2, 1))
        self.assertGreater(s["used"], 0)
        self.assertIn("disk_free", s)

    def test_clear_warm_keeps_played_and_protected(self):
        result = cache_admin.clear("warm")
        self.assertEqual(result["evicted"], ["warm0000000"])
        self.assertGreater(result["freed"], 0)
        self.assertEqual(cache_manager.song_ids(), {"played00000", "queued00000"})

    def test_clear_all_keeps_protected(self):
        cache_admin.clear("all")
        self.assertEqual(cache_manager.song_ids(), {"queued00000"})
        with self.assertRaises(ValueError):
            cache_admin.clear("everything")

    def test_trim_fits_the_limit_without_touching_protected(self):
        with patch("core.cache_manager.settings.get", return_value=0.0):
            result = cache_admin.trim()
        self.assertEqual(set(result["evicted"]), {"played00000", "warm0000000"})
        self.assertEqual(cache_manager.song_ids(), {"queued00000"})


class TestCacheRoutes(CacheTestCase):
    def test_host_only_and_works_for_the_host(self):
        from fastapi.testclient import TestClient
        import main
        client = TestClient(main.app)   # no "with": the worker and warmer don't start
        with patch("core.auth.is_this_laptop", return_value=False):   # a guest's phone
            self.assertEqual(client.get("/api/cache").status_code, 403)
            self.assertEqual(client.post("/api/cache/clear", json={"what": "all"}).status_code, 403)
        make_song(self.root, "aaaaaaaaaaa", warmed_at=time.time())
        main.app.dependency_overrides[auth.require_admin] = lambda: auth.Who(laptop=True, admin=True)
        try:
            self.assertEqual(client.get("/api/cache").json()["songs"], 1)
            self.assertEqual(client.post("/api/cache/clear", json={"what": "nope"}).status_code, 422)
            res = client.post("/api/cache/clear", json={"what": "warm"}).json()
            self.assertEqual((res["evicted"], res["stats"]["songs"]), (["aaaaaaaaaaa"], 0))
            self.assertEqual(client.post("/api/cache/trim").json()["evicted"], [])
        finally:
            main.app.dependency_overrides.clear()


if __name__ == "__main__":
    unittest.main()
