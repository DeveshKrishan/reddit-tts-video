import os

from logger import logger

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
    logger.info(f"Created folder: {folder}")
