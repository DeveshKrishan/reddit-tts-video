from __future__ import annotations

from typing import TYPE_CHECKING

from PIL import Image, ImageDraw, ImageFont

if TYPE_CHECKING:
    from moviepy import VideoClip

FONT_PATH = "assets/fonts/Poppins-Medium.ttf"
HIGHLIGHT_COLOR = "#39FF14"
TEXT_COLOR = "white"
STROKE_COLOR = "black"
STROKE_WIDTH = 10
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

# Punctuation stripped for on-screen captions (TikTok-style). Sentence chunking
# still uses the raw Whisper words so boundaries like "it." / "it's" stay intact.
_DISPLAY_STRIP = str.maketrans("", "", ".,;:\"'`")


def _display_word(word: str) -> str:
    """Return a caption-safe word with most punctuation removed (? and ! kept)."""
    cleaned = word.translate(_DISPLAY_STRIP)
    return cleaned or word


# Minimum font size when shrinking a group to fit the subtitle canvas width.
MIN_FONT_SIZE = 48


def _line_width_for_words(words: list[str], font: ImageFont.FreeTypeFont | ImageFont.ImageFont) -> int:
    """Measure rendered single-line width including inter-word gaps."""
    if not words:
        return 0
    measure = Image.new("RGBA", (1, 1))
    draw = ImageDraw.Draw(measure)
    width = 0
    for index, word in enumerate(words):
        bbox = draw.textbbox((0, 0), word, font=font, stroke_width=STROKE_WIDTH)
        word_w = bbox[2] - bbox[0]
        if index == 0:
            width = word_w
        else:
            width += int(draw.textlength(" ", font=font)) + WORD_EXTRA_GAP + word_w
    return width


def _fit_font_size(words: list[str], font_size: int, max_width: int) -> int:
    """Return the largest font size <= font_size where words fit within max_width."""
    size = font_size
    while size >= MIN_FONT_SIZE:
        font = _load_font(size)
        if _line_width_for_words(words, font) <= max_width:
            return size
        size -= 2
    return MIN_FONT_SIZE


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


def _wrap_word_lines(words: list[str]) -> list[list[str]]:
    """Return all words on one caption line — no line wrapping."""
    return [words] if words else [[]]


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
    """Render single-line caption text with one highlighted word.

    Returns:
        A tuple of (rendered image, highlighted_word_bbox).
        highlighted_word_bbox is (x, y, w, h) within the image, or None.
    """
    fitted_size = _fit_font_size(words, font_size, max_width)
    font = _load_font(fitted_size)
    measure = Image.new("RGBA", (max_width, 10), (0, 0, 0, 0))
    measure_draw = ImageDraw.Draw(measure)
    lines = _wrap_word_lines(words)

    line_metrics: list[tuple[list[str], int, int]] = []
    total_height = 0
    for line in lines:
        line_width = _line_width_for_words(line, font)
        line_text = " ".join(line)
        bbox = measure_draw.textbbox((0, 0), line_text, font=font, stroke_width=STROKE_WIDTH)
        line_height = bbox[3] - bbox[1]
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
        x = max(0, (max_width - line_width) // 2)
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


def _pad_image_to_height(
    image: Image.Image,
    word_bbox: tuple[int, int, int, int] | None,
    target_h: int,
) -> tuple[Image.Image, tuple[int, int, int, int] | None]:
    """Pad a rendered subtitle image to a fixed height, vertically centered."""
    if image.height >= target_h:
        return image, word_bbox
    padded = Image.new("RGBA", (image.width, target_h), (0, 0, 0, 0))
    offset_y = (target_h - image.height) // 2
    padded.paste(image, (0, offset_y), image)
    if word_bbox is None:
        return padded, None
    x, y, w, h = word_bbox
    return padded, (x, y + offset_y, w, h)


def _ends_sentence(word: str) -> bool:
    return bool(word) and word[-1] in ".!?"


def _split_into_sentences(flat: list[dict]) -> list[list[dict]]:
    """Split a flat word list into sentence-sized groups using trailing punctuation."""
    sentences: list[list[dict]] = []
    current: list[dict] = []
    for word_info in flat:
        current.append(word_info)
        if _ends_sentence(word_info["word"]):
            sentences.append(current)
            current = []
    if current:
        sentences.append(current)
    return sentences


def _chunk_sentence_by_width(
    sentence: list[dict],
    max_words_per_group: int,
    max_width: int,
    font_size: int,
) -> list[list[dict]]:
    """Pack words into single-line groups that fit within max_width."""
    font = _load_font(font_size)
    groups: list[list[dict]] = []
    current: list[dict] = []
    current_display: list[str] = []

    for word_info in sentence:
        display = _display_word(word_info["word"])
        trial_words = current + [word_info]
        trial_display = current_display + [display]

        over_word_cap = len(trial_display) > max_words_per_group
        over_width = _line_width_for_words(trial_display, font) > max_width

        if current and (over_word_cap or over_width):
            groups.append(current)
            current = [word_info]
            current_display = [display]
        else:
            current = trial_words
            current_display = trial_display

    if current:
        groups.append(current)
    return groups


def _rechunk_words(
    segment_words_list: list[tuple[dict, list[dict]]],
    max_words_per_group: int,
    max_width: int,
    font_size: int,
) -> list[list[dict]]:
    """Flatten Whisper word dicts and rechunk into on-screen groups.

    Groups never span sentence boundaries. Within each sentence, groups respect
    max_words_per_group and are split early when display width exceeds max_width.
    """
    flat = [w for _, words in segment_words_list for w in words]
    groups: list[list[dict]] = []
    for sentence in _split_into_sentences(flat):
        groups.extend(_chunk_sentence_by_width(sentence, max_words_per_group, max_width, font_size))
    return groups


def create_highlighted_subtitles_clip(
    part_segments: list[dict],
    part_start: float,
    duration: float,
    video_width: int,
    font_size: int,
    horizontal_padding: int = 120,
    max_words_per_group: int = 4,
    subtitle_delay: float = 0.0,
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

    # Rechunk by sentence, word cap, and pixel width so nothing clips horizontally.
    word_groups: list[list[dict]] = _rechunk_words(segment_words_list, max_words_per_group, max_text_width, font_size)

    # Cache: (group_index, highlight_index | None) → (image, highlighted_word_bbox)
    render_cache: dict[tuple[int, int | None], tuple[Image.Image, tuple[int, int, int, int] | None]] = {}
    for group_index, group in enumerate(word_groups):
        word_text = [_display_word(w["word"]) for w in group]
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
        if t < subtitle_delay:
            return None
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

    # Normalize every frame to the same height so vertical centering on the
    # video frame stays correct even when some groups wrap to more lines.
    max_subtitle_h = max((img.height for (img, _) in render_cache.values()), default=1)
    for key, (image, bbox) in list(render_cache.items()):
        render_cache[key] = _pad_image_to_height(image, bbox, max_subtitle_h)

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
            return np.zeros((max_subtitle_h, max_text_width, 3), dtype=np.uint8)
        return np.array(_animated_image(state, t).convert("RGB"))

    def mask_function(t: float) -> np.ndarray:
        state = active_state(t)
        if state is None:
            return np.zeros((max_subtitle_h, max_text_width), dtype=float)
        alpha = np.array(_animated_image(state, t).split()[-1], dtype=float) / 255.0
        return alpha

    clip = VideoClip(frame_function, duration=duration, has_constant_size=True)
    mask = VideoClip(mask_function, is_mask=True, duration=duration, has_constant_size=True)
    return clip.with_mask(mask), max_subtitle_h
