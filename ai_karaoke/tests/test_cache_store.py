"""Song cache storage: atomic writes, cached meta.json reads, one-pass folder scans, eviction.

Every test uses its own temporary cache folder (core.cache_manager.CACHE_DIR is patched),
never the real cache.
"""
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from config import INSTRUMENTAL_FILE, LYRICS_FILE, VOCALS_FILE
from core import cache_files, cache_manager


def make_song(root: Path, song_id: str, size: int = 1000, ready: bool = True, **meta) -> Path:
    folder = root / song_id
    folder.mkdir(parents=True, exist_ok=True)
    for name in (VOCALS_FILE, INSTRUMENTAL_FILE):
        (folder / name).write_bytes(b"\0" * size)
    (folder / LYRICS_FILE).write_text("[]", encoding="utf-8")
    cache_manager.write_meta(song_id, {"id": song_id, "status": "ready" if ready else "separated", **meta})
    return folder


class CacheTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._patch = patch("core.cache_manager.CACHE_DIR", self.root)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self._tmp.cleanup()


class TestCacheFiles(CacheTestCase):
    def test_write_atomic_leaves_no_temp_file(self):
        target = self.root / "a.json"
        cache_files.write_atomic(target, "hello")
        self.assertEqual(target.read_text(encoding="utf-8"), "hello")
        self.assertEqual([p.name for p in self.root.iterdir()], ["a.json"])

    def test_read_json_rejects_corrupt_and_non_objects(self):
        bad, arr = self.root / "bad.json", self.root / "arr.json"
        bad.write_text('{"half": ', encoding="utf-8")
        arr.write_text("[1, 2]", encoding="utf-8")
        self.assertIsNone(cache_files.read_json(bad))
        self.assertIsNone(cache_files.read_json(arr))
        self.assertIsNone(cache_files.read_json(self.root / "missing.json"))

    def test_read_json_sees_changes_made_by_others(self):
        path = self.root / "m.json"
        path.write_text('{"a": 1}', encoding="utf-8")
        self.assertEqual(cache_files.read_json(path), {"a": 1})
        path.write_text('{"a": 22}', encoding="utf-8")
        self.assertEqual(cache_files.read_json(path), {"a": 22})

    def test_cached_read_is_not_reparsed_and_returns_private_copies(self):
        path = self.root / "m.json"
        cache_files.write_json(path, {"tags": ["x"]})
        with patch("core.cache_files.json.loads", side_effect=AssertionError("re-parsed")):
            first = cache_files.read_json(path)
        first["tags"].append("y")
        self.assertEqual(cache_files.read_json(path), {"tags": ["x"]})

    def test_scan_sizes_folder_and_subfolders(self):
        (self.root / "s").mkdir()
        (self.root / "s" / "a.bin").write_bytes(b"1234")
        (self.root / "s" / "sub").mkdir()
        (self.root / "s" / "sub" / "b.bin").write_bytes(b"12")
        size, names = cache_files.scan(self.root / "s")
        self.assertEqual((size, names), (6, {"a.bin"}))
        self.assertEqual(cache_files.scan(self.root / "nope"), (0, set()))


class TestCacheManager(CacheTestCase):
    def test_list_songs_reports_size_and_readiness(self):
        make_song(self.root, "aaaaaaaaaaa", size=500, last_accessed=1)
        make_song(self.root, "bbbbbbbbbbb", size=10, ready=False, last_accessed=2)
        songs = {s["id"]: s for s in cache_manager.list_songs()}
        self.assertTrue(songs["aaaaaaaaaaa"]["ready"])
        self.assertFalse(songs["bbbbbbbbbbb"]["ready"])
        self.assertGreater(songs["aaaaaaaaaaa"]["size"], 1000)
        self.assertEqual([s["id"] for s in cache_manager.list_songs()], ["bbbbbbbbbbb", "aaaaaaaaaaa"])

    def test_ready_needs_the_files_too(self):
        folder = make_song(self.root, "ccccccccccc")
        (folder / LYRICS_FILE).unlink()
        self.assertFalse(cache_manager.is_ready("ccccccccccc"))
        self.assertFalse(cache_manager.list_songs()[0]["ready"])

    def test_meta_changes_by_callers_dont_leak_into_cache(self):
        make_song(self.root, "ddddddddddd", title="Old")
        cache_manager.read_meta("ddddddddddd")["title"] = "Mutated"
        self.assertEqual(cache_manager.read_meta("ddddddddddd")["title"], "Old")
        cache_manager.update_meta("ddddddddddd", title="New")
        self.assertEqual(cache_manager.read_meta("ddddddddddd")["title"], "New")
        self.assertEqual(json.loads((self.root / "ddddddddddd" / "meta.json").read_text("utf-8"))["title"], "New")

    def test_evict_forgets_the_song(self):
        make_song(self.root, "eeeeeeeeeee")
        cache_manager.evict("eeeeeeeeeee")
        self.assertEqual(cache_manager.read_meta("eeeeeeeeeee"), {})
        self.assertEqual(cache_manager.song_ids(), set())

    def test_ensure_space_evicts_least_recent_and_never_protected(self):
        now = time.time()
        for i, sid in enumerate(("old00000000", "mid00000000", "new00000000")):
            make_song(self.root, sid, size=400 * 1024, last_accessed=now - 100 + i)
        limit_gb = 2 * 1024**2 / 1024**3   # room for two of the three songs
        with patch("core.cache_manager.settings.get", return_value=limit_gb):
            evicted = cache_manager.ensure_space(protect={"old00000000"}, headroom=0)
        self.assertEqual(evicted, ["mid00000000"])
        self.assertEqual(cache_manager.song_ids(), {"old00000000", "new00000000"})

    def test_meta_file_is_written_atomically(self):
        make_song(self.root, "fffffffffff")
        with patch("core.cache_files.os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                cache_manager.update_meta("fffffffffff", title="Broken")
        self.assertEqual(cache_manager.read_meta("fffffffffff")["status"], "ready")
        self.assertEqual(sorted(os.listdir(self.root / "fffffffffff")),
                         sorted([VOCALS_FILE, INSTRUMENTAL_FILE, LYRICS_FILE, "meta.json"]))


if __name__ == "__main__":
    unittest.main()
