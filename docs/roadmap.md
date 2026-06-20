# Reddit-TTS-Video

## 1. Project Vision & Goals

- What problem does the app solve?
    - Lack of diversity in the AI - generated reddit video space
- Who are the target users?
    - Viewers who already watch AI - generated content specifically. 
- What is the MVP (Minimum Viable Product)?
    - Grabbing a Reddit story and generating a short form of content accessible to users

## 2. Feature Brainstorm

- Core features (list ideas)
    Paste link from a Reddit URL and generate a video
    Connect to social media platforms such as YouTube, TikTok, Instagram to upload videos to
- Nice-to-have features
    LLM rating "new" posts and adding them to a queue for videos to be processed and uploaded to social media platforms.
- Stretch goals

## 3. Architecture & Tech Stack

- Major components/modules
    - AI generation software
    - Backend is in Python
- Libraries & frameworks to consider
    TBD
- Data storage (DB, files, etc.)
    TBD

## 4. Milestones & Timeline

- Phase 1: Initial setup & scaffolding
    - Webscrape reddit stories
    - Find library that can use tts 
    - Find library that can automate video editing
    - Build a end to end process to input webscraped reddit story into local storage
    - Generate background gameplay to use
- Phase 2: Upload to Social Media Platforms
    - Build an uploader that uploads local shorts to YouTube
- Phase 3: Integrate LLM to rate videos
    - Highly rated videos would be prioritized in uploading process in a queue
    - Train LLM to recognise "Best Post" of the day characteristics and properties to further improve rating efficacy. Could allow to webscrape by "new" posts
- Phase 4: Capture metadata about processes
    - Have LLMs store metrics about render time, memory usage to improve efficency in a database

## 5. Sound Effects Engine

### Overview

Automatically overlay contextual sound effects onto the generated video based on the words and sentiment in the narrated text. The goal is to increase engagement by making videos feel more dynamic and reactive — similar to the "reaction sounds" used in popular Reddit TTS channels.

### Effect Categories

| Category | Trigger | Example Sound |
|---|---|---|
| **Profanity bleep** | Detected curse words (via word list) | TV-style bleep tone over the word's timestamp |
| **Shocking / OMG** | Keywords: `unbelievable`, `no way`, `insane`, `wtf`, `shocked`, `omg`, `horrified` | Dramatic sting / gasp SFX |
| **Funny / Comedic** | Keywords: `lmao`, `lol`, `hilarious`, `rofl`, `dying`, `💀`, `😂` | Rimshot, laugh track, or cartoon boing |
| **Sad / Emotional** | Keywords: `died`, `passed away`, `heartbroken`, `crying`, `tragic` | Sad violin sting |
| **Tension / Suspense** | Keywords: `then it happened`, `what happened next`, `suddenly` | Low drone / suspense riser |

### Implementation Plan

#### Phase 1 — Keyword detection & timestamp mapping
- Add a `sound_effects.py` module with a `detect_sound_cues(word_timestamps)` function
- `word_timestamps` come from the existing Whisper output (already produced in `highlighted_subtitles.py`)
- Each cue returns `{ "effect": "<category>", "start_time": float, "volume": float }`
- Bleep detection uses a configurable profanity word list (stored in `assets/profanity_list.txt`); other categories use keyword/regex matching

#### Phase 2 — Asset management
- Store royalty-free SFX files in `assets/sfx/` (e.g. `bleep.wav`, `rimshot.wav`, `gasp.wav`)
- Add a mapping in `config.yaml` or a new `sfx_config.yaml`:
  ```yaml
  sfx:
    profanity: assets/sfx/bleep.wav
    shocking: assets/sfx/gasp.wav
    funny: assets/sfx/rimshot.wav
    sad: assets/sfx/sad_sting.wav
    suspense: assets/sfx/riser.wav
  ```

#### Phase 3 — Audio mixing
- In `videoeditor.py`, after the TTS audio track is assembled, call `mix_sound_effects(tts_audio, cues, sfx_config)` from `sound_effects.py`
- Use `pydub` or MoviePy's `CompositeAudioClip` to overlay each SFX at its `start_time` with independent volume control
- For profanity bleeps, duck (mute) the underlying TTS audio for the duration of the word before overlaying the bleep tone

#### Phase 4 — Configuration & toggle
- Add a `sound_effects_enabled: true/false` flag to `config.yaml` so it can be disabled per-run
- Allow per-category overrides (e.g. disable bleeps but keep funny SFX)
- Expose settings in `reddit_config.yaml` under a `sound_effects:` section

### Thumbnail intro (part 1 hook)

Shipped on `feat/thumbnail-intro`. Before body narration on part 1, the pipeline:

1. Generates `{id}_title.mp3` (title-only TTS) and prepends it to the body audio track.
2. Overlays a centered Reddit post card PNG (`thumbnail.render_post_card()`) with mask-based fade in/out.
3. Plays a rake whoosh at `t=0` and delays the Emergency Radio intro stinger until after the title finishes.
4. Hides highlighted subtitles until `title_duration + fade_out_seconds`.

Configure via `thumbnail:` in `configs/youtube_config.yaml`. See `docs/view-to-swipe-ratio.md` §3.1 for retention rationale.

### Decisions

- **Bleep detection source:** Run on the raw Reddit text (before TTS). Whisper sometimes mishears or omits profanity, so scanning the source text before synthesis gives more reliable detection. The word's timestamp is still sourced from Whisper for precise audio ducking.
- **Confidence threshold:** Yes — keyword matches will require a minimum confidence score to reduce false positives. Exact keywords score 1.0; fuzzy/partial matches will be filtered at a configurable threshold (default `0.8`) stored in `sfx_config.yaml`.
- **SFX source:** Use the [YouTube Audio Library](https://studio.youtube.com/channel/UCxxxx/music) meme/sound-effects section. It is royalty-free, already cleared for YouTube uploads, and contains popular meme stings (vine boom, bruh, wrong answer, etc.) that fit the Reddit TTS genre well.

---

## 6. Risks & Unknowns

- Technical challenges
    - Storing generated content
    - Finding the correct video-editing style
    - Knowledge about training a LLM
- Open questions
    - Where are we going to store generated content? 
    - What database will we use?