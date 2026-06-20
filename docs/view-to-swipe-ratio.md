# Design Doc: Improving View-to-Swipe Ratio on YouTube Shorts

**Status:** Draft / Proposal
**Author:** _TBD_
**Last updated:** 2026-06-19

---

## 1. Background & Problem

**View-to-swipe ratio** (a.k.a. swipe-away rate) measures how many viewers keep watching past the first few seconds vs. swiping to the next video. YouTube's Shorts algorithm rewards retention heavily: the longer people stay, the more aggressively it distributes the video.

Shorts data consistently shows ~60–70% of viewers who leave do so in the **first 3 seconds**. The dominant causes, in order of impact:

1. The opening doesn't hook them — too slow, vague, or boring.
2. Visuals look generic — indistinguishable from every other Reddit TTS channel.
3. Subtitles are hard to read (too small, off-screen, low contrast).
4. Narration voice/pacing feels robotic or rushed.

**Goal:** Reduce the first-3-second swipe rate and lift average view duration above ~40% of video length.

---

## 2. What the Pipeline Controls Today

| Factor | Where It Lives | Current State |
|--------|----------------|---------------|
| Post selection quality | `configs/reddit_config.yaml`, `fetch_content.py`, `reddit_sources.py` | Uses Reddit `top` ranking (upvote-validated) — considered solved |
| Opening hook (title card) | `thumbnail.py`, `videoeditor.py`, `youtube_config.yaml` | Part 1: centered Reddit post card + title TTS; subtitles hidden until card fades out |
| Subtitle readability | `highlighted_subtitles.py`, `youtube_config.yaml` | TikTok-style: 4 words on screen, 72px neon green highlight + pop animation |
| TTS voice/speed | `youtube_config.yaml` → `tts.py` | `en-US-GuyNeural`, +10% speed |
| Tags/discoverability | `youtube.py`, `youtube_config.yaml` | Tiered tag system in place |
| Video title | `youtube.py` | Post title + subreddit hashtag |
| Background footage | `videoeditor.py` | Single hardcoded `assets/video/input2.mp4` |
| Sound effects | `sound_effects.py`, `configs/sfx_config.yaml` | Keyword/profanity-triggered SFX; Emergency Radio Alert intro (delayed when thumbnail intro is on) + rake whoosh on card pop + background music |

---

## 3. Proposed Changes

Two changes are proposed for the first iteration, plus a set of follow-ups.

> **Note on content quality:** We deliberately do *not* add an upvote/length filter. Reddit's `top` ranking already surfaces community-validated, high-upvote posts, so an extra score filter would be redundant. Content selection is considered solved by the existing `top(time_filter=...)` fetch.

### 3.0 TikTok-Style Subtitle Chunking (Implemented — High Impact)

**Problem:** Full Whisper segments (5–15 words) appeared on screen at once. Viewers had to read ahead while listening, which increases cognitive load and swipe-away rate in the first few seconds.

**Implemented design:** Rechunk all aligned words into groups of 4 (configurable). Only one group is visible at a time; the currently spoken word is highlighted in neon green (`#39FF14`) with a pop animation. Font size increased from 42px → 72px so words are readable at a glance on mobile.

```yaml
shorts:
  subtitle_font_size: 72
  subtitle_max_words_per_group: 4   # 3–5 recommended for Shorts retention
  subtitle_horizontal_padding: 120
  subtitle_bottom_margin: 320
```

**Touch points:**
- `highlighted_subtitles.py` — `_rechunk_words()`, `create_highlighted_subtitles_clip(max_words_per_group=...)`
- `configs/youtube_config.yaml` — knobs above
- `tests/test_highlighted_subtitles.py` — unit tests for chunking and rendering

**Why it works:** Short-form platforms (TikTok, Reels) train viewers to expect small caption bursts. Showing 3–4 words at a time keeps eyes on the screen and reduces the "wall of text" effect that triggers swipes.

---

### 3.1 Title Card Hook Overlay (Implemented — High Impact)

**Problem:** Video starts directly into narration with no visual context; the viewer can't tell what the story is about in the first second.

**Implemented design:** On part 1 only, overlay a centered Reddit-style post card (transparent RGBA PNG) over the gameplay footage. The post title is narrated via a separate `{id}_title.mp3` track prepended to the body audio; card visibility is driven by title duration plus configurable fade in/out. Subtitles stay hidden until the card is fully gone (`subtitle_delay = title_duration + fade_out`).

