"""Utilities for cleaning raw Reddit post text before TTS and alignment."""

from __future__ import annotations

import re


def clean_post_text(text: str) -> str:
    """Strip markdown and URLs that TTS would mangle or skip.

    Edge TTS reads everything literally, so image embeds and bare URLs produce
    garbled or skipped audio. Cleaning the text before synthesis ensures the
    audio matches what stable_whisper/Whisper sees during alignment, which is
    required for subtitles to show at the correct timestamps.

    Transformations applied (in order):
    - Markdown images ``![alt](url)``  → removed entirely (nothing spoken)
    - Markdown links ``[text](url)``   → keep link text, drop URL
    - Bare http/https URLs             → removed
    - Reddit HTML entities             → decoded (&amp; &lt; &gt; &nbsp;)
    - Zero-width Unicode characters    → removed
    - Excessive blank lines            → collapsed to two newlines
    """
    # Markdown images: ![alt text](url) — nothing spoken, drop completely
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    # Markdown links: [link text](url) — keep the visible text only
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    # Bare URLs (http / https)
    text = re.sub(r"https?://\S+", "", text)
    # Common Reddit HTML entities
    text = (
        text.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&nbsp;", " ")
        .replace("&#x200B;", "")
    )
    # Zero-width and invisible Unicode
    text = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", text)
    # Collapse runs of 3+ blank lines to two newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
