from dataclasses import dataclass


@dataclass(frozen=True)
class SubredditSource:
    name: str
    time_filter: str
    limit: int


def parse_subreddit_sources(config: dict) -> list[SubredditSource]:
    """Expand reddit_config.yaml entries into fetch settings."""
    defaults = config.get("defaults", {})
    default_time_filter = defaults.get("time_filter", "day")
    default_limit = defaults.get("limit", 1)
    default_enabled = defaults.get("enabled", True)

    sources: list[SubredditSource] = []
    for entry in config.get("subreddits", []):
        if isinstance(entry, str):
            entry = {"name": entry}
        if not entry.get("enabled", default_enabled):
            continue
        sources.append(
            SubredditSource(
                name=entry["name"],
                time_filter=entry.get("time_filter", default_time_filter),
                limit=entry.get("limit", default_limit),
            )
        )

    return sources
