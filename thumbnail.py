import logging
import textwrap

import praw
from PIL import Image, ImageDraw, ImageFont

logging.basicConfig(level=logging.INFO)


def create_thumbnail(submission: praw.models.Submission) -> None:
    """
    Create a YouTube thumbnail for the submission with an orange background, title, and author.
    """

    # Thumbnail size (YouTube recommended: 1280x720)
    width, height = 1280, 720
    background_color = (255, 255, 255)  # White
    title = submission.title
    # author = submission.author.name if submission.author else "Unknown"

    img = Image.new("RGB", (width, height), color=background_color)
    draw = ImageDraw.Draw(img)

    # Load font (fallback to default if not found)
    try:
        font_title = ImageFont.truetype("assets/fonts/Poppins/Poppins-Medium.ttf", 60)
    except OSError:
        font_title = ImageFont.load_default()

    wrapped_title = textwrap.fill(title, width=20)

    _, _, w, h = draw.textbbox((0, 0), wrapped_title, font=font_title)
    draw.multiline_text(
        ((width - w) / 2, (height - h) / 2), wrapped_title, font=font_title, fill="black", align="center"
    )

    img.save(f"assets/video/{submission.id}_thumbnail.jpg")
    logging.info(f"Thumbnail saved to assets/video/{submission.id}_thumbnail.jpg")
