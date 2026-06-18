import unittest
from unittest.mock import patch

from sound_effects import SoundCue, detect_sound_cues

TEST_KEYWORDS: dict[str, list[str]] = {
    "shocking": ["unbelievable", "insane", "omg", "shocked"],
    "funny": ["lmao", "hilarious", "lol"],
    "sad": ["heartbroken", "died", "crying"],
    "suspense": ["suddenly", "then it happened"],
}


def _make_segments(words: list[tuple[str, float, float]]) -> list[dict]:
    """Build minimal Whisper-style segments with word timestamps."""
    word_list = [{"word": w, "start": s, "end": e} for w, s, e in words]
    if not word_list:
        return []
    return [
        {
            "start": word_list[0]["start"],
            "end": word_list[-1]["end"],
            "text": " ".join(w for w, _, _ in words),
            "words": word_list,
        }
    ]


class TestDetectSoundCues(unittest.TestCase):
    def _detect(self, raw_text: str, words: list[tuple[str, float, float]], **kwargs) -> list[SoundCue]:
        segments = _make_segments(words)
        kwargs.setdefault("keyword_categories", TEST_KEYWORDS)
        with patch("sound_effects._load_profanity_list", return_value={"damn", "shit", "fuck"}):
            return detect_sound_cues(raw_text, segments, **kwargs)

    def test_empty_segments_returns_no_cues(self) -> None:
        with patch("sound_effects._load_profanity_list", return_value={"damn"}):
            cues = detect_sound_cues("damn", [], TEST_KEYWORDS, confidence_threshold=0.8)
        self.assertEqual(cues, [])

    def test_profanity_word_produces_bleep_cue(self) -> None:
        cues = self._detect(
            "he said damn it", [("he", 0.0, 0.3), ("said", 0.3, 0.6), ("damn", 0.6, 0.9), ("it", 0.9, 1.1)]
        )
        profanity_cues = [c for c in cues if c.effect == "profanity"]
        self.assertEqual(len(profanity_cues), 1)
        self.assertAlmostEqual(profanity_cues[0].start_time, 0.6)
        self.assertAlmostEqual(profanity_cues[0].end_time, 0.9)

    def test_no_profanity_produces_no_bleep(self) -> None:
        cues = self._detect("everything was fine", [("everything", 0.0, 0.5), ("was", 0.5, 0.7), ("fine", 0.7, 1.0)])
        profanity_cues = [c for c in cues if c.effect == "profanity"]
        self.assertEqual(profanity_cues, [])

    def test_shocking_keyword_produces_cue(self) -> None:
        cues = self._detect(
            "it was insane what happened",
            [("it", 0.0, 0.2), ("was", 0.2, 0.4), ("insane", 0.4, 0.9), ("what", 0.9, 1.1), ("happened", 1.1, 1.5)],
        )
        shocking_cues = [c for c in cues if c.effect == "shocking"]
        self.assertEqual(len(shocking_cues), 1)
        self.assertAlmostEqual(shocking_cues[0].start_time, 0.4)

    def test_funny_keyword_produces_cue(self) -> None:
        cues = self._detect(
            "it was hilarious I couldn't stop laughing",
            [("it", 0.0, 0.2), ("was", 0.2, 0.4), ("hilarious", 0.4, 1.0)],
        )
        funny_cues = [c for c in cues if c.effect == "funny"]
        self.assertEqual(len(funny_cues), 1)

    def test_sad_keyword_produces_cue(self) -> None:
        cues = self._detect(
            "she was heartbroken",
            [("she", 0.0, 0.3), ("was", 0.3, 0.5), ("heartbroken", 0.5, 1.2)],
        )
        sad_cues = [c for c in cues if c.effect == "sad"]
        self.assertEqual(len(sad_cues), 1)

    def test_suspense_keyword_produces_cue(self) -> None:
        cues = self._detect(
            "suddenly the door opened",
            [("suddenly", 0.0, 0.5), ("the", 0.5, 0.7), ("door", 0.7, 0.9), ("opened", 0.9, 1.3)],
        )
        suspense_cues = [c for c in cues if c.effect == "suspense"]
        self.assertEqual(len(suspense_cues), 1)

    def test_cues_sorted_by_start_time(self) -> None:
        cues = self._detect(
            "suddenly he said shit and everyone was shocked omg",
            [
                ("suddenly", 0.0, 0.5),
                ("he", 0.5, 0.7),
                ("said", 0.7, 0.9),
                ("shit", 0.9, 1.1),
                ("and", 1.1, 1.3),
                ("everyone", 1.3, 1.6),
                ("was", 1.6, 1.8),
                ("shocked", 1.8, 2.2),
                ("omg", 2.2, 2.5),
            ],
        )
        start_times = [c.start_time for c in cues]
        self.assertEqual(start_times, sorted(start_times))

    def test_keyword_not_in_text_produces_no_cue(self) -> None:
        cues = self._detect(
            "it was a normal day",
            [("it", 0.0, 0.2), ("was", 0.2, 0.4), ("a", 0.4, 0.5), ("normal", 0.5, 0.8), ("day", 0.8, 1.0)],
        )
        category_cues = [c for c in cues if c.effect != "profanity"]
        self.assertEqual(category_cues, [])

    def test_only_one_cue_per_category(self) -> None:
        # "lmao" and "hilarious" both trigger "funny" — expect only one cue
        cues = self._detect(
            "lmao that was hilarious",
            [("lmao", 0.0, 0.4), ("that", 0.4, 0.6), ("was", 0.6, 0.8), ("hilarious", 0.8, 1.3)],
        )
        funny_cues = [c for c in cues if c.effect == "funny"]
        self.assertEqual(len(funny_cues), 1)

    def test_multiple_profanity_words_all_produce_cues(self) -> None:
        cues = self._detect(
            "what the fuck and shit happened",
            [
                ("what", 0.0, 0.2),
                ("the", 0.2, 0.4),
                ("fuck", 0.4, 0.7),
                ("and", 0.7, 0.9),
                ("shit", 0.9, 1.1),
                ("happened", 1.1, 1.5),
            ],
        )
        profanity_cues = [c for c in cues if c.effect == "profanity"]
        self.assertEqual(len(profanity_cues), 2)
