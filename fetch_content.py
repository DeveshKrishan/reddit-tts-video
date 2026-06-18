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


def fetch_submissions(reddit: praw.Reddit) -> list[praw.models.Submission]:
    """Fetch top posts from each configured subreddit source."""
    sources = parse_subreddit_sources(load_reddit_config())
    submissions: list[praw.models.Submission] = []

    for source in sources:
        fetched = 0
        for submission in reddit.subreddit(source.name).top(time_filter=source.time_filter, limit=source.limit):
            submissions.append(submission)
            fetched += 1
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
