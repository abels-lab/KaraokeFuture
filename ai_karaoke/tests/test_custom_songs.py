"""Tests for the custom & unofficial songs feature (uploads and links)."""
import io
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from core import eviction, source_ids
from main import app
from services import sources


class TestCustomSongs(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_upload_id_generation_and_source_recognition(self):
        seed = b"test audio content"
        uid = source_ids.make_upload_id(seed)
        self.assertTrue(uid.startswith("u_"))
        self.assertEqual(len(uid), 18)
        self.assertTrue(source_ids.PATTERN.match(uid))
        self.assertEqual(sources.source_of(uid), sources.CUSTOM)
        self.assertTrue(sources.is_valid_id(uid))

    def test_page_url_for_uploads_without_external_url(self):
        uid = source_ids.make_upload_id("sample")
        # Should return "upload://local" when no external URL was registered
        url = sources.page_url(uid)
        self.assertEqual(url, "upload://local")

    def test_eviction_protects_pinned_custom_songs(self):
        metas = [
            {"id": "song_warm_stale", "warmed_at": 100, "rotation": "old", "last_accessed": 10},
            {"id": "song_regular_old", "last_accessed": 20},
            {"id": "song_regular_new", "last_accessed": 30},
            {"id": "u_custom_pinned", "pinned": True, "last_accessed": 5},
        ]
        eviction.current_rotation = "new"
        order = eviction.order(metas)
        # Stale warm evicted first, then regular songs by last_accessed, and pinned songs last
        self.assertEqual(order[0], "song_warm_stale")
        self.assertEqual(order[1], "song_regular_old")
        self.assertEqual(order[2], "song_regular_new")
        self.assertEqual(order[3], "u_custom_pinned")

    def test_ssrf_protection_on_probe(self):
        # Localhost and LAN IPs must be rejected by check_url
        res = self.client.post("/api/custom/probe", json={"url": "http://127.0.0.1:8000/test"})
        self.assertEqual(res.status_code, 400)
        self.assertIn("not allowed", res.json().get("detail", "").lower())

        res = self.client.post("/api/custom/probe", json={"url": "http://192.168.1.50:8000/test"})
        self.assertEqual(res.status_code, 400)
        self.assertIn("not allowed", res.json().get("detail", "").lower())

    @patch("services.custom_ingest.probe_url")
    def test_probe_endpoint_success(self, mock_probe):
        mock_probe.return_value = {
            "url": "https://example.com/song.mp3",
            "title": "Example Song",
            "artist": "Artist X",
            "duration": 180,
            "thumbnail": "https://example.com/thumb.jpg",
        }
        res = self.client.post("/api/custom/probe", json={"url": "https://example.com/song.mp3"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["title"], "Example Song")

    @patch("services.custom_ingest.ingest_link")
    @patch("routers.custom_songs.enqueue")
    def test_link_endpoint_queue(self, mock_enqueue, mock_ingest):
        uid = source_ids.make_upload_id("https://example.com/track")
        mock_ingest.return_value = {
            "id": uid,
            "title": "Track Title",
            "channel": "Channel",
            "duration": 200,
            "thumbnail": None,
        }
        mock_enqueue.return_value = {"id": uid, "title": "Track Title"}

        res = self.client.post(
            "/api/custom/link",
            json={
                "url": "https://example.com/track",
                "title": "Track Title",
                "artist": "Channel",
                "target": "queue",
                "singer": "Host",
            },
        )
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertEqual(data["song_id"], uid)
        self.assertTrue(data["queued"])
        mock_enqueue.assert_called_once()

    @patch("services.custom_ingest.ingest_file")
    @patch("core.worker.worker.submit_library", new_callable=AsyncMock)
    def test_upload_endpoint_library(self, mock_submit_library, mock_ingest):
        uid = source_ids.make_upload_id(b"fake wav bytes")
        mock_ingest.return_value = {
            "id": uid,
            "title": "My Recording",
            "channel": "Me",
            "duration": 150,
            "thumbnail": None,
        }

        fake_audio = io.BytesIO(b"RIFF" + b"\x00" * 2000)
        res = self.client.post(
            "/api/custom/upload",
            data={"title": "My Recording", "artist": "Me", "target": "library"},
            files={"file": ("recording.wav", fake_audio, "audio/wav")},
        )
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertEqual(data["song_id"], uid)
        self.assertFalse(data["queued"])
        mock_submit_library.assert_called_once_with(uid)


if __name__ == "__main__":
    unittest.main()
