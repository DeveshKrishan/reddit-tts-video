import os

from gtts import gTTS

import fetch_content as fetch_content
from logger import logger
from thumbnail import create_thumbnail
from videoeditor import create_video
from youtube import upload_video

OUTPUT_FOLDER = "assets/audio"


def main() -> None:
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


if __name__ == "__main__":
    main()
