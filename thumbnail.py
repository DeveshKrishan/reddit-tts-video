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

    # Draw a profile picture using the provided pfp image
    pfp_img = Image.open("assets/sololevelingpfp.jpg").convert("RGBA")
    pfp_img = pfp_img.resize((2 * profile_radius, 2 * profile_radius), Image.LANCZOS)
    # Create a mask for a circular crop
    mask = Image.new("L", (2 * profile_radius, 2 * profile_radius), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse((0, 0, 2 * profile_radius, 2 * profile_radius), fill=255)
    img.paste(pfp_img, (40, profile_y - profile_radius), mask)
    username = "The Daily Redditor"
    try:
        font_user = ImageFont.truetype("assets/fonts/Poppins-Medium.ttf", 44)
    except OSError:
        font_user = ImageFont.load_default()
    user_w, user_h = draw.textbbox((0, 0), username, font=font_user)[2:]

    gap = 10
    left_x = 40 + 2 * profile_radius + 20
    block_y = profile_y - (user_h + gap + 44) // 2  # 44 is emoji_size
    user_x = left_x
    user_y = block_y
    emoji_x = left_x
    emoji_y = user_y + user_h + gap
    # Draw username
    draw.text((user_x, user_y), username, font=font_user, fill="black")
    # Draw the verified emoji PNG instead of a blue circle

    verified_img = Image.open("assets/emojis/verified.png").convert("RGBA")
    verified_size = 32
    verified_img = verified_img.resize((verified_size, verified_size), Image.LANCZOS)
    check_x = user_x + user_w + 10
    check_y = user_y + user_h // 2 - verified_size // 2
    img.paste(verified_img, (int(check_x), int(check_y)), verified_img)
    # Draw emoji row using PNGs in the pattern: diamond, fire, skull, shocked (repeat 2x)
    emoji_files = [
        "assets/emojis/diamond.png",
        "assets/emojis/fire.png",
        "assets/emojis/skull.png",
        "assets/emojis/shocked.png",
        "assets/emojis/diamond.png",
        "assets/emojis/fire.png",
        "assets/emojis/skull.png",
        "assets/emojis/shocked.png",
    ]
    emoji_size = 44
    emoji_gap = 10
    emoji_x = left_x
    for emoji_path in emoji_files:
        emoji_img = Image.open(emoji_path).convert("RGBA").resize((emoji_size, emoji_size), Image.LANCZOS)
        img.paste(emoji_img, (int(emoji_x), int(emoji_y)), emoji_img)
        emoji_x += emoji_size + emoji_gap

    # Draw like/comment icons and counts (simple placeholders)
    icon_y = height - 80

    # Draw the wrapped title (large, bold, left-aligned)
    # Calculate available space for the title
    title_top = profile_y + profile_radius + 30
    title_bottom = icon_y - 30  # leave some gap above the icons
    available_height = title_bottom - title_top
    # Set horizontal padding (reduced for more width)
    padding_x = 30  # Reduce padding to allow more text width
    max_text_width = width - 2 * padding_x
    # Dynamically adjust font size and wrapping to fit the space and width
    max_font_size = 80
    min_font_size = 28
    wrapped_title = title
    for font_size in range(max_font_size, min_font_size - 1, -2):
        try:
            font_title = ImageFont.truetype("assets/fonts/Poppins-Medium.ttf", font_size)
        except OSError:
            font_title = ImageFont.load_default()
        # Try much larger wrap widths to fit more words per line
        for wrap_width in range(40, 8, -1):
            wrapped = textwrap.fill(title, width=wrap_width)
            bbox = draw.multiline_textbbox((0, 0), wrapped, font=font_title)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            if text_h <= available_height and text_w <= max_text_width:
                wrapped_title = wrapped
                break
        if text_h <= available_height and text_w <= max_text_width:
            break
    text_x = padding_x
    text_y = title_top + (available_height - text_h) // 2  # center vertically in available space
    draw.multiline_text((text_x, text_y), wrapped_title, font=font_title, fill="black", align="left")

    # Draw like/comment icons and counts (simple placeholders)
    icon_y = height - 80
    try:
        font_icon = ImageFont.truetype("assets/fonts/Poppins-Medium.ttf", 40)
    except OSError:
        font_icon = ImageFont.load_default()
    # Use heart.png for the heart icon
    heart_img = Image.open("assets/emojis/heart.png").convert("RGBA")
    heart_size = 40
    heart_img = heart_img.resize((heart_size, heart_size), Image.LANCZOS)
    img.paste(heart_img, (40, icon_y), heart_img)
    draw.text((100, icon_y), "99+", font=font_icon, fill="gray")

    # Use conversation.png for the comment icon
    conversation_img = Image.open("assets/emojis/conversation.png").convert("RGBA")
    conversation_size = 40
    conversation_img = conversation_img.resize((conversation_size, conversation_size), Image.LANCZOS)
    img.paste(conversation_img, (220, icon_y), conversation_img)
    draw.text((300, icon_y), "99+", font=font_icon, fill="gray")

    img.save(f"assets/video/{submission.id}_thumbnail.jpg")
    logging.info(f"Thumbnail saved to assets/video/{submission.id}_thumbnail.jpg")
