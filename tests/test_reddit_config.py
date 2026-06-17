import unittest

from config import load_reddit_config
from reddit_sources import parse_subreddit_sources


class TestRedditConfig(unittest.TestCase):
    def test_loads_configured_subreddits(self) -> None:
        sources = parse_subreddit_sources(load_reddit_config())
        names = [source.name for source in sources]

        self.assertEqual(names, ["AITAH", "AmIOverreacting"])

    def test_applies_defaults(self) -> None:
        config = {
            "defaults": {"time_filter": "week", "limit": 2, "enabled": True},
            "subreddits": [{"name": "testsubreddit"}],
        }
        source = parse_subreddit_sources(config)[0]

        self.assertEqual(source.name, "testsubreddit")
        self.assertEqual(source.time_filter, "week")
        self.assertEqual(source.limit, 2)

    def test_skips_disabled_subreddits(self) -> None:
        config = {
            "defaults": {"enabled": True},
            "subreddits": [
                {"name": "enabled_sub"},
                {"name": "disabled_sub", "enabled": False},
            ],
        }
        names = [source.name for source in parse_subreddit_sources(config)]

        self.assertEqual(names, ["enabled_sub"])

    def test_supports_string_subreddit_entries(self) -> None:
        config = {"subreddits": ["AITAH"]}
        source = parse_subreddit_sources(config)[0]

        self.assertEqual(source.name, "AITAH")
        self.assertEqual(source.time_filter, "day")
        self.assertEqual(source.limit, 1)
