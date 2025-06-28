import os
import ssl

import whisper
from moviepy import AudioFileClip, CompositeVideoClip, TextClip, VideoFileClip
from moviepy.video.tools.subtitles import SubtitlesClip


def create_video(submission) -> None:
    ssl._create_default_https_context = ssl._create_unverified_context

    OUTPUT_FOLDER = "output"
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    clip = VideoFileClip("assets/video/input2.mp4")

    audio = AudioFileClip(f"assets/audio/{submission.id}.mp3")
    duration = min(clip.duration, audio.duration)
    clip = clip.subclipped(0, duration)

    # target_width = 1080
    # target_height = 1920

    # center_x, center_y = clip.w // 2, clip.h // 2

    # crop_x = center_x - target_width / 2
    # crop_y = center_y - target_height / 2
    model = whisper.load_model("base")
    result = model.transcribe(f"assets/audio/{submission.id}.mp3")

    subtitles = [((segment["start"], segment["end"]), segment["text"]) for segment in result["segments"]]

    def make_textclip(txt: str) -> TextClip:
        """Generates a TextClip for subtitles with the given text, centered on the video."""
        return TextClip(
            text=txt,
            font_size=48,
            color="white",
            text_align="center",
            stroke_color="black",
            stroke_width=5,
            size=(clip.w, clip.h),
            method="caption",
        )

    subtitles_clip = SubtitlesClip(subtitles=subtitles, make_textclip=make_textclip)

    # clip = clip.cropped(x1=crop_x, y1=crop_y, width=target_width, height=target_height)

    clip = clip.with_audio(audio)

    final_video = CompositeVideoClip([clip, subtitles_clip.with_position(("center", "center"))])

    final_video.write_videofile(f"{OUTPUT_FOLDER}/{submission.id}.mov", fps=30)
