"""Settings › Sources: switching sources off, their order, the host's own links, and the services
and API that follow it. Each test uses its own temporary sources.json; no network."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core import sources_registry as reg
from routers import sources as sources_router
from services import lyrics_chain, search


class RegistryCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.file = Path(self.tmp.name) / "sources.json"
        self.settings = {"use_soundcloud": True, "use_genius": True, "use_chords_lyrics": True, "min_lyric_lines": 3}
        for p in (patch.object(reg, "STATE_FILE", self.file),
                  patch("core.sources_registry.settings.get", side_effect=self.settings.get),
                  patch("core.sources_registry.settings.update", side_effect=self.settings.update),
                  patch("services.lyrics_chain.settings.get", side_effect=self.settings.get)):
            p.start()
            self.addCleanup(p.stop)
        reg.reload()
        self.addCleanup(reg.reload)
        self.addCleanup(self.tmp.cleanup)

    def ids(self, kind, on_only=True):
        return [e["id"] for e in (reg.ordered(kind) if on_only else reg.entries(kind))]


class TestRegistry(RegistryCase):
    def test_defaults(self):
        self.assertEqual(self.ids("songs"), ["youtube", "soundcloud"])
        self.assertEqual(self.ids("synced"), ["lrclib", "syncedlyrics"])
        self.assertTrue(all(e["url"].startswith("https://") for k, *_ in reg.KINDS for e in reg.entries(k)))

    def test_switch_off_and_reorder_persist(self):
        reg.set_enabled("lrclib", False)
        reg.move("syncedlyrics", -1)
        reg.reload()   # read back from the file
        self.assertEqual(self.ids("synced", on_only=False), ["syncedlyrics", "lrclib"])
        self.assertEqual(self.ids("synced"), ["syncedlyrics"])
        self.assertFalse(reg.enabled("lrclib"))

    def test_setting_backed_toggle_is_the_setting(self):
        reg.set_enabled("soundcloud", False)
        self.assertFalse(self.settings["use_soundcloud"])
        self.assertEqual(self.ids("songs"), ["youtube"])
        self.assertNotIn("soundcloud", self.file.read_text(encoding="utf-8") if self.file.exists() else "")

    def test_custom_links(self):
        link = reg.save_custom("lyrics", "My lyrics", "https://lyrics.example.com/{artist_slug}/{title_slug}")
        self.assertTrue(link["id"].startswith("c_") and link["enabled"])
        reg.move(link["id"], -1)
        self.assertEqual(self.ids("lyrics"), [link["id"], "genius"])
        reg.save_custom("lyrics", "Renamed", "https://lyrics.example.com/?q={query}", link["id"])
        reg.reload()
        self.assertEqual(reg.entries("lyrics")[0]["name"], "Renamed")
        reg.remove_custom(link["id"])
        self.assertEqual(self.ids("lyrics"), ["genius"])
        with self.assertRaises(KeyError):
            reg.remove_custom(link["id"])

    def test_bad_links_and_broken_file(self):
        with self.assertRaises(ValueError):
            reg.save_custom("songs", "LAN", "http://192.168.1.2/{query}")
        with self.assertRaises(ValueError):
            reg.save_custom("chords", "X", "https://example.com/{query}")
        self.file.write_text('{"off": ["youtube"], "custom": [{"id": "c_1", "kind": "songs", "name": "Bad", '
                             '"template": "http://localhost/{query}"}, "junk"]}', encoding="utf-8")
        with self.assertLogs("core.sources_store", "WARNING"):
            reg.reload()
            self.assertEqual(self.ids("songs"), ["soundcloud"])
        self.file.write_text("{not json", encoding="utf-8")
        with self.assertLogs("core.sources_store", "WARNING"):
            reg.reload()
            self.assertEqual(self.ids("songs"), ["youtube", "soundcloud"])


class TestServicesFollowTheRegistry(RegistryCase):
    def test_lyrics_chain_order_and_switches(self):
        asked = []
        def fake(entry, *_):
            return lambda: asked.append(entry["id"]) or (f"text from {entry['id']}" if entry["id"] == "amdm" else None)
        reg.set_enabled("syncedlyrics", False)
        reg.move("amdm", -1)
        with patch("services.lyrics_chain._fetcher", side_effect=fake):
            self.assertEqual(next(lyrics_chain.found("Oasis - Wonderwall", "Wonderwall")), ("AmDm.ru", "text from amdm"))
        self.assertEqual(asked, ["lrclib", "genius", "amdm"])
        self.settings["use_chords_lyrics"] = False
        with patch("services.lyrics_chain._fetcher", side_effect=fake):
            self.assertEqual(list(lyrics_chain.found("q", "q")), [])

    def test_search_uses_switched_on_sources_in_order(self):
        link = reg.save_custom("songs", "Vimeo", "https://vimeo.com/search?q={query}")
        reg.set_enabled("youtube", False)
        reg.move(link["id"], -1)
        hit = lambda sid, src: {"id": sid, "source": src}
        with patch("services.search.sources.flat_search", return_value=[hit("sc_0000000001", "soundcloud")]) as flat, \
                patch("services.search.custom_songs.search", return_value=[hit("x_0123456789abcdef", link["id"])]):
            raw = search._gather("song", 5, {"errors": []})
        self.assertEqual([r["source"] for r in raw], [link["id"], "soundcloud"])
        self.assertEqual(flat.call_args.args[0], "soundcloud")
        reg.set_enabled("soundcloud", False)
        reg.set_enabled(link["id"], False)
        with self.assertRaisesRegex(RuntimeError, "switched off"):
            search._gather("song", 5, {"errors": []})


class TestApi(RegistryCase):
    def setUp(self):
        super().setUp()
        app = FastAPI()
        app.include_router(sources_router.router)
        self.client = TestClient(app)
        hub = patch("routers.sources.hub.broadcast")
        hub.start()
        self.addCleanup(hub.stop)

    def test_host_can_manage_links(self):
        page = self.client.get("/api/sources").json()
        self.assertEqual([k["id"] for k in page["kinds"]], ["songs", "synced", "lyrics", "chords", "info"])
        bad = self.client.post("/api/sources/custom", json={"kind": "songs", "name": "x", "template": "http://10.0.0.1/{query}"})
        self.assertEqual(bad.status_code, 422)
        page = self.client.post("/api/sources/custom", json={"kind": "songs", "name": "Vimeo",
                                                             "template": "https://vimeo.com/search?q={query}"}).json()
        cid = page["kinds"][0]["sources"][-1]["id"]
        self.assertEqual(self.client.put(f"/api/sources/{cid}", json={"enabled": False}).status_code, 200)
        self.assertEqual(self.client.post(f"/api/sources/{cid}/move", json={"step": -1}).status_code, 200)
        self.assertEqual(self.ids("songs", on_only=False)[1], cid)
        self.assertEqual(self.client.delete(f"/api/sources/custom/{cid}").status_code, 200)
        self.assertEqual(self.client.put("/api/sources/nope", json={"enabled": True}).status_code, 404)
        test = self.client.post("/api/sources/test", json={"kind": "lyrics", "template": "https://localhost/{query}"})
        self.assertEqual(test.status_code, 422)

    def test_guests_are_refused(self):
        with patch("core.auth.is_this_laptop", return_value=False):
            self.assertEqual(self.client.get("/api/sources").status_code, 403)
            self.assertEqual(self.client.post("/api/sources/custom", json={}).status_code, 403)


if __name__ == "__main__":
    unittest.main()
