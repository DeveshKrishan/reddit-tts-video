import os
from datetime import datetime, timezone

import fetch_content as fetch_content
from config import load_config
from logger import logger
from text_utils import clean_post_text
from tts import generate_tts
from videoeditor import create_videos
from youtube import upload_video

OUTPUT_FOLDER = "assets/audio"


def main() -> None:
    job_start = datetime.now(timezone.utc)
    job_start_str = job_start.strftime("%Y-%m-%dT%H:%M:%SZ")

    config = load_config()
    tts_config = config.get("tts", {})

    submissions = fetch_content.fetch_submissions(fetch_content.create_password_flow_with_praw())
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    for submission in submissions:
        title = submission.title
        content = clean_post_text(submission.selftext)
        author = submission.author.name if submission.author else "Unknown"
        submission_id = submission.id

        generate_tts(
            text=content,
            output_path=f"{OUTPUT_FOLDER}/{submission_id}.mp3",
            voice=tts_config.get("voice", "en-US-GuyNeural"),
            rate=tts_config.get("rate", "+10%"),
            pitch=tts_config.get("pitch", "+0Hz"),
        )

        logger.info(f"Saved audio for submission: {title} by {author}. Submission ID: {submission_id}")

        videos = create_videos(submission)

        for video_file, part, total_parts in videos:
            upload_video(
                submission=submission,
                video_file=video_file,
                part=part,
                total_parts=total_parts,
            )

    job_end = datetime.now(timezone.utc)
    job_end_str = job_end.strftime("%Y-%m-%dT%H:%M:%SZ")
    job_run_time = round((job_end - job_start).total_seconds(), 2)
    log_dict = {
        "job_run_time": job_run_time,
        "job_start_time": job_start_str,
        "job_end_time": job_end_str,
        "destination": "YouTube",
    }
    logger.info(f"Job summary: {log_dict}")


if __name__ == "__main__":
    main()
