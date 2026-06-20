import os
import textwrap

import praw
from PIL import Image, ImageDraw, ImageFont

from config import load_config
from logger import logger

FONT_PATH = "assets/fonts/Poppins-Medium.ttf"
CARD_CORNER_RADIUS = 20
CARD_PADDING = 28


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except OSError:
        return ImageFont.load_default()


def _paste_rgba(base: Image.Image, overlay: Image.Image, position: tuple[int, int]) -> None:
    base.paste(overlay, position, overlay)


def _rounded_rect_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    return mask


def _fit_wrapped_title(
    draw: ImageDraw.ImageDraw,
    title: str,
    max_text_width: int,
    available_height: int,
) -> tuple[str, ImageFont.FreeTypeFont | ImageFont.ImageFont, int]:
    wrapped_title = title
    text_h = 0
    font_title = _load_font(60)
    for font_size in range(72, 27, -2):
        font_title = _load_font(font_size)
        for wrap_width in range(36, 8, -1):
            wrapped = textwrap.fill(title, width=wrap_width)
            bbox = draw.multiline_textbbox((0, 0), wrapped, font=font_title)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            if text_h <= available_height and text_w <= max_text_width:
                return wrapped, font_title, text_h
            wrapped_title = wrapped
    return wrapped_title, font_title, text_h


def render_post_card(submission: praw.models.Submission, card_width: int = 900) -> Image.Image:
    """Render a Reddit-style post card with a transparent background for video overlay."""
    thumbnail_config = load_config().get("thumbnail", {})
    username = thumbnail_config.get("username", "The Daily Redditor")
    profile_radius = 52
    title = submission.title

    header_height = profile_radius * 2 + 24
    footer_height = 56
    content_width = card_width - 2 * CARD_PADDING
    title_area_height = 420

    measure = Image.new("RGBA", (content_width, title_area_height), (0, 0, 0, 0))
    measure_draw = ImageDraw.Draw(measure)
    wrapped_title, font_title, text_h = _fit_wrapped_title(
        measure_draw,
        title,
        content_width,
        title_area_height,
    )

    card_height = CARD_PADDING + header_height + 24 + text_h + 24 + footer_height + CARD_PADDING
    card = Image.new("RGBA", (card_width, card_height), (0, 0, 0, 0))
    card_mask = _rounded_rect_mask((card_width, card_height), CARD_CORNER_RADIUS)
    card_bg = Image.new("RGBA", (card_width, card_height), (255, 255, 255, 255))
    card.paste(card_bg, mask=card_mask)
    draw = ImageDraw.Draw(card)

    profile_y = CARD_PADDING + profile_radius
    pfp_img = Image.open("assets/sololevelingpfp.jpg").convert("RGBA")
    pfp_img = pfp_img.resize((2 * profile_radius, 2 * profile_radius), Image.LANCZOS)
    pfp_mask = Image.new("L", (2 * profile_radius, 2 * profile_radius), 0)
    pfp_draw = ImageDraw.Draw(pfp_mask)
    pfp_draw.ellipse((0, 0, 2 * profile_radius, 2 * profile_radius), fill=255)
    _paste_rgba(card, pfp_img, (CARD_PADDING, profile_y - profile_radius))

    font_user = _load_font(40)
    user_x = CARD_PADDING + 2 * profile_radius + 18
    user_y = profile_y - 18
    draw.text((user_x, user_y), username, font=font_user, fill="black")

    user_bbox = draw.textbbox((user_x, user_y), username, font=font_user)
    verified_img = Image.open("assets/emojis/verified.png").convert("RGBA")
    verified_size = 28
    verified_img = verified_img.resize((verified_size, verified_size), Image.LANCZOS)
    _paste_rgba(
        card,
        verified_img,
        (user_bbox[2] + 8, user_y + (user_bbox[3] - user_bbox[1]) // 2 - verified_size // 2),
    )

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
    emoji_size = 40
    emoji_gap = 8
    emoji_y = user_y + (user_bbox[3] - user_bbox[1]) + 10
    emoji_x = user_x
    for emoji_path in emoji_files:
        emoji_img = Image.open(emoji_path).convert("RGBA").resize((emoji_size, emoji_size), Image.LANCZOS)
        _paste_rgba(card, emoji_img, (int(emoji_x), int(emoji_y)))
        emoji_x += emoji_size + emoji_gap

    title_top = CARD_PADDING + header_height + 12
    text_x = CARD_PADDING
    text_y = title_top
    draw.multiline_text((text_x, text_y), wrapped_title, font=font_title, fill="black", align="left")

    icon_y = card_height - CARD_PADDING - 40
    font_icon = _load_font(34)
    heart_img = Image.open("assets/emojis/heart.png").convert("RGBA")
    heart_size = 36
    heart_img = heart_img.resize((heart_size, heart_size), Image.LANCZOS)
    heart_text = "99+"
    heart_text_bbox = draw.textbbox((0, 0), heart_text, font=font_icon)
    heart_text_w = heart_text_bbox[2] - heart_text_bbox[0]
    heart_text_h = heart_text_bbox[3] - heart_text_bbox[1]
    heart_img_x = CARD_PADDING
    _paste_rgba(card, heart_img, (heart_img_x, icon_y))
    draw.text(
        (heart_img_x + heart_size + 16, icon_y + (heart_size - heart_text_h) // 2 - 4),
        heart_text,
        font=font_icon,
        fill="gray",
    )

    conversation_img = Image.open("assets/emojis/conversation.png").convert("RGBA")
    conversation_size = 36
    conversation_img = conversation_img.resize((conversation_size, conversation_size), Image.LANCZOS)
    comment_text = "99+"
    comment_text_bbox = draw.textbbox((0, 0), comment_text, font=font_icon)
    comment_text_h = comment_text_bbox[3] - comment_text_bbox[1]
    conversation_img_x = heart_img_x + heart_size + heart_text_w + 48
    _paste_rgba(card, conversation_img, (conversation_img_x, icon_y))
    draw.text(
        (conversation_img_x + conversation_size + 16, icon_y + (conversation_size - comment_text_h) // 2 - 4),
        comment_text,
        font=font_icon,
        fill="gray",
    )

    return card


def create_thumbnail(submission: praw.models.Submission) -> str:
    """Generate and save a transparent post card PNG for in-video overlay."""
    thumbnail_config = load_config().get("thumbnail", {})
    card_width = int(thumbnail_config.get("card_width", 900))
    card = render_post_card(submission, card_width=card_width)

    os.makedirs("assets/thumbnails", exist_ok=True)
    output_path = f"assets/thumbnails/{submission.id}.png"
    card.save(output_path)
    logger.info(f"Post card saved to {output_path}")
    return output_path
