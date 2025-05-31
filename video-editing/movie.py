import os
import ssl

import whisper
from moviepy import AudioFileClip, CompositeVideoClip, TextClip, VideoFileClip
from moviepy.video.tools.subtitles import SubtitlesClip

ssl._create_default_https_context = ssl._create_unverified_context

OUTPUT_FOLDER = "assets/video"
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
clip = VideoFileClip("video/input3.mp4")

target_width = 1080
target_height = 1920
subtitle = TextClip(text="Test", font_size=48).with_duration(5)
# subtitle = subtitle.set_position(("center", clip.h - 150)).set_duration(5)  # Show for 5 seconds at the bottom

center_x, center_y = clip.w // 2, clip.h // 2

crop_x = center_x - target_width / 2
crop_y = center_y - target_height / 2
model = whisper.load_model("base")
result = model.transcribe("audio/1ehlrdd.mp3")

subtitles = [((segment["start"], segment["end"]), segment["text"]) for segment in result["segments"]]


def make_textclip(txt: str) -> TextClip:
    """Generates a TextClip for subtitles with the given text."""
    return TextClip(text=txt, font_size=24, color="white")


subtitles_clip = SubtitlesClip(subtitles=subtitles, make_textclip=make_textclip)

# clip = clip.without_audio()
clip = clip.cropped(x1=crop_x, y1=crop_y, width=target_width, height=target_height)

audio = AudioFileClip("audio/1ehlrdd.mp3")
clip = clip.with_audio(audio)
# clip.with_effects([afx.AudioFadeIn("00:00:06")])

# clip = clip.with_audio(audio)
final_video = CompositeVideoClip([clip, subtitles_clip])

final_video.write_videofile(f"{OUTPUT_FOLDER}/output_cropped.mov", fps=30)
