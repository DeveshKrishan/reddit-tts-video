import os
import re

import praw
from dotenv import load_dotenv
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from config import DEBUG, load_config
from logger import logger

# Keyword → YouTube search tags mapping.
# Keys are words to detect in the post title (lowercase); values are tags to emit.
_KEYWORD_TAG_MAP: dict[str, list[str]] = {
    # Relationships
    "husband": ["husbandwife", "marriagedrama", "relationship"],
    "wife": ["husbandwife", "marriagedrama", "relationship"],
    "boyfriend": ["relationship", "relationshipadvice", "boyfriendgirlfriend"],
    "girlfriend": ["relationship", "relationshipadvice", "boyfriendgirlfriend"],
    "fiancé": ["engaged", "relationship", "wedding"],
    "fiance": ["engaged", "relationship", "wedding"],
    "ex": ["exdrama", "breakup", "relationship"],
    "partner": ["relationship", "relationshipadvice"],
    "marriage": ["marriagedrama", "relationship", "married"],
    "divorce": ["divorce", "marriagedrama", "relationship"],
    "sister": ["familydrama", "siblings"],
    "brother": ["familydrama", "siblings"],
    "mom": ["familydrama", "toxicfamily", "momstories"],
    "mother": ["familydrama", "toxicfamily", "momstories"],
    "dad": ["familydrama", "toxicfamily"],
    "father": ["familydrama", "toxicfamily"],
    "parents": ["familydrama", "toxicparents"],
    "inlaw": ["inlaws", "familydrama", "motherinlaw"],
    "inlaws": ["inlaws", "familydrama", "motherinlaw"],
    "coworker": ["workplacedrama", "coworkers", "officedrama"],
    "boss": ["workplacedrama", "toxicworkplace", "work"],
    "friend": ["friendshipdrama", "toxic", "friendship"],
    "neighbor": ["neighbordrama", "neighbors"],
    "roommate": ["roommate", "roommatestories"],
    # Conflicts / actions
    "cheated": ["cheating", "infidelity", "betrayal"],
    "cheat": ["cheating", "infidelity", "betrayal"],
    "cheating": ["cheating", "infidelity", "betrayal"],
    "lied": ["betrayal", "honesty", "trust"],
    "lying": ["betrayal", "honesty"],
    "stole": ["drama", "betrayal"],
    "fired": ["workplacedrama", "fired", "work"],
    "quit": ["workplacedrama", "quitmyjob"],
    "pregnant": ["pregnancydrama", "family", "relationship"],
    "baby": ["familydrama", "parenting"],
    "wedding": ["weddingdrama", "wedding", "relationship"],
    "money": ["moneydrama", "finances", "relationship"],
    "inheritance": ["familydrama", "inheritance", "money"],
    "entitled": ["entitledpeople", "karen", "entitledparents"],
    "karen": ["karen", "entitledpeople"],
    "toxic": ["toxicpeople", "toxicrelationship"],
    "abuse": ["abuse", "toxicrelationship", "mentalhealth"],
    "trauma": ["trauma", "mentalhealth"],
    "secret": ["secrets", "betrayal", "drama"],
    "revenge": ["revenge", "prorevenge", "satisfying"],
    "blocked": ["drama", "relationship"],
    "confronted": ["confrontation", "drama"],
    "ghosted": ["ghosted", "dating", "relationship"],
    # Outcomes
    "update": ["redditupdate", "storytime"],
    "apology": ["apology", "drama"],
    "cut off": ["toxicfamily", "nocontact"],
    "nocontact": ["nocontact", "toxicfamily"],
}


def _post_tags(title: str) -> list[str]:
    """Derive high-searchability YouTube tags from the post title.

    Scans the title for known relationship/conflict keywords and maps them to
    popular YouTube search terms, then falls back to cleaned title words.
    """
    lower = title.lower()
    seen: set[str] = set()
    tags: list[str] = []

    def _add(t: str) -> None:
        key = t.lower()
        if key not in seen:
            seen.add(key)
            tags.append(t)

    # Keyword-mapped tags first (highest relevance)
    for keyword, mapped in _KEYWORD_TAG_MAP.items():
        if keyword in lower:
            for t in mapped:
                _add(t)
            if len(tags) >= 8:
                break

    # Fill remaining slots with cleaned title words (≥5 chars, not already added)
    stop = {
        "about",
        "after",
        "again",
        "against",
        "always",
        "because",
        "before",
        "could",
        "every",
        "going",
        "should",
        "their",
        "there",
        "these",
        "think",
        "those",
        "though",
        "until",
        "wants",
        "which",
        "while",
        "would",
        "years",
        "still",
        "people",
        "really",
        "where",
    }
    for word in re.findall(r"[a-zA-Z]{5,}", title):
        if word.lower() not in stop:
            _add(word)
        if len(tags) >= 10:
            break

    return tags


def _build_tags(
    submission: praw.models.Submission,
    tags_config: dict,
) -> list[str]:
    """Combine broad + subreddit-specific + post-specific tags (deduped, max 500 chars total)."""
    broad: list[str] = tags_config.get("broad", [])
    subreddit_map: dict[str, list[str]] = tags_config.get("subreddit", {})
    niche: list[str] = subreddit_map.get(str(submission.subreddit), [])
    post: list[str] = _post_tags(submission.title)

    seen: set[str] = set()
    combined: list[str] = []
    for tag in broad + niche + post:
        key = tag.lower()
        if key not in seen:
            seen.add(key)
            combined.append(tag)

    # YouTube tag list must be ≤ 500 chars total (joined by commas)
    result: list[str] = []
    total = 0
    for tag in combined:
        if total + len(tag) + 1 > 500:
            break
        result.append(tag)
        total += len(tag) + 1
    return result


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
    tags_config = config.get("tags", {})

    if not category_id or not privacy_status:
        raise ValueError("Category ID and Privacy Status must be set in configs/youtube_config.yaml")

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
    tags = _build_tags(submission, tags_config)
    if tags:
        description += "\n\n" + " ".join(f"#{t}" for t in tags)
    elif shorts_config.get("enabled") and shorts_config.get("add_hashtag", True):
        description += "\n\n#Shorts"

    safe_title = submission.title if submission.title else "Reddit Story"
    safe_title = "".join(c for c in safe_title if c.isprintable())

    suffixes: list[str] = []
    if part and total_parts and total_parts > 1:
        suffixes.append(f"(Part {part}/{total_parts})")
    if shorts_config.get("add_subreddit_hashtag", True):
        suffixes.append(f"#{submission.subreddit}")

    if suffixes:
        suffix = " " + " ".join(suffixes)
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

    except RefreshError as exc:
        logger.error(REFRESH_TOKEN_HELP)
        raise RefreshError(f"{exc}. {REFRESH_TOKEN_HELP}") from exc
