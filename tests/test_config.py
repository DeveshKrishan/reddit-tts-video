import unittest

from config import load_config


class TestConfig(unittest.TestCase):
    def test_shorts_defaults(self) -> None:
        config = load_config()
        shorts = config["shorts"]

        self.assertEqual(shorts["width"], 1080)
        self.assertEqual(shorts["height"], 1920)
        self.assertEqual(shorts["max_duration_seconds"], 180)
        self.assertEqual(shorts["long_content_strategy"], "split")
