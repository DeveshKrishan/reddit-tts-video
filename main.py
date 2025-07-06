import os
from datetime import datetime, timezone

from gtts import gTTS

import fetch_content as fetch_content
from logger import logger
from thumbnail import create_thumbnail
from videoeditor import create_video
from youtube import upload_video

OUTPUT_FOLDER = "assets/audio"


def main() -> None:
    job_start = datetime.now(timezone.utc)
    job_start_str = job_start.strftime("%Y-%m-%dT%H:%M:%SZ")

    submissions = fetch_content.fetch_submissions(fetch_content.create_password_flow_with_praw())
    submissions = submissions[:1]  # Limit to the first submission for simplicity
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    for submission in submissions:
        title = submission.title
        content = submission.selftext
        author = submission.author.name if submission.author else "Unknown"
        submission_id = submission.id

        # generate audio from the content
        tts = gTTS(content)
        # save locally
        tts.save(f"{OUTPUT_FOLDER}/{submission_id}.mp3")

        logger.info(f"Saved audio for submission: {title} by {author}. Submission ID: {submission_id}")

        create_thumbnail(submission)
        create_video(submission)

        upload_video(submission=submission, video_file=f"output/{submission_id}.mov")

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