- Rendered with PIL in `thumbnail.render_post_card()` — wraps/shrinks long titles (72px → 28px).
- Alpha mask fade (`FadeIn`/`FadeOut` on mask, not RGB) avoids a black flash on transparent pixels.
- Rake whoosh SFX at card pop (`t=0`); Emergency Radio intro stinger delayed until after title narration.

```yaml
# configs/youtube_config.yaml
thumbnail:
  enabled: true
  card_width: 900
  fade_in_seconds: 0.4
  fade_out_seconds: 0.5
  username: "The Daily Redditor"
  sfx: assets/sfx/Rake Swing Whoosh Close.mp3
  sfx_volume: 0.45
```

**Touch points:**
- `thumbnail.py` — `render_post_card()` RGBA card PNG
- `main.py` — generates `{id}_title.mp3` when thumbnail is enabled
- `videoeditor.py` — card overlay, title audio prepend, SFX timing, subtitle delay
- `highlighted_subtitles.py` — `subtitle_delay` parameter
- `configs/sfx_config.yaml` — `sfx.thumbnail_pop`
- `tests/test_thumbnail.py` — unit tests for card rendering

**Why it works:** Showing and *hearing* the title immediately tells the viewer *"this is a story about X"* so they opt in before body narration. Highest-leverage fix for the first-3-second drop.

**Decisions:**
- Part 1 only (multi-part stories keep the hook on the opening segment).
- Long titles wrap and shrink font rather than hard-truncate.

---

### 3.2 Intro Sound Effect (Implemented — Medium Impact)

**Problem:** The audio previously opened cold on the narration. A short, punchy intro sound signals *"a story is starting"* and pairs with the visual hook.

**Implemented design:** Reuse the existing SFX engine. An intro cue for part 1 fires via `build_intro_cues()` in `sound_effects.py`. When the thumbnail intro is enabled, this stinger is delayed until after title narration so the spoken hook is audible; the rake whoosh at `t=0` covers the card pop instead.

**Sound asset (YouTube Audio Library):**

| File | Character |
|------|-----------|
| `Emergency Radio Alert.mp3` | Urgent EAS-style alert — strong attention grab at t=0 |

```yaml
# configs/sfx_config.yaml
intro:
  enabled: true
  files:
    - assets/sfx/Emergency Radio Alert.mp3
  volume: 1.0
  parts: first_only
```

**Touch points:**
- `configs/sfx_config.yaml` — `intro` section
- `sound_effects.py` / `videoeditor.py` — `build_intro_cues()`, mixed via existing `mix_sound_effects` step
- `assets/sfx/README.md` — documents the intro filename

**Open questions:**
- Volume level — tune after local preview if the alert clips the first narrated word.
- First part only, or every part? Currently `first_only`.

---

## 4. Follow-ups (Out of Scope for First Iteration)

- **Footage variety:** Rotate among 3–5 background clips (random pick per video) to keep visuals fresh and lift session watch time. Requires multiple files in `assets/video/`.
- **TTS voice testing:** A/B `en-US-ChristopherNeural` (authoritative, conflict posts) and `en-US-AriaNeural` (relationship/AITAH) vs. current default. Possibly drop rate to `+5%` for clarity.
- **Upload timing experiments:** Test 12–2pm and 7–9pm PST slots vs. current 7am.

---

## 5. Success Metrics

| Metric | Target | Source |
|--------|--------|--------|
| Average view duration | > 40% of length | Studio → Engagement |
| Swipe-away rate (first 30s) | < 30% | Studio → Audience Retention |
| CTR from Shorts shelf | > 5% | Studio → Reach |
| Views per upload | Beat baseline | Studio → Content |

Read the retention graph per video: a sharp drop at 0–3s means the hook needs work; a drop at a specific timestamp means the content there is losing people.

---

## 6. Rollout Plan

1. ~~Land subtitle chunking (3.0)~~ — shipped on `feat/bigger-subtitles`.
2. ~~Land intro sound (3.2)~~ — shipped on `feat/cursor-skills`.
3. ~~Land title card (3.1)~~ — shipped on `feat/thumbnail-intro`.
4. Run with `DEBUG=True` locally; review output videos manually.
5. Monitor retention for 1–2 weeks vs. baseline with thumbnail intro enabled.
6. Decide on follow-ups based on metrics.
