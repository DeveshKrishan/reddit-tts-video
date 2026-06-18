"""Text-to-speech synthesis via Microsoft Edge TTS (neural voices).

Edge TTS is free, requires no API key, and produces natural-sounding
neural voices well-suited for Reddit story narration.

Voice options (en-US neural):
  en-US-GuyNeural          — male, conversational (good default for Reddit)
  en-US-ChristopherNeural  — male, authoritative
  en-US-AriaNeural         — female, natural/expressive
  en-US-JennyNeural        — female, friendly

Rate/pitch use CSS Speech relative notation:
  rate:  "+10%"  → 10% faster  |  "-10%"  → 10% slower  |  "+0%"  → default
  pitch: "+5Hz"  → slightly higher  |  "+0Hz" → default
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import edge_tts

from logger import logger


async def _synthesise(text: str, output_path: str, voice: str, rate: str, pitch: str) -> None:
    communicate = edge_tts.Communicate(text, voice=voice, rate=rate, pitch=pitch)
    await communicate.save(output_path)


def generate_tts(
    text: str,
    output_path: str,
    voice: str = "en-US-GuyNeural",
    rate: str = "+10%",
    pitch: str = "+0Hz",
) -> None:
    """Synthesise *text* to *output_path* using Microsoft Edge neural TTS.

    Args:
        text: The plain-text content to narrate.
        output_path: Destination file path (MP3).
        voice: Edge TTS voice name.
        rate: Speaking rate relative to default (e.g. "+10%", "-5%").
        pitch: Pitch offset in Hz (e.g. "+0Hz", "+5Hz").
    """
    logger.info(f"Generating TTS → {Path(output_path).name}  voice={voice}  rate={rate}  pitch={pitch}")
    asyncio.run(_synthesise(text, output_path, voice, rate, pitch))
