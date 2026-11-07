import unittest
from unittest.mock import patch

from services import ultrastar_source


def _mock_txt(artist: str, title: str, video: str) -> str:
    header = (
        f"#ARTIST:{artist}\n"
        f"#TITLE:{title}\n"
        f"#BPM:384\n"
        f"#GAP:1000\n"
        f"#VIDEO:{video}\n"
    )
    # Generate 5 lines with 5 notes each (25 notes total)
    body = []
    beat = 0
    for _ in range(5):
        for _ in range(5):
            body.append(f": {beat} 2 4 la ")
            beat += 4
        body.append(f"- {beat}")
        beat += 4
    return header + "\n".join(body) + "\n"


class TestUltraStarMatching(unittest.TestCase):

    def test_tokens_strips_accents_and_noise(self):
        tokens_accented = ultrastar_source._tokens("Céline Dion")
        tokens_plain = ultrastar_source._tokens("Celine Dion")
        self.assertEqual(tokens_accented, tokens_plain)
        self.assertEqual(tokens_accented, {"celine", "dion"})

        tokens_title = ultrastar_source._tokens("My Heart Will Go On (Love Theme from Titanic) [Official Video]")
        self.assertEqual(tokens_title, {"my", "heart", "will", "go", "on"})

    def test_similar_exact_and_mashup(self):
        query = "Celine Dion - My Heart Will Go On"
        good_song = {
            "headers": {"ARTIST": "Céline Dion", "TITLE": "My Heart Will Go On"}
        }
        mashup_song = {
            "headers": {
                "ARTIST": "Celinekin Park (Linkin Park vs. Céline Dion)",
                "TITLE": "In The End My Heart Will Go On"
            }
        }
        good_score = ultrastar_source._similar(good_song, query)
        mashup_score = ultrastar_source._similar(mashup_song, query)

        self.assertEqual(good_score, 1.0)
        self.assertLess(mashup_score, 0.6)

    @patch("services.usdb.search")
    def test_candidates_uses_enriched_metadata(self, mock_search):
        mock_search.side_effect = lambda artist, title: [3440] if artist == "Céline Dion" else []
        meta = {
            "title": "Celine Dion - My Heart Will Go On (Lyrics)",
            "artist": "Céline Dion",
            "clean_title": "My Heart Will Go On"
        }
        result = ultrastar_source.candidates(meta)
        self.assertEqual(result, [3440])

    @patch("core.cache_files.kept_file")
    @patch("core.cache_manager.read_meta")
    @patch("core.cache_manager.update_meta")
    @patch("core.cache_files.write_atomic")
    @patch("services.usdb.configured", return_value=True)
    @patch("core.sources_registry.enabled", return_value=True)
    @patch("services.ultrastar_source.candidates", return_value=[28639, 3440])
    @patch("services.usdb.fetch_txt")
    def test_fetch_prefers_mirror_video_match(self, mock_fetch_txt, _cands, _en, _cfg,
                                             mock_write, mock_update, mock_meta, mock_file):
        mock_file.return_value.is_file.return_value = False
        mock_meta.return_value = {
            "title": "Celine Dion - My Heart Will Go On",
            "mirrors": ["A3QAqZQYLIQ"],
            "duration": 275,
            "usdb": None,
        }
        txt_28639 = _mock_txt("Celinekin Park", "In The End My Heart Will Go On", "v=U02H0M0C2rk")
        txt_3440 = _mock_txt("Céline Dion", "My Heart Will Go On", "v=A3QAqZQYLIQ")

        mock_fetch_txt.side_effect = lambda uid: txt_28639 if uid == 28639 else txt_3440

        match = ultrastar_source._fetch("p79GmLNLMrY")
        self.assertEqual(match, "video")
        mock_update.assert_called_with("p79GmLNLMrY", usdb={"id": 3440, "match": "video"})

    @patch("core.cache_files.kept_file")
    @patch("core.cache_manager.read_meta")
    @patch("core.cache_manager.update_meta")
    @patch("core.cache_files.write_atomic")
    @patch("services.usdb.configured", return_value=True)
    @patch("core.sources_registry.enabled", return_value=True)
    @patch("services.ultrastar_source.candidates", return_value=[28639, 3440])
    @patch("services.usdb.fetch_txt")
    def test_fetch_picks_best_title_similarity_when_no_video_match(self, mock_fetch_txt, _cands, _en, _cfg,
                                                                  mock_write, mock_update, mock_meta, mock_file):
        mock_file.return_value.is_file.return_value = False
        mock_meta.return_value = {
            "title": "Celine Dion - My Heart Will Go On",
            "mirrors": [],  # no video match
            "duration": 275,
            "usdb": None,
        }
        txt_28639 = _mock_txt("Celinekin Park", "In The End My Heart Will Go On", "v=U02H0M0C2rk")
        txt_3440 = _mock_txt("Céline Dion", "My Heart Will Go On", "v=A3QAqZQYLIQ")

        mock_fetch_txt.side_effect = lambda uid: txt_28639 if uid == 28639 else txt_3440

        match = ultrastar_source._fetch("p79GmLNLMrY")
        self.assertEqual(match, "title")
        mock_update.assert_called_with("p79GmLNLMrY", usdb={"id": 3440, "match": "title"})


if __name__ == "__main__":
    unittest.main()
