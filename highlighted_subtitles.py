from __future__ import annotations

from typing import TYPE_CHECKING

from PIL import Image, ImageDraw, ImageFont

if TYPE_CHECKING:
    from moviepy import VideoClip

FONT_PATH = "assets/fonts/Poppins-Medium.ttf"
HIGHLIGHT_COLOR = "#39FF14"
TEXT_COLOR = "white"
STROKE_COLOR = "black"
STROKE_WIDTH = 4
LINE_SPACING = 8
# Extra pixels added between words on top of a normal space, giving the pop
# animation room to expand without clipping into adjacent words.
WORD_EXTRA_GAP = 12

# Pop animation: highlighted word scales to this multiplier at peak.
POP_SCALE_PEAK = 1.10
# Fraction of word duration over which the scale-up completes (ease-out cubic).
POP_RAMP_FRACTION = 0.2
# Transparent padding (px) added above and below the text canvas so the pop
# scale animation never clips the top of the first line or the bottom of the
# last line. Also absorbs font ascenders that sit above the baseline (bbox[1] < 0).
POP_PADDING = 12


def _load_font(font_size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(FONT_PATH, font_size)
    except OSError:
        return ImageFont.load_default()


def segment_words(segment: dict) -> list[dict]:
    """Normalize whisper word timings for a segment."""
    words = segment.get("words") or []
    normalized: list[dict] = []
    for word_info in words:
        word = word_info.get("word", "").strip().lower()
        if word:
            normalized.append({**word_info, "word": word})

    if normalized:
        return normalized

    text_words = segment.get("text", "").strip().lower().split()
    if not text_words:
        return []

    start = float(segment["start"])
    end = float(segment["end"])
    slot = max((end - start) / len(text_words), 0.01)
    return [
        {"word": word, "start": start + index * slot, "end": start + (index + 1) * slot}
        for index, word in enumerate(text_words)
    ]


def _wrap_word_lines(words: list[str], font: ImageFont.ImageFont, max_width: int) -> list[list[str]]:
    measure = Image.new("RGBA", (max_width, 10), (0, 0, 0, 0))
    draw = ImageDraw.Draw(measure)
    lines: list[list[str]] = []
    current: list[str] = []

    for word in words:
        trial = " ".join(current + [word]) if current else word
        bbox = draw.textbbox((0, 0), trial, font=font, stroke_width=STROKE_WIDTH)
        # Account for extra inter-word gap when checking if line exceeds max width.
        extra = WORD_EXTRA_GAP * max(0, len(current))
        if bbox[2] - bbox[0] + extra > max_width and current:
            lines.append(current)
            current = [word]
        else:
            current.append(word)

    if current:
        lines.append(current)
    return lines or [[]]


def _pop_scale(progress: float) -> float:
    """Ease-out cubic: 1.0 → POP_SCALE_PEAK over first POP_RAMP_FRACTION of word, then hold."""
    if progress < POP_RAMP_FRACTION:
        t = progress / POP_RAMP_FRACTION
        ease = 1.0 - (1.0 - t) ** 3
        return 1.0 + (POP_SCALE_PEAK - 1.0) * ease
    return POP_SCALE_PEAK


def _apply_pop_scale(
    image: Image.Image,
    word_bbox: tuple[int, int, int, int],
    scale: float,
) -> Image.Image:
    """Scale up the highlighted word region and overlay it on the image."""
    if scale <= 1.0:
        return image

    x, y, w, h = int(word_bbox[0]), int(word_bbox[1]), int(word_bbox[2]), int(word_bbox[3])
    if w <= 0 or h <= 0:
        return image

    word_region = image.crop((x, y, x + w, y + h))
    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))
    scaled = word_region.resize((new_w, new_h), Image.LANCZOS)

    result = image.copy()

    # Erase the original word so it doesn't bleed through the scaled version.
    erase = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    result.paste(erase, (x, y))

    paste_x = int(x + (w - new_w) / 2)
    paste_y = int(y + (h - new_h) / 2)
    mask = scaled if scaled.mode == "RGBA" else None
    result.paste(scaled, (paste_x, paste_y), mask)
    return result


