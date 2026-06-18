from pathlib import Path

import yaml

CONFIG_PATH = Path("youtube_config.yaml")
REDDIT_CONFIG_PATH = Path("reddit_config.yaml")
SFX_CONFIG_PATH = Path("sfx_config.yaml")

DEBUG = False


def _reddit_environment() -> str:
    return "development" if DEBUG else "production"


def load_config() -> dict:
    """Load pipeline configuration from youtube_config.yaml."""
    with CONFIG_PATH.open("r") as f:
        return yaml.safe_load(f) or {}


def load_sfx_config() -> dict:
    """Load sound effects configuration from sfx_config.yaml."""
    with SFX_CONFIG_PATH.open("r") as f:
        return yaml.safe_load(f) or {}


def load_reddit_config() -> dict:
    """Load subreddit sources for the active environment from reddit_config.yaml."""
    with REDDIT_CONFIG_PATH.open("r") as f:
        config = yaml.safe_load(f) or {}

    environment = _reddit_environment()
    if environment not in config:
        raise ValueError(f"Missing {environment!r} section in {REDDIT_CONFIG_PATH}")

    return config[environment]
