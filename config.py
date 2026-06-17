from pathlib import Path

import yaml

CONFIG_PATH = Path("youtube_config.yaml")
REDDIT_CONFIG_PATH = Path("reddit_config.yaml")


def load_config() -> dict:
    """Load pipeline configuration from youtube_config.yaml."""
    with CONFIG_PATH.open("r") as f:
        return yaml.safe_load(f) or {}


def load_reddit_config() -> dict:
    """Load subreddit sources from reddit_config.yaml."""
    with REDDIT_CONFIG_PATH.open("r") as f:
        return yaml.safe_load(f) or {}
