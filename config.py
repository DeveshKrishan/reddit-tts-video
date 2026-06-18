from pathlib import Path

import yaml

CONFIG_PATH = Path("youtube_config.yaml")
REDDIT_CONFIG_PATH = Path("reddit_config.yaml")
REDDIT_TEST_CONFIG_PATH = Path("reddit_config.test.yaml")

DEBUG = False


def _reddit_config_path() -> Path:
    return REDDIT_TEST_CONFIG_PATH if DEBUG else REDDIT_CONFIG_PATH


def load_config() -> dict:
    """Load pipeline configuration from youtube_config.yaml."""
    with CONFIG_PATH.open("r") as f:
        return yaml.safe_load(f) or {}


def load_reddit_config() -> dict:
    """Load subreddit sources from reddit_config.yaml (test config when DEBUG is on)."""
    with _reddit_config_path().open("r") as f:
        return yaml.safe_load(f) or {}
