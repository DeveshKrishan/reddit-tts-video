import unittest
from unittest.mock import patch

import config
from config import load_reddit_config
from reddit_sources import parse_subreddit_sources


class TestRedditConfig(unittest.TestCase):
    def test_loads_production_subreddits(self) -> None:
        sources = parse_subreddit_sources(load_reddit_config())
        names = [source.name for source in sources]

        self.assertEqual(names, ["AITAH", "AmIOverreacting"])

    def test_loads_development_subreddits(self) -> None:
        with patch.object(config, "DEBUG", True):
            sources = parse_subreddit_sources(load_reddit_config())
            names = [source.name for source in sources]

        self.assertEqual(names, ["test"])

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

    def test_per_subreddit_limit_override(self) -> None:
        config = {
            "defaults": {"limit": 1},
            "subreddits": [
                {"name": "AITAH", "limit": 3},
                {"name": "AmIOverreacting", "limit": 2},
            ],
        }
        sources = parse_subreddit_sources(config)

        self.assertEqual([(source.name, source.limit) for source in sources], [("AITAH", 3), ("AmIOverreacting", 2)])

    def test_rejects_invalid_limit(self) -> None:
        config = {"subreddits": [{"name": "AITAH", "limit": 0}]}

        with self.assertRaises(ValueError):
            parse_subreddit_sources(config)
