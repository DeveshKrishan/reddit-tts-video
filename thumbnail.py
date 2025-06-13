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
        font_title = ImageFont.truetype("assets/fonts/Poppins-Medium.ttf", 60)
    except OSError:
        font_title = ImageFont.load_default()

    # Draw the username as 'The Daily Redditor' (no submission author)
    profile_radius = 60
    _ = 40 + profile_radius
    profile_y = 40 + profile_radius  # Move profile up
    # Draw a brown circle as a placeholder for the profile pic
    draw.ellipse(
        (40, profile_y - profile_radius, 40 + 2 * profile_radius, profile_y + profile_radius), fill=(120, 90, 60)
    )
    # Vertically center the username and emojis as a block to the icon on the left, but left-align them
    username = "The Daily Redditor"
    try:
        font_user = ImageFont.truetype("assets/fonts/Poppins-Medium.ttf", 44)
    except OSError:
        font_user = ImageFont.load_default()
    user_w, user_h = draw.textbbox((0, 0), username, font=font_user)[2:]

    emojis = "🎩🤍🧑‍⚖️🏆🧿😃❤️‍🔥💀👎"
    try:
        font_emoji = ImageFont.truetype("assets/fonts/Poppins-Medium.ttf", 44)
    except OSError:
        font_emoji = ImageFont.load_default()
    emoji_w, emoji_h = draw.textbbox((0, 0), emojis, font=font_emoji)[2:]

    # Calculate the total height of username + gap + emojis
    gap = 10
    total_text_height = user_h + gap + emoji_h
    # Vertically center this block to the icon, but left-align to the icon's right edge
    left_x = 40 + 2 * profile_radius + 20
    block_y = profile_y - total_text_height // 2
    user_x = left_x
    user_y = block_y
    emoji_x = left_x
    emoji_y = user_y + user_h + gap

    draw.text((user_x, user_y), username, font=font_user, fill="black")
    # Draw the verified emoji PNG instead of a blue circle
    from PIL import Image as PILImage

    verified_img = PILImage.open("assets/emojis/verified.png").convert("RGBA")
    verified_size = 32
    verified_img = verified_img.resize((verified_size, verified_size), PILImage.LANCZOS)
    check_x = user_x + user_w + 10
    check_y = user_y + user_h // 2 - verified_size // 2
    img.paste(verified_img, (int(check_x), int(check_y)), verified_img)
    draw.text((emoji_x, emoji_y), emojis, font=font_emoji, fill="black")

    # Draw the wrapped title (large, bold, left-aligned)
    wrapped_title = textwrap.fill(title, width=22)
    try:
        font_title = ImageFont.truetype("assets/fonts/Poppins-Medium.ttf", 54)
    except OSError:
        font_title = ImageFont.load_default()
    _, _, w, h = draw.textbbox((0, 0), wrapped_title, font=font_title)
    text_x = 40
    text_y = profile_y + profile_radius + 30
    draw.multiline_text((text_x, text_y), wrapped_title, font=font_title, fill="black", align="left")

    # Draw like/comment icons and counts (simple placeholders)
    icon_y = height - 80
    try:
        font_icon = ImageFont.truetype("assets/fonts/Poppins-Medium.ttf", 40)
    except OSError:
        font_icon = ImageFont.load_default()
    # Use heart.png for the heart icon
    heart_img = PILImage.open("assets/emojis/heart.png").convert("RGBA")
    heart_size = 40
    heart_img = heart_img.resize((heart_size, heart_size), PILImage.LANCZOS)
    img.paste(heart_img, (40, icon_y), heart_img)
    draw.text((100, icon_y), "99+", font=font_icon, fill="gray")
    draw.text((220, icon_y), "💬", font=font_icon, fill="gray")
    draw.text((300, icon_y), "99+", font=font_icon, fill="gray")

    # Draw share icon (simple placeholder)
    draw.text((width - 120, icon_y), "⇪ Share", font=font_icon, fill="gray")

    img.save(f"assets/video/{submission.id}_thumbnail.jpg")
    logging.info(f"Thumbnail saved to assets/video/{submission.id}_thumbnail.jpg")
