from pathlib import Path

import yaml

CONFIG_PATH = Path("youtube_config.yaml")


def load_config() -> dict:
    """Load pipeline configuration from youtube_config.yaml."""
    with CONFIG_PATH.open("r") as f:
        return yaml.safe_load(f) or {}
