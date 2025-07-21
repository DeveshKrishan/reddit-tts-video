import os
import ssl

import whisper
from moviepy import AudioFileClip, CompositeVideoClip, TextClip, VideoFileClip
from moviepy.video.fx.Loop import Loop
from moviepy.video.tools.subtitles import SubtitlesClip


def create_video(submission) -> None:
    """Create a video for the submission with audio and subtitles"""
    ssl._create_default_https_context = ssl._create_unverified_context

    OUTPUT_FOLDER = "output"
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    clip = VideoFileClip("assets/video/input2.mp4")
    audio = AudioFileClip(f"assets/audio/{submission.id}.mp3")
    duration = audio.duration
    # Loop the video if it's shorter than the audio
    if clip.duration < duration:
        effect = Loop(duration=duration).copy()
        clip = effect.apply(clip)
    else:
        clip = clip.subclipped(0, duration)

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

    clip = clip.with_audio(audio)

    final_video = CompositeVideoClip([clip, subtitles_clip.with_position(("center", "center"))])

    final_video.write_videofile(f"{OUTPUT_FOLDER}/{submission.id}.mov", fps=30)
