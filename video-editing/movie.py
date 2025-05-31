import os

from moviepy import AudioFileClip, CompositeVideoClip, VideoFileClip

OUTPUT_FOLDER = "assets/video"
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
clip = VideoFileClip("video/input3.mp4")

target_width = 1080
target_height = 1920

center_x, center_y = clip.w // 2, clip.h // 2

crop_x = center_x - target_width / 2
crop_y = center_y - target_height / 2

# clip = clip.without_audio()
clip = clip.cropped(x1=crop_x, y1=crop_y, width=target_width, height=target_height)


audio = AudioFileClip("audio/1ehlrdd.mp3")
clip = clip.with_audio(audio)
# clip.with_effects([afx.AudioFadeIn("00:00:06")])

# clip = clip.with_audio(audio)
final_video = CompositeVideoClip([clip])

final_video.write_videofile(f"{OUTPUT_FOLDER}/output_cropped.mov", fps=30)
