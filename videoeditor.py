import os
import ssl

import stable_whisper
from moviepy import AudioFileClip, CompositeVideoClip, VideoFileClip, vfx
from moviepy.video.fx.Loop import Loop

from config import load_config, load_sfx_config
from highlighted_subtitles import create_highlighted_subtitles_clip
from logger import logger
from parts import split_segments
from sound_effects import SoundCue, detect_sound_cues, mix_sound_effects


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
    subtitles_clip,
    position: str,
    bottom_margin: int = 320,
) -> tuple[str, int] | tuple[str, str]:
    if position == "lower_third":
        # Anchor the bottom of the subtitle block at a fixed margin above the frame bottom.
        # This prevents multi-line wrapping from pushing text off-screen or under
        # YouTube Shorts' overlay buttons.
        subtitle_h = subtitles_clip.size[1] if subtitles_clip.size[1] > 1 else 0
        y = max(0, clip.h - bottom_margin - subtitle_h)
        return ("center", y)
    return ("center", "center")


def _output_path(output_folder: str, submission_id: str, part: int, total_parts: int) -> str:
    if total_parts == 1:
        return f"{output_folder}/{submission_id}.mov"
    return f"{output_folder}/{submission_id}_part{part}.mov"


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
    fps: int,
    all_cues: list[SoundCue] | None = None,
    sfx_config: dict | None = None,
) -> None:
    duration = part_end - part_start
    part_audio = audio.subclipped(part_start, part_end)

    if base_clip.duration < duration:
        clip = Loop(duration=duration).copy().apply(base_clip)
    else:
        clip = base_clip.subclipped(0, duration)

    if all_cues is not None and sfx_config:
        part_audio = _apply_sfx_to_part(part_audio, all_cues, part_start, part_end, sfx_config)

    subtitles_clip = create_highlighted_subtitles_clip(
        part_segments=part_segments,
        part_start=part_start,
        duration=duration,
        video_width=clip.w,
        font_size=subtitle_font_size,
    )
    clip = clip.with_audio(part_audio)
    pos = _subtitle_position(clip, subtitles_clip, subtitle_position, subtitle_bottom_margin)
    final_video = CompositeVideoClip([clip, subtitles_clip.with_position(pos)])
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
    subtitle_font_size = shorts.get("subtitle_font_size", 42)
    subtitle_position = shorts.get("subtitle_position", "lower_third")
    subtitle_bottom_margin = shorts.get("subtitle_bottom_margin", 320)

    output_folder = "output"
    os.makedirs(output_folder, exist_ok=True)

    audio_path = f"assets/audio/{submission.id}.mp3"
    base_clip = _crop_to_aspect(VideoFileClip("assets/video/input2.mp4"), target_width, target_height, crop_mode)
    audio = AudioFileClip(audio_path)

    # Forced alignment: align the original post text to the TTS audio so subtitles
    # display the exact words from the post rather than Whisper's transcription guess.
    model = stable_whisper.load_model("base")
    result = model.align(audio_path, submission.selftext, language="en")
    segments = result.to_dict()["segments"]

    sfx_section = load_sfx_config()
    sfx_enabled = sfx_section.get("enabled", False)
    sfx_confidence = sfx_section.get("confidence_threshold", 0.8)
    sfx_config = sfx_section.get("sfx", {}) if sfx_enabled else None
    sfx_keywords: dict[str, list[str]] = sfx_section.get("keywords", {})
    all_cues = detect_sound_cues(submission.selftext, segments, sfx_keywords, sfx_confidence) if sfx_enabled else None
    if all_cues:
        logger.info(f"Detected {len(all_cues)} sound cue(s) for submission {submission.id}.")

    if audio.duration <= max_duration:
        parts = [(0.0, audio.duration, segments)]
    else:
        parts = split_segments(segments, max_duration)
        logger.info(f"Splitting submission {submission.id} into {len(parts)} Shorts parts.")

    total_parts = len(parts)
    created_videos: list[tuple[str, int, int]] = []

    for index, (part_start, part_end, part_segments) in enumerate(parts, start=1):
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
            fps=fps,
            all_cues=all_cues,
            sfx_config=sfx_config,
        )
        created_videos.append((output_path, index, total_parts))
        logger.info(f"Created Short part {index}/{total_parts}: {output_path}")

    audio.close()
    base_clip.close()
    return created_videos
