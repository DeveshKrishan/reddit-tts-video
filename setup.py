import os

folders = [
    "assets/audio",
    "assets/video",
    "assets/emojis",
    "assets/fonts",
    "assets/thumbnails",
    "output",
]

for folder in folders:
    os.makedirs(folder, exist_ok=True)
    print(f"Created folder: {folder}")
