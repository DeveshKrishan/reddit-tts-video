import os
import ssl

import stable_whisper
from moviepy import AudioFileClip, CompositeVideoClip, ImageClip, VideoFileClip, concatenate_audioclips, vfx
from moviepy.video.fx.Loop import Loop

from config import load_config, load_sfx_config
from highlighted_subtitles import create_highlighted_subtitles_clip
from logger import logger
from parts import split_segments
from sound_effects import SoundCue, build_background_music_clip, build_intro_cues, detect_sound_cues, mix_sound_effects
from text_utils import clean_post_text
from thumbnail import create_thumbnail


def _crop_to_aspect(clip: VideoFileClip, target_width: int, target_height: int, crop_mode: str) -> VideoFileClip:
    """Crop and resize clip to the target 9:16 aspect ratio."""
    target_aspect = target_width / target_height
    src_w, src_h = clip.size
    src_aspect = src_w / src_h

    if src_aspect > target_aspect:
        crop_width = int(src_h * target_aspect)
        if crop_mode == "center":
            x_center = src_w / 2
            clip = clip.with_effects([vfx.Crop(x_center=x_center, width=crop_width, height=src_h)])
        else:
            clip = clip.with_effects([vfx.Crop(x1=0, width=crop_width, height=src_h)])
    elif src_aspect < target_aspect:
        crop_height = int(src_w / target_aspect)
        if crop_mode == "center":
            y_center = src_h / 2
            clip = clip.with_effects([vfx.Crop(y_center=y_center, width=src_w, height=crop_height)])
        else:
            clip = clip.with_effects([vfx.Crop(y1=0, width=src_w, height=crop_height)])

    return clip.with_effects([vfx.Resize((target_width, target_height))])


