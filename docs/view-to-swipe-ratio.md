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
| Opening hook (title card) | `videoeditor.py` | Not implemented — starts straight into narration |
| Subtitle readability | `highlighted_subtitles.py`, `youtube_config.yaml` | TikTok-style: 4 words on screen, 72px neon green highlight + pop animation |
| TTS voice/speed | `youtube_config.yaml` → `tts.py` | `en-US-GuyNeural`, +10% speed |
| Tags/discoverability | `youtube.py`, `youtube_config.yaml` | Tiered tag system in place |
| Video title | `youtube.py` | Post title + subreddit hashtag |
| Background footage | `videoeditor.py` | Single hardcoded `assets/video/input2.mp4` |
| Sound effects | `sound_effects.py`, `configs/sfx_config.yaml` | Keyword/profanity-triggered SFX; Emergency Radio Alert intro + background music |

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

### 3.1 Title Card Hook Overlay (Proposal — High Impact)

**Problem:** Video starts directly into narration with no visual context; the viewer can't tell what the story is about in the first second.

**Proposed design:** Overlay the Reddit post title as a styled card for the first ~2 seconds, fading out as narration begins.

- Rendered with PIL using the subtitle font (`Poppins-Medium`).
- Semi-transparent dark panel behind text for readability over any footage.
- Fades out over ~0.3s at the 2s mark.

```yaml
shorts:
  title_card_enabled: true
  title_card_duration: 2.0      # seconds visible
  title_card_fade_duration: 0.3 # fade-out duration
```

**Touch points:**
- `videoeditor.py` — compose a title-card clip over the first N seconds in `_render_part`.
- new helper (e.g. `title_card.py`) — render the styled title image.
- `youtube_config.yaml` — config knobs above.

**Why it works:** Showing the title immediately tells the viewer *"this is a story about X"* so they opt in before narration. Highest-leverage fix for the first-3-second drop.

**Open questions:**
- Show on every part, or only part 1?
- Truncate long titles to N lines, or shrink font to fit?

---

### 3.2 Intro Sound Effect (Implemented — Medium Impact)

**Problem:** The audio previously opened cold on the narration. A short, punchy intro sound signals *"a story is starting"* and pairs with the visual hook.

**Implemented design:** Reuse the existing SFX engine. An always-on intro cue at `t=0` for part 1 fires via `build_intro_cues()` in `sound_effects.py`.

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
- **Narrated title line:** Prepend the post title as the first TTS line so the hook is heard, not just shown.
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
3. Land title card (3.1) behind `title_card_enabled`.
4. Run with `DEBUG=True` locally; review output videos manually.
5. Enable in production config; monitor retention for 1–2 weeks vs. baseline.
6. Decide on follow-ups based on metrics.
