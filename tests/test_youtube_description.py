import sys
import unittest
from unittest.mock import MagicMock

# CI installs only PyYAML, Pillow, and numpy; stub heavy runtime deps before project imports.
for module_name in (
    "praw",
    "dotenv",
    "google",
    "google.auth",
    "google.auth.exceptions",
    "google.oauth2",
    "google.oauth2.credentials",
    "googleapiclient",
    "googleapiclient.discovery",
    "googleapiclient.http",
):
    if module_name not in sys.modules:
        sys.modules[module_name] = MagicMock()

from youtube import _build_description  # noqa: E402


class TestYouTubeDescription(unittest.TestCase):
    def _submission(
        self,
        *,
        title: str = "My unfair punishment story",
        subreddit: str = "test",
        author: str = "storyteller",
        permalink: str = "/r/test/comments/abc123/my_story/",
    ) -> MagicMock:
        submission = MagicMock()
        submission.title = title
        submission.subreddit = subreddit
        submission.author = author
        submission.permalink = permalink
        return submission

    def test_omits_post_title_from_description(self) -> None:
        submission = self._submission(title="Do not paste this whole title into the description")

        description = _build_description(submission)

        self.assertNotIn(submission.title, description)

    def test_reddit_url_on_its_own_line(self) -> None:
        submission = self._submission()

        description = _build_description(submission)

        self.assertIn(
            "Read the original post:\nhttps://www.reddit.com/r/test/comments/abc123/my_story/",
            description,
        )

    def test_includes_source_attribution_without_title(self) -> None:
        submission = self._submission(subreddit="AmItTheAsshole", author="throwaway123")

        description = _build_description(submission)

        self.assertIn("Source: r/AmItTheAsshole · u/throwaway123", description)

    def test_part_prefix_and_tags(self) -> None:
        submission = self._submission()

        description = _build_description(
            submission,
            part=2,
            total_parts=3,
            tags=["reddit", "storytime"],
        )

        self.assertTrue(description.startswith("Part 2 of 3\n\n"))
        self.assertIn("#reddit #storytime", description)

    def test_shorts_hashtag_fallback(self) -> None:
        submission = self._submission()

        description = _build_description(submission, add_shorts_hashtag=True)

        self.assertTrue(description.endswith("#Shorts"))
