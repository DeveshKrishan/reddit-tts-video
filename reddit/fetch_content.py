from dataclasses import dataclass
import praw
import os
from dotenv import load_dotenv

def create_password_flow_with_praw(client_id: str, client_secret: str, user_agent: str) -> praw.Reddit:
    """
    Create a Reddit client using PRAW (Python Reddit API Wrapper) with password authentication.
    """
    return praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent=user_agent,
    )

if __name__ == "__main__":
    # Example usage
    submissions = []
    load_dotenv()  
    reddit = create_password_flow_with_praw(
        client_id=os.getenv('CLIENT_ID'),
        client_secret=os.getenv('CLIENT_SECRET'),
        user_agent=f'script:test-auth:v1.0 by /u/{os.getenv("USERNAME")}',
    )

    for submission in reddit.subreddit("AITAH").top(limit=1):
        print(submission.title)
        print(submission.selftext)
