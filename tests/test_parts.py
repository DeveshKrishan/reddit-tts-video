import unittest

from parts import split_segments


class TestSplitSegments(unittest.TestCase):
    def test_returns_empty_for_no_segments(self) -> None:
        self.assertEqual(split_segments([], 180), [])

    def test_keeps_short_content_in_one_part(self) -> None:
        segments = [{"start": 0, "end": 60, "text": "short story"}]
        parts = split_segments(segments, 180)

        self.assertEqual(len(parts), 1)
        self.assertEqual(parts[0][0], 0)
        self.assertEqual(parts[0][1], 60)

    def test_splits_at_sentence_boundaries(self) -> None:
        segments = [
            {"start": 0, "end": 90, "text": "first"},
            {"start": 90, "end": 180, "text": "second"},
            {"start": 180, "end": 240, "text": "third"},
        ]
        parts = split_segments(segments, 180)

        self.assertEqual(len(parts), 2)
        self.assertEqual(parts[0][0], 0)
        self.assertEqual(parts[0][1], 180)
        self.assertEqual(parts[1][0], 180)
        self.assertEqual(parts[1][1], 240)
