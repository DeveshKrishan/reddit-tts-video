import sys
import unittest
from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock, patch

# CI installs only PyYAML and Pillow; stub heavy runtime deps before project imports.
if "praw" not in sys.modules:
    sys.modules["praw"] = MagicMock()

if "stable_whisper" not in sys.modules:
    sys.modules["stable_whisper"] = MagicMock()

if "moviepy" not in sys.modules:
    _moviepy = MagicMock()
    _moviepy.AudioFileClip = MagicMock
    _moviepy.CompositeVideoClip = MagicMock
    _moviepy.ImageClip = MagicMock
    _moviepy.VideoClip = MagicMock
    _moviepy.VideoFileClip = MagicMock
    _moviepy.concatenate_audioclips = MagicMock
    _moviepy.vfx = MagicMock()
    sys.modules["moviepy"] = _moviepy
    _loop = MagicMock()
    _loop.Loop = MagicMock
    sys.modules["moviepy.video.fx.Loop"] = _loop

from highlighted_subtitles import create_highlighted_subtitles_clip


class TestThumbnail(unittest.TestCase):
    def _submission(self, title: str = "Teachers Of Reddit, What Was The Most Unfair Punishment?") -> MagicMock:
        submission = MagicMock()
        submission.title = title
        submission.id = "abc123"
        return submission

    def test_render_post_card_is_transparent_overlay(self) -> None:
        from thumbnail import render_post_card

        card = render_post_card(self._submission(), card_width=900)

        self.assertEqual(card.mode, "RGBA")
        self.assertEqual(card.size[0], 900)
        self.assertGreater(card.size[1], 200)
        alpha = card.split()[-1]
        self.assertLess(alpha.getextrema()[0], 255)

    @patch("thumbnail.render_post_card")
    @patch("thumbnail.os.makedirs")
    def test_create_thumbnail_saves_png(self, mock_makedirs, mock_render_post_card) -> None:
        from thumbnail import create_thumbnail

        card = MagicMock()
        mock_render_post_card.return_value = card

        path = create_thumbnail(self._submission())

        self.assertEqual(path, "assets/thumbnails/abc123.png")
        mock_makedirs.assert_called_once_with("assets/thumbnails", exist_ok=True)
        card.save.assert_called_once_with("assets/thumbnails/abc123.png")


class TestThumbnailTiming(unittest.TestCase):
    def test_offset_segment_timestamps(self) -> None:
        from videoeditor import _offset_segment_timestamps

        segments = [
            {
                "start": 0.0,
                "end": 1.0,
                "words": [{"word": "hello", "start": 0.0, "end": 1.0}],
            }
        ]
        shifted = _offset_segment_timestamps(segments, 2.5)
        self.assertEqual(shifted[0]["start"], 2.5)
        self.assertEqual(shifted[0]["words"][0]["start"], 2.5)

    @patch("videoeditor.ImageClip")
    def test_build_faded_thumbnail_clip_duration(self, mock_image_clip) -> None:
        from videoeditor import _build_faded_thumbnail_clip

        mock_clip = MagicMock()
        mock_mask = MagicMock()
        mock_image_clip.return_value = mock_clip
        mock_clip.with_duration.return_value = mock_clip
        mock_clip.with_position.return_value = mock_clip
        mock_clip.mask = mock_mask
        mock_mask.with_effects.return_value = mock_mask
        mock_clip.with_mask.return_value = mock_clip

        _, total_duration = _build_faded_thumbnail_clip("card.png", title_duration=4.0, fade_in=0.4, fade_out=0.5)

        self.assertEqual(total_duration, 4.5)
        mock_clip.with_duration.assert_called_once_with(4.5)
        mock_mask.with_effects.assert_called_once()


class TestSubtitleDelay(unittest.TestCase):
    def test_subtitle_delay_hides_captions_during_intro(self) -> None:
        segments = [
            {
                "start": 0.0,
                "end": 5.0,
                "words": [{"word": "hello", "start": 0.0, "end": 5.0}],
            }
        ]
        captured: dict[str, Callable[[float], Any]] = {}

        def fake_video_clip(frame_function, duration, has_constant_size=True, is_mask=False):
            if not is_mask:
                captured["frame_function"] = frame_function
            mock = MagicMock()
            mock.with_mask.return_value = mock
            return mock

        with (
            patch("highlighted_subtitles.render_highlighted_text") as mock_render,
            patch("moviepy.VideoClip", fake_video_clip),
        ):
            mock_render.return_value = (
                __import__("PIL").Image.new("RGBA", (100, 40), (255, 255, 255, 255)),
                None,
            )
            create_highlighted_subtitles_clip(
                part_segments=segments,
                part_start=0.0,
                duration=4.0,
                video_width=1080,
                font_size=48,
                subtitle_delay=2.0,
            )

        frame_function = captured["frame_function"]
        self.assertEqual(frame_function(0.5).max(), 0)
        self.assertGreater(frame_function(2.5).max(), 0)