def render_highlighted_text(
    words: list[str],
    highlight_index: int | None,
    font_size: int,
    max_width: int,
) -> tuple[Image.Image, tuple[int, int, int, int] | None]:
    """Render wrapped caption text with one highlighted word.

    Returns:
        A tuple of (rendered image, highlighted_word_bbox).
        highlighted_word_bbox is (x, y, w, h) within the image, or None.
    """
    font = _load_font(font_size)
    measure = Image.new("RGBA", (max_width, 10), (0, 0, 0, 0))
    measure_draw = ImageDraw.Draw(measure)
    lines = _wrap_word_lines(words, font, max_width)

    line_metrics: list[tuple[list[str], int, int]] = []
    total_height = 0
    for line in lines:
        line_text = " ".join(line)
        bbox = measure_draw.textbbox((0, 0), line_text, font=font, stroke_width=STROKE_WIDTH)
        line_height = bbox[3] - bbox[1]
        # Add WORD_EXTRA_GAP for each inter-word gap so the centering x matches
        # what the rendering loop actually draws (which uses extra gap per word pair).
        line_width = bbox[2] - bbox[0] + WORD_EXTRA_GAP * max(0, len(line) - 1)
        line_metrics.append((line, line_width, line_height))
        total_height += line_height

    if line_metrics:
        total_height += LINE_SPACING * (len(line_metrics) - 1)

    # Add POP_PADDING to both top and bottom so the pop-scale animation (which
    # grows each word by POP_SCALE_PEAK in every direction) never bleeds outside
    # the canvas. The padding is transparent so it doesn't affect appearance.
    canvas_height = max(1, total_height + 2 * POP_PADDING)
    image = Image.new("RGBA", (max_width, canvas_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    y = POP_PADDING
    word_counter = 0
    highlighted_word_bbox: tuple[int, int, int, int] | None = None

    for line, line_width, line_height in line_metrics:
        x = (max_width - line_width) // 2
        for word in line:
            color = HIGHLIGHT_COLOR if word_counter == highlight_index else TEXT_COLOR
            draw.text(
                (x, y),
                word,
                font=font,
                fill=color,
                stroke_width=STROKE_WIDTH,
                stroke_fill=STROKE_COLOR,
            )
            word_bbox = draw.textbbox((x, y), word, font=font, stroke_width=STROKE_WIDTH)

            if word_counter == highlight_index:
                highlighted_word_bbox = (
                    int(word_bbox[0]),
                    int(word_bbox[1]),
                    int(word_bbox[2] - word_bbox[0]),
                    int(word_bbox[3] - word_bbox[1]),
                )

            x = word_bbox[2] + measure_draw.textlength(" ", font=font) + WORD_EXTRA_GAP
            word_counter += 1
        y += line_height + LINE_SPACING

    return image, highlighted_word_bbox


def _rechunk_words(
    segment_words_list: list[tuple[dict, list[dict]]],
    max_words_per_group: int,
) -> list[list[dict]]:
    """Flatten all Whisper word dicts and rechunk into fixed-size groups.

    Each group is shown on screen simultaneously, replacing the full-segment
    display. Smaller groups (3–4 words) create the TikTok-style caption effect
    that keeps viewers engaged.
    """
    flat = [w for _, words in segment_words_list for w in words]
    groups: list[list[dict]] = []
    for i in range(0, len(flat), max_words_per_group):
        chunk = flat[i : i + max_words_per_group]
        if chunk:
            groups.append(chunk)
    return groups


def create_highlighted_subtitles_clip(
    part_segments: list[dict],
    part_start: float,
    duration: float,
    video_width: int,
    font_size: int,
    horizontal_padding: int = 120,
    max_words_per_group: int = 4,
) -> tuple[VideoClip, int]:
    """Build a subtitle clip that highlights the active spoken word in neon green,
    with a pop (scale-in) animation on each newly highlighted word.

    Words are rechunked into groups of `max_words_per_group` (default 4) so
    only a small burst of words is visible at once — the TikTok-style caption
    format proven to maximise view-to-swipe ratio on short-form video.
    """
    import numpy as np
    from moviepy import VideoClip

    max_text_width = video_width - horizontal_padding
    segment_words_list = [(segment, segment_words(segment)) for segment in part_segments]

    # Rechunk words into fixed-size groups for TikTok-style display.
    word_groups: list[list[dict]] = _rechunk_words(segment_words_list, max_words_per_group)

    # Cache: (group_index, highlight_index | None) → (image, highlighted_word_bbox)
    render_cache: dict[tuple[int, int | None], tuple[Image.Image, tuple[int, int, int, int] | None]] = {}
    for group_index, group in enumerate(word_groups):
        word_text = [w["word"] for w in group]
        render_cache[(group_index, None)] = render_highlighted_text(word_text, None, font_size, max_text_width)
        for highlight_index in range(len(group)):
            render_cache[(group_index, highlight_index)] = render_highlighted_text(
                word_text, highlight_index, font_size, max_text_width
            )

    # Word timing lookup: (group_index, word_index) → (start, end) relative to part_start
    word_timings: dict[tuple[int, int], tuple[float, float]] = {}
    for group_index, group in enumerate(word_groups):
        for word_index, word_info in enumerate(group):
            word_timings[(group_index, word_index)] = (
                float(word_info["start"]) - part_start,
                float(word_info["end"]) - part_start,
            )

    def active_state(t: float) -> tuple[int, int | None] | None:
        for group_index, group in enumerate(word_groups):
            if not group:
                continue
            group_start = float(group[0]["start"]) - part_start
            group_end = float(group[-1]["end"]) - part_start
            if group_start <= t < group_end:
                highlight_index = None
                for word_index, word_info in enumerate(group):
                    word_start = float(word_info["start"]) - part_start
                    word_end = float(word_info["end"]) - part_start
                    if word_start <= t < word_end:
                        highlight_index = word_index
                        break
                return group_index, highlight_index
        return None

    def _animated_image(state: tuple[int, int | None], t: float) -> Image.Image:
        """Return the subtitle image with the pop animation applied for time t."""
        image, word_bbox = render_cache[state]
        group_index, highlight_index = state

        if highlight_index is not None and word_bbox is not None:
            timing = word_timings.get((group_index, highlight_index))
            if timing:
                word_start, word_end = timing
                word_dur = word_end - word_start
                if word_dur > 0:
                    progress = max(0.0, min(1.0, (t - word_start) / word_dur))
                    scale = _pop_scale(progress)
                    if scale > 1.0:
                        return _apply_pop_scale(image, word_bbox, scale)

        return image

    def frame_function(t: float) -> np.ndarray:
        state = active_state(t)
        if state is None:
            return np.zeros((1, max_text_width, 3), dtype=np.uint8)
        return np.array(_animated_image(state, t).convert("RGB"))

    def mask_function(t: float) -> np.ndarray:
        state = active_state(t)
        if state is None:
            return np.zeros((1, max_text_width), dtype=float)
        alpha = np.array(_animated_image(state, t).split()[-1], dtype=float) / 255.0
        return alpha

    # Pre-compute the maximum rendered height across all cached frames so the
    # caller can anchor the subtitle block's BOTTOM edge (not the top) at a
    # fixed position above the YouTube Shorts UI buttons.
    max_subtitle_h = max((img.height for (img, _) in render_cache.values()), default=1)

    clip = VideoClip(frame_function, duration=duration, has_constant_size=False)
    mask = VideoClip(mask_function, is_mask=True, duration=duration, has_constant_size=False)
    return clip.with_mask(mask), max_subtitle_h
