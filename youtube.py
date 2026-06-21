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
from observability import record_video_upload_error, record_video_upload_success

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


def _youtube_watch_url(video_id: str) -> str:
    return f"https://youtube.com/watch?v={video_id}"


def _build_description(
    submission: praw.models.Submission,
    *,
    part: int | None = None,
    total_parts: int | None = None,
    tags: list[str] | None = None,
    add_shorts_hashtag: bool = False,
    next_part_url: str | None = None,
    next_part: int | None = None,
) -> str:
    """Build the YouTube upload description.

    YouTube descriptions are plain text only — markdown/HTML anchor tags are not
    supported. Bare https:// URLs are auto-linked by YouTube (blue, clickable).
    """
    post_url = f"https://www.reddit.com{submission.permalink}"
    author = submission.author if submission.author else "[deleted]"

    lines = [
        f"Source: r/{submission.subreddit} · u/{author}",
        "",
        "Read the original post:",
        post_url,
        "",
        "If you enjoyed this video, please like, comment, and subscribe for more Reddit stories!",
        "Share with your friends and let us know your thoughts below.",
    ]
    body = "\n".join(lines)

    if tags:
        body += "\n\n" + " ".join(f"#{t}" for t in tags)
    elif add_shorts_hashtag:
        body += "\n\n#Shorts"

    prefix_lines: list[str] = []
    if part and total_parts and total_parts > 1:
        prefix_lines.append(f"Part {part} of {total_parts}")
    if next_part_url and next_part:
        if prefix_lines:
            prefix_lines.append("")
        prefix_lines.extend([f"Watch Part {next_part}:", next_part_url])

    if prefix_lines:
        return "\n\n".join(["\n".join(prefix_lines), body])
    return body


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


def _description_kwargs(
    *,
    part: int | None,
    total_parts: int | None,
    tags: list[str],
    shorts_config: dict,
    next_part_url: str | None = None,
    next_part: int | None = None,
) -> dict:
    return {
        "part": part,
        "total_parts": total_parts,
        "tags": tags,
        "add_shorts_hashtag": bool(
            not tags and shorts_config.get("enabled") and shorts_config.get("add_hashtag", True)
        ),
        "next_part_url": next_part_url,
        "next_part": next_part,
    }


def _update_video_description(youtube, video_id: str, description: str) -> None:
    response = youtube.videos().list(part="snippet", id=video_id).execute()
    items = response.get("items", [])
    if not items:
        logger.warning(f"Could not fetch video {video_id} to update description.")
        return

    snippet = items[0]["snippet"]
    snippet["description"] = description
    youtube.videos().update(part="snippet", body={"id": video_id, "snippet": snippet}).execute()
    logger.info(f"Updated description for video {video_id} with next-part link.")


def link_next_part_in_description(
    submission: praw.models.Submission,
    *,
    video_id: str,
    part: int,
    total_parts: int,
    next_video_id: str,
    next_part: int,
    youtube,
) -> None:
    """Patch an earlier part's description after the next part has been uploaded."""
    config = load_config()
    tags = _build_tags(submission, config.get("tags", {}))
    description = _build_description(
        submission,
        **_description_kwargs(
            part=part,
            total_parts=total_parts,
            tags=tags,
            shorts_config=config.get("shorts", {}),
            next_part_url=_youtube_watch_url(next_video_id),
            next_part=next_part,
        ),
    )
    try:
        _update_video_description(youtube, video_id, description)
    except Exception as exc:
        logger.error(
            f"Failed to add Part {next_part} link to video {video_id}: {exc}. "
            "Earlier part uploaded without a next-part link."
        )


def upload_video(
    submission: praw.models.Submission,
    video_file: str,
    part: int | None = None,
    total_parts: int | None = None,
    youtube=None,
) -> str | None:
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

    if youtube is None:
        creds = get_credentials(scopes)
        youtube = build("youtube", "v3", credentials=creds)

    tags = _build_tags(submission, tags_config)
    description = _build_description(
        submission,
        **_description_kwargs(
            part=part,
            total_parts=total_parts,
            tags=tags,
            shorts_config=shorts_config,
        ),
    )

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
        record_video_upload_success(
            submission_id=submission.id,
            subreddit=str(submission.subreddit),
            part=part,
            total_parts=total_parts,
        )
        return response["id"]

    except RefreshError as exc:
        record_video_upload_error(
            "RefreshError",
            submission_id=submission.id,
            subreddit=str(submission.subreddit),
            part=part,
            total_parts=total_parts,
        )
        logger.error(REFRESH_TOKEN_HELP)
        raise RefreshError(f"{exc}. {REFRESH_TOKEN_HELP}") from exc
    except Exception as exc:
        record_video_upload_error(
            type(exc).__name__,
            submission_id=submission.id,
            subreddit=str(submission.subreddit),
            part=part,
            total_parts=total_parts,
        )
        raise

    return None


def upload_submission_videos(
    submission: praw.models.Submission,
    videos: list[tuple[str, int, int]],
) -> None:
    """Upload all parts for a submission and link each part to the next in order."""
    if not videos:
        return

    load_dotenv(override=True)
    config = load_config()
    scopes = config.get(
        "scopes", ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"]
    )
    youtube = build("youtube", "v3", credentials=get_credentials(scopes))
    uploaded_ids: dict[int, str] = {}

    for video_file, part, total_parts in videos:
        video_id = upload_video(
            submission,
            video_file,
            part=part,
            total_parts=total_parts,
            youtube=youtube,
        )
        if not video_id:
            continue

        if part > 1:
            previous_part = part - 1
            previous_video_id = uploaded_ids.get(previous_part)
            if previous_video_id and total_parts > 1:
                link_next_part_in_description(
                    submission,
                    video_id=previous_video_id,
                    part=previous_part,
                    total_parts=total_parts,
                    next_video_id=video_id,
                    next_part=part,
                    youtube=youtube,
                )

        uploaded_ids[part] = video_id
