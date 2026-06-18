import numpy as np
from moviepy import VideoClip
from PIL import Image, ImageDraw, ImageFont

FONT_PATH = "assets/fonts/Poppins-Medium.ttf"
HIGHLIGHT_COLOR = "#90EE90"
TEXT_COLOR = "white"
STROKE_COLOR = "black"
STROKE_WIDTH = 4
LINE_SPACING = 8

# Pop animation: highlighted word scales to this multiplier at peak.
POP_SCALE_PEAK = 1.25
# Fraction of word duration over which the scale-up completes (ease-out cubic).
POP_RAMP_FRACTION = 0.2


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
        if bbox[2] - bbox[0] > max_width and current:
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

    x, y, w, h = word_bbox
    if w <= 0 or h <= 0:
        return image

    word_region = image.crop((x, y, x + w, y + h))
    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))
    scaled = word_region.resize((new_w, new_h), Image.LANCZOS)

    result = image.copy()
    paste_x = x + (w - new_w) // 2
    paste_y = y + (h - new_h) // 2
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
        line_width = bbox[2] - bbox[0]
        line_metrics.append((line, line_width, line_height))
        total_height += line_height

    if line_metrics:
        total_height += LINE_SPACING * (len(line_metrics) - 1)

    image = Image.new("RGBA", (max_width, max(1, total_height)), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    y = 0
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
                    word_bbox[0],
                    word_bbox[1],
                    word_bbox[2] - word_bbox[0],
                    word_bbox[3] - word_bbox[1],
                )

            x = word_bbox[2] + measure_draw.textlength(" ", font=font)
            word_counter += 1
        y += line_height + LINE_SPACING

    return image, highlighted_word_bbox


def create_highlighted_subtitles_clip(
    part_segments: list[dict],
    part_start: float,
    duration: float,
    video_width: int,
    font_size: int,
) -> VideoClip:
    """Build a subtitle clip that highlights the active spoken word in light green,
    with a pop (scale-in) animation on each newly highlighted word."""
    max_text_width = video_width - 80
    segment_words_list = [(segment, segment_words(segment)) for segment in part_segments]

    # Cache: (segment_index, highlight_index | None) → (image, highlighted_word_bbox)
    render_cache: dict[tuple[int, int | None], tuple[Image.Image, tuple[int, int, int, int] | None]] = {}
    for segment_index, (_, words) in enumerate(segment_words_list):
        word_text = [word_info["word"] for word_info in words]
        render_cache[(segment_index, None)] = render_highlighted_text(word_text, None, font_size, max_text_width)
        for highlight_index in range(len(words)):
            render_cache[(segment_index, highlight_index)] = render_highlighted_text(
                word_text, highlight_index, font_size, max_text_width
            )

    # Word timing lookup: (segment_index, word_index) → (start, end) relative to part_start
    word_timings: dict[tuple[int, int], tuple[float, float]] = {}
    for segment_index, (_, words) in enumerate(segment_words_list):
        for word_index, word_info in enumerate(words):
            word_timings[(segment_index, word_index)] = (
                float(word_info["start"]) - part_start,
                float(word_info["end"]) - part_start,
            )

    def active_state(t: float) -> tuple[int, int | None] | None:
        for segment_index, (segment, words) in enumerate(segment_words_list):
            start = float(segment["start"]) - part_start
            end = float(segment["end"]) - part_start
            if start <= t < end:
                highlight_index = None
                for index, word_info in enumerate(words):
                    word_start = float(word_info["start"]) - part_start
                    word_end = float(word_info["end"]) - part_start
                    if word_start <= t < word_end:
                        highlight_index = index
                        break
                return segment_index, highlight_index
        return None

    def _animated_image(state: tuple[int, int | None], t: float) -> Image.Image:
        """Return the subtitle image with the pop animation applied for time t."""
        image, word_bbox = render_cache[state]
        segment_index, highlight_index = state

        if highlight_index is not None and word_bbox is not None:
            timing = word_timings.get((segment_index, highlight_index))
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

    clip = VideoClip(frame_function, duration=duration, has_constant_size=False)
    mask = VideoClip(mask_function, is_mask=True, duration=duration, has_constant_size=False)
    return clip.with_mask(mask)
