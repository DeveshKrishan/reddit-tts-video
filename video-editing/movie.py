from moviepy.editor import VideoFileClip

clip = VideoFileClip("input.mp4")

target_width = 1080
target_height = 1920

# Center crop to phone aspect ratio (9:16)
clip_cropped = clip.crop(x_center=clip.w // 2, y_center=clip.h // 2, width=target_width, height=target_height)

clip_cropped.write_videofile("output_cropped.mp4", codec="libx264", fps=30)
