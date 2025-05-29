from moviepy import VideoFileClip, vfx

OUTPUT_FOLDER = "assets/video"
clip = VideoFileClip("video/input2.mp4")

target_width = 1080
target_height = 1920

# Center crop to phone aspect ratio (9:16)

# Resize the cropped video to width 460, maintaining aspect ratio
clip_resized = clip.with_effects(
    [
        vfx.Resize(width=target_width, height=target_height),
    ]
)

clip_resized.write_videofile("output_cropped.mp4", codec="libx264", fps=30)
