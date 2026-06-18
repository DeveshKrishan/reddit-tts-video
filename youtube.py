import os

import praw
from dotenv import load_dotenv
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from config import DEBUG, load_config
from logger import logger

REFRESH_TOKEN_HELP = (
    "Your YouTube refresh token is invalid or expired. "
    "Regenerate it with: python3 get_youtube_refresh_token.py\n"
    "Then update YT_REFRESH_TOKEN in .env (and GitHub secrets if you use CI)."
)


def _missing_youtube_env_vars() -> list[str]:
    return [
        name
        for name, value in (
            ("YT_CLIENT_ID", os.getenv("YT_CLIENT_ID")),
            ("YT_CLIENT_SECRET", os.getenv("YT_CLIENT_SECRET")),
            ("YT_REFRESH_TOKEN", os.getenv("YT_REFRESH_TOKEN")),
        )
        if not value
    ]


def get_credentials(scopes: list[str]) -> Credentials:
    """Retrieves YouTube API credentials."""
    missing = _missing_youtube_env_vars()
    if missing:
        raise ValueError(
            f"Missing YouTube credentials in .env: {', '.join(missing)}. "
            "Run python3 get_youtube_refresh_token.py to generate a refresh token."
        )

    return Credentials(
        None,
        refresh_token=os.getenv("YT_REFRESH_TOKEN"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.getenv("YT_CLIENT_ID"),
        client_secret=os.getenv("YT_CLIENT_SECRET"),
        scopes=scopes,
    )


def upload_video(
    submission: praw.models.Submission,
    video_file: str,
    part: int | None = None,
    total_parts: int | None = None,
) -> None:
    """
    Uploads a video to YouTube using info from a PRAW submission object and a YAML config for static/auth settings.
    """
    load_dotenv(override=True)

    config = load_config()
    category_id = config.get("category_id")
    privacy_status = config.get("privacy_status")
    shorts_config = config.get("shorts", {})

    if not category_id or not privacy_status:
        raise ValueError("Category ID and Privacy Status must be set in youtube_config.yaml")

    if DEBUG:
        category_id = "22"  # People & Blogs
        privacy_status = "private"  # For testing, set to public

    scopes = config.get(
        "scopes", ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"]
    )

    creds = get_credentials(scopes)

    youtube = build("youtube", "v3", credentials=creds)

    post_url = f"https://www.reddit.com{submission.permalink}"
    description = (
        f"'{submission.title}' by u/{submission.author} in r/{submission.subreddit}\n"
        f"Original post: {post_url}\n\n"
        "If you enjoyed this video, please like, comment, and subscribe for more Reddit stories!\n"
        "Share with your friends and let us know your thoughts below."
    )
    if part and total_parts and total_parts > 1:
        description = f"Part {part} of {total_parts}\n\n{description}"
    if shorts_config.get("enabled") and shorts_config.get("add_hashtag", True):
        description += "\n\n#Shorts"

    safe_title = submission.title if submission.title else "Reddit Story"
    safe_title = "".join(c for c in safe_title if c.isprintable())
    if part and total_parts and total_parts > 1:
        suffix = f" (Part {part}/{total_parts})"
        safe_title = safe_title[: 100 - len(suffix)] + suffix
    else:
        safe_title = safe_title[:100]

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

    upload_label = submission.title
    if part and total_parts and total_parts > 1:
        upload_label = f"{submission.title} (Part {part}/{total_parts})"
    logger.info(f"Uploading video: {upload_label}")
    try:
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                logger.info(f"Uploaded {int(status.progress() * 100)}%...")
        logger.info("Upload complete!")
        logger.info(f"Video ID: {response['id']}")

        thumbnail_path = f"assets/thumbnails/{submission.id}.jpg"
        if os.path.exists(thumbnail_path):
            youtube.thumbnails().set(videoId=response["id"], media_body=MediaFileUpload(thumbnail_path)).execute()
            logger.info(f"Thumbnail uploaded from {thumbnail_path}")
        else:
            logger.info(f"Thumbnail not found at {thumbnail_path}, skipping thumbnail upload.")
    except RefreshError as exc:
        logger.error(REFRESH_TOKEN_HELP)
        raise RefreshError(f"{exc}. {REFRESH_TOKEN_HELP}") from exc
