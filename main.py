import logging
import os

from gtts import gTTS

import reddit.fetch_content as fetch_content

OUTPUT_FOLDER = "audio"


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    submissions = fetch_content.fetch_submissions(fetch_content.create_password_flow_with_praw())
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

        logging.info(f"Saved audio for submission: {title} by {author}")


if __name__ == "__main__":
    main()
