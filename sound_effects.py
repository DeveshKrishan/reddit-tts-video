"""Contextual sound effects engine.

Detects trigger keywords and profanity in raw Reddit text, maps them to
Whisper word timestamps, and mixes the corresponding SFX clips into the
TTS audio track.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np
    from moviepy import AudioArrayClip, AudioFileClip, CompositeAudioClip

from logger import logger

PROFANITY_LIST_PATH = Path("assets/profanity_list.txt")


@dataclass
class SoundCue:
    effect: str
    start_time: float
    end_time: float
    volume: float = 1.0


def _load_profanity_list() -> set[str]:
    if not PROFANITY_LIST_PATH.exists():
        logger.warning(f"Profanity list not found at {PROFANITY_LIST_PATH}; bleep detection disabled.")
        return set()
    return {w.strip().lower() for w in PROFANITY_LIST_PATH.read_text().splitlines() if w.strip()}


def _flatten_word_timestamps(segments: list[dict]) -> list[dict]:
    """Flatten Whisper segments into a list of {word, start, end} dicts."""
    words: list[dict] = []
    for segment in segments:
        for w in segment.get("words") or []:
            word = w.get("word", "").strip().lower()
            if word:
                words.append(
                    {
                        "word": word,
                        "start": float(w["start"]),
                        "end": float(w["end"]),
                    }
                )
    return words


def _find_word_timestamp(word: str, flat_words: list[dict]) -> dict | None:
    """Return the first Whisper entry that matches `word` (strips punctuation)."""
    target = word.lower().strip()
    for entry in flat_words:
        clean = re.sub(r"[^\w]", "", entry["word"])
        if clean == target:
            return entry
    return None


def detect_sound_cues(
    raw_text: str,
    segments: list[dict],
    keyword_categories: dict[str, list[str]],
    confidence_threshold: float = 0.8,
) -> list[SoundCue]:
    """Detect sound cue trigger points from raw Reddit text and Whisper segments.

    Profanity is detected against the raw text before TTS synthesis (more
    reliable than Whisper transcription). Keyword categories are also scanned
    in the raw text and mapped to Whisper word timestamps for precise placement.

    Args:
        raw_text: The original Reddit post body text.
        segments: Whisper result["segments"] list (must have word_timestamps=True).
        keyword_categories: Mapping of effect name → trigger keyword list, loaded
            from the ``sound_effects.keywords`` section of configs/sfx_config.yaml.
        confidence_threshold: Minimum match confidence; exact keyword matches
            score 1.0, fuzzy matches below this value are discarded.

    Returns:
        List of SoundCues sorted by start_time.
    """
    cues: list[SoundCue] = []
    flat_words = _flatten_word_timestamps(segments)
    profanity_set = _load_profanity_list()
    text_lower = raw_text.lower()

    # --- Profanity bleeps (scan every Whisper word against the profanity list) ---
    for entry in flat_words:
        clean = re.sub(r"[^\w]", "", entry["word"])
        if clean in profanity_set:
            cues.append(
                SoundCue(
                    effect="profanity",
                    start_time=entry["start"],
                    end_time=entry["end"],
                    volume=1.0,
                )
            )
            logger.debug(f"Profanity bleep cue at t={entry['start']:.2f}s: '{entry['word']}'")

    # --- Keyword categories (scan raw text, map to first matching Whisper word) ---
    for category, keywords in keyword_categories.items():
        triggered = False
        for keyword in keywords:
            if keyword not in text_lower:
                continue

            # Exact phrase match → confidence 1.0
            confidence = 1.0
            if confidence < confidence_threshold:
                continue

            first_word = re.sub(r"[^\w]", "", keyword.split()[0])
            keyword_entry = _find_word_timestamp(first_word, flat_words)
            if keyword_entry is None:
                continue

            cues.append(
                SoundCue(
                    effect=category,
                    start_time=keyword_entry["start"],
                    end_time=keyword_entry["end"],
                    volume=0.7,
                )
            )
            logger.debug(f"Sound cue [{category}] at t={keyword_entry['start']:.2f}s: '{keyword}'")
            triggered = True
            break  # one trigger per category per video

        if triggered:
            continue

    return sorted(cues, key=lambda c: c.start_time)


def _duck_tts(audio: AudioFileClip, profanity_cues: list[SoundCue]) -> AudioArrayClip:
    """Return a copy of the TTS audio with profanity word regions silenced."""
    import numpy as np
    from moviepy import AudioArrayClip

    fps = audio.fps
    frames: np.ndarray = audio.to_soundarray(fps=fps).copy()

    # Ensure 2-D shape (n_samples, n_channels) for AudioArrayClip
    if frames.ndim == 1:
        frames = frames[:, np.newaxis]

    for cue in profanity_cues:
        s = max(0, int(cue.start_time * fps))
        e = min(len(frames), int(cue.end_time * fps))
        frames[s:e] = 0

    return AudioArrayClip(frames, fps=fps)


def mix_sound_effects(
    audio: AudioFileClip,
    cues: list[SoundCue],
    sfx_config: dict,
) -> CompositeAudioClip:
    """Overlay contextual SFX clips onto the TTS audio track.

    For profanity cues the underlying TTS audio is silenced (ducked) for the
    word's duration before the bleep tone is overlaid. All other effects are
    simply mixed additively at the cue's start_time.

    Args:
        audio: The TTS audio clip for this part (already subclipped to part bounds).
        cues: Sound cues with timestamps relative to this part's start.
        sfx_config: Mapping of effect name → file path (from configs/sfx_config.yaml).

    Returns:
        A CompositeAudioClip with the same duration as the input audio.
    """
    from moviepy import AudioFileClip, CompositeAudioClip, afx

    if not cues:
        return CompositeAudioClip([audio])

    profanity_cues = [c for c in cues if c.effect == "profanity"]
    base_audio: AudioFileClip | AudioArrayClip = _duck_tts(audio, profanity_cues) if profanity_cues else audio

    clips: list = [base_audio]

    for cue in cues:
        sfx_path = sfx_config.get(cue.effect)
        if not sfx_path:
            continue
        if not Path(sfx_path).exists():
            logger.warning(f"SFX file not found for '{cue.effect}': {sfx_path} — skipping.")
            continue

        sfx_clip = AudioFileClip(sfx_path).with_start(cue.start_time).with_effects([afx.MultiplyVolume(cue.volume)])
        clips.append(sfx_clip)
        logger.debug(f"Mixing SFX '{cue.effect}' at t={cue.start_time:.2f}s from {sfx_path}")

    composite = CompositeAudioClip(clips)
    return composite.with_duration(audio.duration)
