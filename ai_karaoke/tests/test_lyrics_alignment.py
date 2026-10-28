import unittest

from services import vocal_activity, word_timing


class TestLyricsAlignment(unittest.TestCase):

    def test_first_vocal_onset_skips_blips_and_steps_back(self):
        vocal_map = {
            "regions": [[0.5, 0.95], [2.35, 3.25], [6.1, 7.0], [15.35, 23.3], [32.85, 80.85]],
            "loud": [[2.35, 2.75], [6.1, 6.5], [34.0, 69.5]],
        }
        # First sustained loud is at 34.0s; covering region starts at 32.85s
        onset = vocal_activity.first_vocal_onset(vocal_map, start_time=0.0)
        self.assertEqual(onset, 32.85)

    def test_first_vocal_onset_clamps_far_covering_region(self):
        vocal_map = {
            "regions": [[10.0, 80.0]],  # bleed joined to region
            "loud": [[34.0, 69.5]],
        }
        # Covering region is too far back (> 2.0s); clamped to loud_start - 2.0 = 32.0s
        onset = vocal_activity.first_vocal_onset(vocal_map, start_time=0.0)
        self.assertEqual(onset, 32.0)

    def test_first_vocal_onset_no_covering_region(self):
        vocal_map = {
            "regions": [[35.0, 80.0]],
            "loud": [[34.0, 69.5]],
        }
        onset = vocal_activity.first_vocal_onset(vocal_map, start_time=0.0)
        self.assertEqual(onset, 32.5)

    def test_first_vocal_onset_immediate_vocals(self):
        vocal_map = {
            "regions": [[0.2, 10.0]],
            "loud": [[0.5, 10.0]],
        }
        onset = vocal_activity.first_vocal_onset(vocal_map, start_time=0.0)
        self.assertEqual(onset, 0.0)

    def test_first_vocal_onset_no_sustained_vocals(self):
        vocal_map = {
            "regions": [[1.0, 1.4]],
            "loud": [[1.0, 1.4]],  # duration < 1.0s
        }
        onset = vocal_activity.first_vocal_onset(vocal_map, start_time=2.0)
        self.assertEqual(onset, 2.0)

    def test_timing_quality_catches_pre_intro_bleed(self):
        regions = [[15.35, 23.3], [32.85, 80.85]]
        loud = [[34.0, 69.5]]
        # 2 lines placed in pre-intro bleed at 15-20s where there are no loud vocals
        segments = [
            {"start": 15.1, "end": 17.0, "words": [{"word": "A", "start": 15.1, "end": 17.0}]},
            {"start": 17.5, "end": 19.8, "words": [{"word": "B", "start": 17.5, "end": 19.8}]},
            {"start": 34.2, "end": 37.9, "words": [{"word": "C", "start": 34.2, "end": 37.9}]},
        ]
        tq = vocal_activity.timing_quality(segments, regions, loud=loud)
        self.assertTrue(tq["poor"])

    def test_timing_quality_passes_clean_alignment(self):
        regions = [[32.85, 80.85]]
        loud = [[34.0, 69.5]]
        segments = [
            {"start": 34.2, "end": 37.9, "words": [{"word": "A", "start": 34.2, "end": 37.9}]},
            {"start": 38.0, "end": 41.5, "words": [{"word": "B", "start": 38.0, "end": 41.5}]},
        ]
        tq = vocal_activity.timing_quality(segments, regions, loud=loud)
        self.assertFalse(tq["poor"])

    def test_cap_to_phrase_word_starting_in_silence(self):
        regions = [[15.0, 23.0], [33.0, 80.0]]
        # A word starting in silence at 23.5s and stretching to 34.0s (10.5s duration)
        words = [{"word": "and", "start": 23.5, "end": 34.0}]
        word_timing._cap_to_phrase(words, regions)
        # Should be capped to start + STRAY_MAX (24.5s)
        self.assertAlmostEqual(words[0]["end"], 24.5, places=2)

    def test_cap_to_phrase_word_starting_in_phrase(self):
        regions = [[15.0, 23.0], [33.0, 80.0]]
        # A word starting at 22.8s inside region and stretching to 26.0s
        words = [{"word": "bag", "start": 22.8, "end": 26.0}]
        word_timing._cap_to_phrase(words, regions)
        # Should be capped to held (23.0) + PHRASE_PAD (0.3) = 23.3
        self.assertAlmostEqual(words[0]["end"], 23.3, places=2)

    def test_reattach_edges_does_not_pull_across_regions(self):
        regions = [[15.0, 23.0], [33.0, 80.0]]
        # words in two different phrases
        words = [
            {"word": "bag", "start": 22.5, "end": 23.3},
            {"word": "pushed", "start": 34.5, "end": 35.5},
            {"word": "down", "start": 35.5, "end": 36.0},
        ]
        word_timing._reattach_edges(words, prev_end=None, next_start=None, regions=regions)
        # 'pushed' should stay in its vocal phrase at 34.5s, NOT pulled back to 23.3s
        self.assertGreaterEqual(words[1]["start"], 34.0)


if __name__ == "__main__":
    unittest.main()