def _subtitle_position(
    clip: VideoFileClip,
    subtitle_h: int,
    position: str,
    bottom_margin: int = 320,
) -> tuple[str, int] | tuple[str, str]:
    if position == "center":
        y = max(0, (clip.h - subtitle_h) // 2)
        return ("center", y)
    if position == "lower_third":
        # Anchor the BOTTOM of the tallest possible subtitle block at a fixed
        # margin above the frame bottom, so YouTube Shorts UI buttons never
        # overlap the text. subtitle_h is the pre-computed max height from the
        # render cache (not the t=0 size), so all frames are positioned correctly.
        y = max(0, clip.h - bottom_margin - subtitle_h)
        return ("center", y)
    return ("center", "center")


def _output_path(output_folder: str, submission_id: str, part: int, total_parts: int) -> str:
    if total_parts == 1:
        return f"{output_folder}/{submission_id}.mov"
    return f"{output_folder}/{submission_id}_part{part}.mov"


def _offset_segment_timestamps(segments: list[dict], offset: float) -> list[dict]:
    """Shift Whisper segment and word timestamps by `offset` seconds."""
    if offset <= 0:
        return segments
    shifted: list[dict] = []
    for segment in segments:
        new_segment = dict(segment)
        new_segment["start"] = float(segment.get("start", 0)) + offset
        new_segment["end"] = float(segment.get("end", 0)) + offset
        words = []
        for word in segment.get("words") or []:
            words.append(
                {
                    **word,
                    "start": float(word.get("start", 0)) + offset,
                    "end": float(word.get("end", 0)) + offset,
                }
            )
        new_segment["words"] = words
        shifted.append(new_segment)
    return shifted


def _build_faded_thumbnail_clip(
    thumbnail_path: str,
    title_duration: float,
    fade_in: float,
    fade_out: float,
):
    """Build a centered post card clip that fades in/out over the gameplay via alpha."""
    hold_duration = max(title_duration, fade_in)
    clip_duration = hold_duration + fade_out
    card_clip = (
        ImageClip(thumbnail_path, transparent=True).with_duration(clip_duration).with_position(("center", "center"))
    )

    mask = card_clip.mask
    if mask is None:
        return card_clip, clip_duration

    mask_effects = []
    if fade_in > 0:
        mask_effects.append(vfx.FadeIn(fade_in))
    if fade_out > 0:
        mask_effects.append(vfx.FadeOut(fade_out))
    if mask_effects:
        card_clip = card_clip.with_mask(mask.with_effects(mask_effects))
    return card_clip, clip_duration


def _load_narration_audio(submission, thumbnail_enabled: bool) -> tuple[AudioFileClip, float]:
    """Load body narration and prepend title audio when the thumbnail intro is enabled."""
    config = load_config()
    tts_config = config.get("tts", {})
    audio_path = f"assets/audio/{submission.id}.mp3"
    title_audio_path = f"assets/audio/{submission.id}_title.mp3"
    body_audio = AudioFileClip(audio_path)

    if not thumbnail_enabled:
        return body_audio, 0.0

    if not os.path.exists(title_audio_path):
        from tts import generate_tts

        logger.info(f"Generating missing title narration for submission {submission.id}.")
        generate_tts(
            text=submission.title,
            output_path=title_audio_path,
            voice=tts_config.get("voice", "en-US-GuyNeural"),
            rate=tts_config.get("rate", "+10%"),
            pitch=tts_config.get("pitch", "+0Hz"),
        )

    title_audio = AudioFileClip(title_audio_path)
    title_duration = title_audio.duration
    audio = concatenate_audioclips([title_audio, body_audio])
    logger.info(f"Prepended title narration ({title_duration:.2f}s) for submission {submission.id}.")
    return audio, title_duration


def _apply_sfx_to_part(
    part_audio: AudioFileClip,
    all_cues: list[SoundCue],
    part_start: float,
    part_end: float,
    sfx_config: dict,
) -> AudioFileClip:
    """Filter cues to this part, make timestamps relative, and mix SFX."""
    part_cues = [
        SoundCue(
            effect=c.effect,
            start_time=c.start_time - part_start,
            end_time=c.end_time - part_start,
            volume=c.volume,
        )
        for c in all_cues
        if part_start <= c.start_time < part_end
    ]
    if not part_cues:
        return part_audio
    return mix_sound_effects(part_audio, part_cues, sfx_config)


def _render_part(
    base_clip: VideoFileClip,
    audio: AudioFileClip,
    part_start: float,
    part_end: float,
    part_segments: list[dict],
    output_path: str,
    subtitle_font_size: int,
    subtitle_position: str,
    subtitle_bottom_margin: int,
    subtitle_horizontal_padding: int,
    subtitle_max_words_per_group: int,
    fps: int,
    all_cues: list[SoundCue] | None = None,
    sfx_config: dict | None = None,
    bg_music_config: dict | None = None,
    thumbnail_path: str | None = None,
    title_duration: float = 0.0,
    thumbnail_fade_in: float = 0.0,
    thumbnail_fade_out: float = 0.0,
    subtitle_delay: float = 0.0,
) -> None:
    from moviepy import CompositeAudioClip

    duration = part_end - part_start
    part_audio = audio.subclipped(part_start, part_end)

    if base_clip.duration < duration:
        clip = Loop(duration=duration).copy().apply(base_clip)
    else:
        clip = base_clip.subclipped(0, duration)

    if all_cues is not None and sfx_config:
        part_audio = _apply_sfx_to_part(part_audio, all_cues, part_start, part_end, sfx_config)

    if bg_music_config:
        bg_clip = build_background_music_clip(bg_music_config, duration)
        if bg_clip is not None:
            part_audio = CompositeAudioClip([part_audio, bg_clip]).with_duration(duration)

    subtitles_clip, max_subtitle_h = create_highlighted_subtitles_clip(
        part_segments=part_segments,
        part_start=part_start,
        duration=duration,
        video_width=clip.w,
        font_size=subtitle_font_size,
        horizontal_padding=subtitle_horizontal_padding,
        max_words_per_group=subtitle_max_words_per_group,
        subtitle_delay=subtitle_delay,
    )
    clip = clip.with_audio(part_audio)
    pos = _subtitle_position(clip, max_subtitle_h, subtitle_position, subtitle_bottom_margin)

    layers: list = [clip]
    if thumbnail_path and title_duration > 0:
        card_clip, _ = _build_faded_thumbnail_clip(
            thumbnail_path,
            title_duration=title_duration,
            fade_in=thumbnail_fade_in,
            fade_out=thumbnail_fade_out,
        )
        layers.append(card_clip)
    layers.append(subtitles_clip.with_position(pos))
    final_video = CompositeVideoClip(layers)
    final_video.write_videofile(output_path, fps=fps)


def create_videos(submission) -> list[tuple[str, int, int]]:
    """Create one or more vertical YouTube Shorts for the submission."""
    ssl._create_default_https_context = ssl._create_unverified_context  # type: ignore[assignment]

    config = load_config()
    shorts = config.get("shorts", {})
    target_width = shorts.get("width", 1080)
    target_height = shorts.get("height", 1920)
    fps = shorts.get("fps", 30)
    max_duration = shorts.get("max_duration_seconds", 180)
    crop_mode = shorts.get("crop_mode", "center")
    subtitle_font_size = shorts.get("subtitle_font_size", 72)
    subtitle_position = shorts.get("subtitle_position", "lower_third")
    subtitle_bottom_margin = shorts.get("subtitle_bottom_margin", 320)
    subtitle_horizontal_padding = shorts.get("subtitle_horizontal_padding", 120)
    subtitle_max_words_per_group = shorts.get("subtitle_max_words_per_group", 4)
    thumbnail_config = config.get("thumbnail", {})
    thumbnail_enabled = thumbnail_config.get("enabled", False)
    thumbnail_fade_in = float(thumbnail_config.get("fade_in_seconds", 0.4))
    thumbnail_fade_out = float(thumbnail_config.get("fade_out_seconds", 0.5))
    thumbnail_sfx_volume = float(thumbnail_config.get("sfx_volume", 1.0))

    output_folder = "output"
    os.makedirs(output_folder, exist_ok=True)

    audio_path = f"assets/audio/{submission.id}.mp3"
    audio, title_duration = _load_narration_audio(submission, thumbnail_enabled)

    # Forced alignment: align the cleaned post text to the TTS audio so subtitles
    # display the exact words from the post rather than Whisper's transcription guess.
    # Using clean_post_text ensures the same text that was fed to TTS is used here,
    # eliminating mismatches from image markdown and bare URLs.
    model = stable_whisper.load_model("base")
    clean_text = clean_post_text(submission.selftext)
    result = model.align(audio_path, clean_text, language="en")
    segments = _offset_segment_timestamps(result.to_dict()["segments"], title_duration)
    base_clip = _crop_to_aspect(VideoFileClip("assets/video/input2.mp4"), target_width, target_height, crop_mode)

    # Alignment quality check: count segments with non-trivial duration. When
    # stable_whisper can't align the text (e.g. gaming jargon, symbols, poor TTS
    # match), failed segments get zero or near-zero duration and subtitles never
    # appear. Fall back to Whisper's own transcription which always gives reliable
    # timestamps — text may differ slightly but timing is accurate.
    valid_segs = sum(1 for s in segments if float(s.get("end", 0)) - float(s.get("start", 0)) > 0.1)
    total_segs = len(segments)
    logger.info(f"Forced alignment quality: {valid_segs}/{total_segs} segments have valid timing.")
    if total_segs > 0 and valid_segs / total_segs < 0.5:
        logger.warning(
            f"Forced alignment too unreliable ({valid_segs}/{total_segs} valid segments). "
            "Falling back to Whisper transcription for subtitle timestamps."
        )
        result = model.transcribe(audio_path, language="en", word_timestamps=True)
        segments = _offset_segment_timestamps(result.to_dict()["segments"], title_duration)

    sfx_section = load_sfx_config()
    sfx_enabled = sfx_section.get("enabled", False)
    sfx_confidence = sfx_section.get("confidence_threshold", 0.8)
    sfx_config: dict | None = sfx_section.get("sfx", {}) if sfx_enabled else None
    sfx_keywords: dict[str, list[str]] = sfx_section.get("keywords", {})
    all_cues: list[SoundCue] | None = (
        detect_sound_cues(clean_text, segments, sfx_keywords, sfx_confidence) if sfx_enabled else None
    )
    if all_cues:
        logger.info(f"Detected {len(all_cues)} sound cue(s) for submission {submission.id}.")

    bg_music_config: dict | None = sfx_section.get("background_music") if sfx_enabled else None

    intro_result = build_intro_cues(sfx_section.get("intro", {}))
    if intro_result:
        # Register each intro file under a unique effect key so mix_sound_effects
        # can resolve them independently (e.g. "intro_0", "intro_1").
        extra = {f"intro_{i}": path for i, (_, path) in enumerate(intro_result)}
        sfx_config = {**(sfx_config or {}), **extra}

    if audio.duration <= max_duration:
        parts = [(0.0, audio.duration, segments)]
    else:
        parts = split_segments(segments, max_duration)
        logger.info(f"Splitting submission {submission.id} into {len(parts)} Shorts parts.")

    total_parts = len(parts)
    created_videos: list[tuple[str, int, int]] = []
    thumbnail_path: str | None = None
    if thumbnail_enabled:
        thumbnail_path = create_thumbnail(submission)
        if sfx_config is not None and thumbnail_config.get("sfx"):
            sfx_config = {**sfx_config, "thumbnail_pop": thumbnail_config["sfx"]}

    for index, (part_start, part_end, part_segments) in enumerate(parts, start=1):
        part_cues: list[SoundCue] = list(all_cues or [])
        part_thumbnail_path: str | None = None
        part_subtitle_delay = 0.0
        if index == 1 and thumbnail_path:
            part_thumbnail_path = thumbnail_path
            part_subtitle_delay = max(title_duration, thumbnail_fade_in) + thumbnail_fade_out
            part_cues.insert(
                0,
                SoundCue(
                    effect="thumbnail_pop",
                    start_time=part_start,
                    end_time=part_start,
                    volume=thumbnail_sfx_volume,
                ),
            )
        if index == 1 and intro_result:
            # Build sequential intro cues: each clip starts right after the previous
            # one ends. Anchor the chain to part_start so the time-range filter in
            # _apply_sfx_to_part always includes them even with alignment offsets.
            offset = part_start
            intro_timed: list[SoundCue] = []
            for i, (cue_base, path) in enumerate(intro_result):
                intro_timed.append(
                    SoundCue(
                        effect=f"intro_{i}",
                        start_time=offset,
                        end_time=offset,
                        volume=cue_base.volume,
                    )
                )
                try:
                    with AudioFileClip(path) as _clip:
                        offset += _clip.duration
                except Exception:
                    logger.warning(f"Could not read duration of intro clip {path}; next cue may overlap.")
            part_cues = intro_timed + part_cues

        output_path = _output_path(output_folder, submission.id, index, total_parts)
        _render_part(
            base_clip=base_clip,
            audio=audio,
            part_start=part_start,
            part_end=part_end,
            part_segments=part_segments,
            output_path=output_path,
            subtitle_font_size=subtitle_font_size,
            subtitle_position=subtitle_position,
            subtitle_bottom_margin=subtitle_bottom_margin,
            subtitle_horizontal_padding=subtitle_horizontal_padding,
            subtitle_max_words_per_group=subtitle_max_words_per_group,
            fps=fps,
            all_cues=part_cues or None,
            sfx_config=sfx_config,
            bg_music_config=bg_music_config,
            thumbnail_path=part_thumbnail_path,
            title_duration=title_duration if part_thumbnail_path else 0.0,
            thumbnail_fade_in=thumbnail_fade_in if part_thumbnail_path else 0.0,
            thumbnail_fade_out=thumbnail_fade_out if part_thumbnail_path else 0.0,
            subtitle_delay=part_subtitle_delay,
        )
        created_videos.append((output_path, index, total_parts))
        logger.info(f"Created Short part {index}/{total_parts}: {output_path}")

    audio.close()
    base_clip.close()
    return created_videos
