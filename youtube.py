import os

import praw
import yaml
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


def get_credentials(scopes: list[str]) -> Credentials:
    """Retrieves YouTube API credientials"""
    creds = Credentials(
        None,
        refresh_token=os.getenv("YT_REFRESH_TOKEN"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.getenv("YT_CLIENT_ID"),
        client_secret=os.getenv("YT_CLIENT_SECRET"),
        scopes=scopes,
    )

    return creds


def upload_video(submission: praw.models.Submission, video_file: str) -> None:
    """
    Uploads a video to YouTube using info from a PRAW submission object and a YAML config for static/auth settings.
    """
    load_dotenv()  # Loads variables from .env

    # Load static config and auth scopes from YAML
    with open("youtube_config.yaml", "r") as f:
        config = yaml.safe_load(f)
    category_id = config.get("category_id")
    privacy_status = config.get("privacy_status")
    scopes = config.get(
        "scopes", ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"]
    )

    creds = get_credentials(scopes)

    youtube = build("youtube", "v3", credentials=creds)

    # Build a safe, short description using only title, author, and subreddit (no link)
    description = f"'{submission.title}' by u/{submission.author} in r/{submission.subreddit}"

    # Build a safe, short title for YouTube
    safe_title = submission.title if submission.title else "Reddit Story"
    safe_title = "".join(c for c in safe_title if c.isprintable())
    safe_title = safe_title[:100]  # YouTube title max length

    body = {
        "snippet": {
            "title": safe_title,
            "description": description,
            "categoryId": category_id,
        },
        "status": {"privacyStatus": privacy_status, "selfDeclaredMadeForKids": False},
    }

    media = MediaFileUpload(video_file, chunksize=-1, resumable=True)

    request = youtube.videos().insert(part=",".join(body.keys()), body=body, media_body=media)

    print(f"Uploading video: {submission.title}")
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Uploaded {int(status.progress() * 100)}%...")
    print("Upload complete!")
    print("Video ID:", response["id"])

    # Set the thumbnail after upload
    thumbnail_path = f"assets/thumbnails/{submission.id}.jpg"
    if os.path.exists(thumbnail_path):
        youtube.thumbnails().set(videoId=response["id"], media_body=MediaFileUpload(thumbnail_path)).execute()
        print(f"Thumbnail uploaded from {thumbnail_path}")
    else:
        print(f"Thumbnail not found at {thumbnail_path}, skipping thumbnail upload.")
