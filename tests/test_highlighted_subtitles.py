import unittest

from highlighted_subtitles import (
    POP_PADDING,
    _display_word,
    _pad_image_to_height,
    _rechunk_words,
    render_highlighted_text,
    segment_words,
)


def _word(text: str, start: float, end: float) -> dict:
    return {"word": text, "start": start, "end": end}


def _segment(text: str, start: float, end: float, words: list[dict] | None = None) -> dict:
    return {"text": text, "start": start, "end": end, "words": words}


class TestRechunkWords(unittest.TestCase):
    def test_empty_input_returns_empty(self) -> None:
        self.assertEqual(_rechunk_words([], 4), [])

    def test_fewer_words_than_group_size(self) -> None:
        segment_words_list = [(_segment("hello world", 0.0, 1.0), [_word("hello", 0.0, 0.5), _word("world", 0.5, 1.0)])]
        groups = _rechunk_words(segment_words_list, 4)
        self.assertEqual(len(groups), 1)
        self.assertEqual([w["word"] for w in groups[0]], ["hello", "world"])

    def test_exact_multiple_of_group_size(self) -> None:
        words = [_word(f"w{i}", float(i), float(i + 1)) for i in range(8)]
        segment_words_list = [(_segment(" ".join(w["word"] for w in words), 0.0, 8.0), words)]
        groups = _rechunk_words(segment_words_list, 4)
        self.assertEqual(len(groups), 2)
        self.assertEqual(len(groups[0]), 4)
        self.assertEqual(len(groups[1]), 4)

    def test_remainder_creates_final_short_group(self) -> None:
        words = [_word(f"w{i}", float(i), float(i + 1)) for i in range(5)]
        segment_words_list = [(_segment("five words", 0.0, 5.0), words)]
        groups = _rechunk_words(segment_words_list, 4)
        self.assertEqual(len(groups), 2)
        self.assertEqual(len(groups[0]), 4)
        self.assertEqual(len(groups[1]), 1)

    def test_flattens_across_multiple_segments(self) -> None:
        segment_words_list = [
            (_segment("one two", 0.0, 2.0), [_word("one", 0.0, 1.0), _word("two", 1.0, 2.0)]),
            (
                _segment("three four five", 2.0, 5.0),
                [_word("three", 2.0, 3.0), _word("four", 3.0, 4.0), _word("five", 4.0, 5.0)],
            ),
        ]
        groups = _rechunk_words(segment_words_list, 4)
        self.assertEqual(len(groups), 2)
        self.assertEqual([w["word"] for w in groups[0]], ["one", "two", "three", "four"])
        self.assertEqual([w["word"] for w in groups[1]], ["five"])

    def test_preserves_word_timing_dicts(self) -> None:
        original = _word("hello", 1.0, 1.5)
        segment_words_list = [(_segment("hello", 1.0, 1.5), [original])]
        groups = _rechunk_words(segment_words_list, 4)
        self.assertIs(groups[0][0], original)

    def test_does_not_span_sentence_boundaries(self) -> None:
        words = [
            _word("believe", 0.0, 0.3),
            _word("it.", 0.3, 0.6),
            _word("it's", 0.6, 0.9),
            _word("crazy", 0.9, 1.2),
        ]
        segment_words_list = [(_segment("believe it. it's crazy", 0.0, 1.2), words)]
        groups = _rechunk_words(segment_words_list, 4)
        self.assertEqual(len(groups), 2)
        self.assertEqual([w["word"] for w in groups[0]], ["believe", "it."])
        self.assertEqual([w["word"] for w in groups[1]], ["it's", "crazy"])

    def test_long_sentence_splits_at_max_words_without_crossing_sentences(self) -> None:
        words = [
            _word("one", 0.0, 0.2),
            _word("two", 0.2, 0.4),
            _word("three", 0.4, 0.6),
            _word("four", 0.6, 0.8),
            _word("five.", 0.8, 1.0),
            _word("six", 1.0, 1.2),
        ]
        segment_words_list = [(_segment("one two three four five. six", 0.0, 1.2), words)]
        groups = _rechunk_words(segment_words_list, 4)
        self.assertEqual([w["word"] for w in groups[0]], ["one", "two", "three", "four"])
        self.assertEqual([w["word"] for w in groups[1]], ["five."])
        self.assertEqual([w["word"] for w in groups[2]], ["six"])


class TestDisplayWord(unittest.TestCase):
    def test_strips_periods_and_commas(self) -> None:
        self.assertEqual(_display_word("unusable,"), "unusable")
        self.assertEqual(_display_word("it."), "it")

    def test_keeps_question_and_exclamation_marks(self) -> None:
        self.assertEqual(_display_word("what?"), "what?")
        self.assertEqual(_display_word("no!"), "no!")

    def test_strips_apostrophes_from_contractions(self) -> None:
        self.assertEqual(_display_word("it's"), "its")


class TestSegmentWords(unittest.TestCase):
    def test_normalizes_whisper_words(self) -> None:
        segment = _segment(
            "Hello World",
            0.0,
            1.0,
            [{"word": " Hello ", "start": 0.0, "end": 0.5}, {"word": " World ", "start": 0.5, "end": 1.0}],
        )
        words = segment_words(segment)
        self.assertEqual([w["word"] for w in words], ["hello", "world"])

    def test_falls_back_to_segment_text_when_no_word_timestamps(self) -> None:
        segment = _segment("alpha beta gamma", 0.0, 3.0, None)
        words = segment_words(segment)
        self.assertEqual([w["word"] for w in words], ["alpha", "beta", "gamma"])
        self.assertAlmostEqual(words[0]["start"], 0.0)
        self.assertAlmostEqual(words[-1]["end"], 3.0)


class TestRenderHighlightedText(unittest.TestCase):
    def test_canvas_includes_pop_padding(self) -> None:
        image, _ = render_highlighted_text(["hello", "world"], None, font_size=72, max_width=920)
        # Without POP_PADDING the canvas would be shorter; padding adds 2 * POP_PADDING px.
        self.assertGreaterEqual(image.height, 2 * POP_PADDING)

    def test_pad_image_to_height_centers_shorter_canvas(self) -> None:
        image, bbox = render_highlighted_text(["hello"], 0, font_size=72, max_width=920)
        target_h = image.height + 40
        padded, padded_bbox = _pad_image_to_height(image, bbox, target_h)
        self.assertEqual(padded.height, target_h)
        self.assertIsNotNone(padded_bbox)
        assert padded_bbox is not None and bbox is not None
        self.assertEqual(padded_bbox[1], bbox[1] + 20)

    def test_highlighted_word_gets_bbox(self) -> None:
        _, bbox = render_highlighted_text(["one", "two", "three"], highlight_index=1, font_size=72, max_width=920)
        self.assertIsNotNone(bbox)
        x, y, w, h = bbox  # type: ignore[misc]
        self.assertGreater(w, 0)
        self.assertGreater(h, 0)
        self.assertGreaterEqual(y, 0)


if __name__ == "__main__":
    unittest.main()
