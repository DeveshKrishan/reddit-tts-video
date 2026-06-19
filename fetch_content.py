import os

import praw
from dotenv import load_dotenv

from config import load_reddit_config
from logger import logger
from reddit_sources import parse_subreddit_sources

logger = logger


def create_password_flow_with_praw() -> praw.Reddit:
    """
    Create a Reddit client using PRAW (Python Reddit API Wrapper) with password authentication.
    """
    load_dotenv(override=True)
    return praw.Reddit(
        client_id=os.getenv("CLIENT_ID"),
        client_secret=os.getenv("CLIENT_SECRET"),
        user_agent=f"script:test-auth:v1.0 by /u/{os.getenv('USERNAME')}",
    )


def _is_text_post(submission: praw.models.Submission) -> bool:
    """Return True only for self-posts with usable body text.

    Link posts have an empty selftext; removed/deleted posts contain the
    sentinel strings '[removed]' or '[deleted]'. Either case produces a
    malformed TTS audio file that crashes MoviePy downstream.
    """
    text = (submission.selftext or "").strip()
    return bool(text) and text not in ("[removed]", "[deleted]")


def fetch_submissions(reddit: praw.Reddit) -> list[praw.models.Submission]:
    """Fetch top text posts from each configured subreddit source."""
    sources = parse_subreddit_sources(load_reddit_config())
    submissions: list[praw.models.Submission] = []

    for source in sources:
        fetched = 0
        # Over-fetch (up to 3× limit) so we can skip link/removed posts and
        # still satisfy the configured limit.
        candidates = reddit.subreddit(source.name).top(time_filter=source.time_filter, limit=source.limit * 3)
        for submission in candidates:
            if not _is_text_post(submission):
                logger.debug(f"Skipping non-text post '{submission.id}' from r/{source.name}.")
                continue
            submissions.append(submission)
            fetched += 1
            if fetched >= source.limit:
                break
        logger.info(
            f"Fetched {fetched} submission(s) from r/{source.name} "
            f"(time_filter={source.time_filter}, limit={source.limit})."
        )

    if submissions:
        logger.info(f"Fetched {len(submissions)} total submission(s) from {len(sources)} subreddit(s).")

    return submissions


if __name__ == "__main__":
    reddit = create_password_flow_with_praw()
    submissions = fetch_submissions(reddit)
    logger.info(f"Fetched {len(submissions)} submission(s) from configured subreddits.")
