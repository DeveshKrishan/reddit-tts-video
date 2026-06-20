import os
from datetime import datetime, timezone

from dotenv import load_dotenv

import fetch_content as fetch_content
from config import load_config
from logger import logger
from observability import create_metrics_tracker, shutdown_otel
from text_utils import clean_post_text
from tts import generate_tts
from videoeditor import create_videos
from youtube import upload_video

OUTPUT_FOLDER = "assets/audio"


def main() -> None:
    load_dotenv(override=True)

    job_start = datetime.now(timezone.utc)
    job_start_str = job_start.strftime("%Y-%m-%dT%H:%M:%SZ")

    config = load_config()
    tts_config = config.get("tts", {})
    metrics = create_metrics_tracker(config.get("metrics", {}))

    with metrics.track_phase("fetch_submissions"):
        submissions = fetch_content.fetch_submissions(fetch_content.create_password_flow_with_praw())
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    thumbnail_config = config.get("thumbnail", {})

    for submission in submissions:
        title = submission.title
        content = clean_post_text(submission.selftext)
        author = submission.author.name if submission.author else "Unknown"
        submission_id = submission.id

        tts_kwargs = {
            "voice": tts_config.get("voice", "en-US-GuyNeural"),
            "rate": tts_config.get("rate", "+10%"),
            "pitch": tts_config.get("pitch", "+0Hz"),
        }

        with metrics.track_phase("tts", submission_id=submission_id):
            if thumbnail_config.get("enabled", False):
                generate_tts(
                    text=title,
                    output_path=f"{OUTPUT_FOLDER}/{submission_id}_title.mp3",
                    **tts_kwargs,
                )

            generate_tts(
                text=content,
                output_path=f"{OUTPUT_FOLDER}/{submission_id}.mp3",
                **tts_kwargs,
            )

        logger.info(f"Saved audio for submission: {title} by {author}. Submission ID: {submission_id}")

        with metrics.track_phase("video_render", submission_id=submission_id):
            videos = create_videos(submission)

        for video_file, part, total_parts in videos:
            with metrics.track_phase(
                "youtube_upload",
                submission_id=submission_id,
                part=part,
                total_parts=total_parts,
            ):
                upload_video(
                    submission=submission,
                    video_file=video_file,
                    part=part,
                    total_parts=total_parts,
                )

    job_end = datetime.now(timezone.utc)
    job_end_str = job_end.strftime("%Y-%m-%dT%H:%M:%SZ")
    job_run_time = round((job_end - job_start).total_seconds(), 2)
    metrics.log_job_summary(
        duration_sec=job_run_time,
        job_start_time=job_start_str,
        job_end_time=job_end_str,
        destination="YouTube",
        submissions_processed=len(submissions),
    )


if __name__ == "__main__":
    try:
        main()
    finally:
        shutdown_otel()
