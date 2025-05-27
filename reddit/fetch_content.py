import logging
import os

import praw
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


def create_password_flow_with_praw() -> praw.Reddit:
    """
    Create a Reddit client using PRAW (Python Reddit API Wrapper) with password authentication.
    """
    logging.basicConfig(level=logging.INFO)
    load_dotenv()

    return praw.Reddit(
        client_id=os.getenv("CLIENT_ID"),
        client_secret=os.getenv("CLIENT_SECRET"),
        user_agent=f"script:test-auth:v1.0 by /u/{os.getenv('USERNAME')}",
    )


def fetch_submissions(reddit: praw.Reddit) -> list[praw.models.Submission]:
    """
    Fetch the top submission from the AITAH subreddit.
    """
    list_of_submissions = []
    for submission in reddit.subreddit("AITAH").top(limit=1):
        list_of_submissions.append(submission)

    if not list_of_submissions:
        logging.info("Reddit client created successfully with PRAW.")

    return list_of_submissions


if __name__ == "__main__":
    # Example usage
    reddit = create_password_flow_with_praw()
    submissions = fetch_submissions(reddit)
    logging.info(f"Fetched {len(submissions)} submission(s) from AITAH subreddit.")
