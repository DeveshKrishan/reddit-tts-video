# Design Doc: Improving View-to-Swipe Ratio on YouTube Shorts

**Status:** Draft / Proposal
**Author:** _TBD_
**Last updated:** 2026-06-18

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
| Subtitle readability | `highlighted_subtitles.py`, `youtube_config.yaml` | Padding + green highlight + pop animation |
| TTS voice/speed | `youtube_config.yaml` → `tts.py` | `en-US-GuyNeural`, +10% speed |
| Tags/discoverability | `youtube.py`, `youtube_config.yaml` | Tiered tag system in place |
| Video title | `youtube.py` | Post title + subreddit hashtag |
| Background footage | `videoeditor.py` | Single hardcoded `assets/video/input2.mp4` |
| Sound effects | `sound_effects.py`, `configs/sfx_config.yaml` | Keyword/profanity-triggered SFX mixed into TTS; no intro sound |

---

## 3. Proposed Changes

Two changes are proposed for the first iteration, plus a set of follow-ups.

> **Note on content quality:** We deliberately do *not* add an upvote/length filter. Reddit's `top` ranking already surfaces community-validated, high-upvote posts, so an extra score filter would be redundant. Content selection is considered solved by the existing `top(time_filter=...)` fetch.

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

### 3.2 Intro Sound Effect (Proposal — Medium Impact)

**Problem:** The audio currently opens cold on the narration. A short, punchy intro sound under the title card adds an audio hook that signals *"a story is starting"* and pairs with the visual in 3.1.

**Proposed design:** Reuse the existing SFX engine rather than building anything new. The pipeline already mixes timestamped `SoundCue`s into the TTS track via `mix_sound_effects` (`sound_effects.py`). We add an always-on intro cue at `t=0` for part 1 (not a keyword trigger — it always fires), gated by config.

**Sound assets (YouTube Audio Library):** Two intro stingers are already in `assets/sfx/`:

| File | Character |
|------|-----------|
| `Reverberating Slam.mp3` | Heavy, dramatic impact — good for conflict/drama posts |
| `Crash Metal Sweetener Distant.mp3` | Metallic crash with distance — slightly lighter, still attention-grabbing |

**Randomization:** Pick one file at random per video (part 1 only). This keeps the opening from feeling identical across every upload while still landing a strong hook. Over time, retention data in YouTube Studio can show whether one sound outperforms the other.

- `random.choice(intro_files)` at render time in `videoeditor.py` (or a small helper in `sound_effects.py`).
- Same volume for both so the mix is consistent regardless of which clip plays.
- Ideally timed with the title-card window (3.1) so audio and visual hooks land together.

```yaml
# configs/sfx_config.yaml
intro:
  enabled: true
  files:
    - assets/sfx/Reverberating Slam.mp3
    - assets/sfx/Crash Metal Sweetener Distant.mp3
  volume: 0.6        # keep it under the narration so it doesn't startle
  parts: first_only  # first_only | all
```

**Touch points:**
- `configs/sfx_config.yaml` — `intro` section with `files` list (not a single path).
- `sound_effects.py` / `videoeditor.py` — random pick from `intro.files`, build `SoundCue(effect="intro", start_time=0.0, ...)`, pass into existing mix step.
- `assets/sfx/README.md` — document the two intro filenames.

**Open questions:**
- Volume level — loud enough to register, quiet enough not to clip the first narrated word? Start at `0.6` and tune after local preview.
- First part only, or every part? Default `first_only`.

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

1. Land this design doc; agree on defaults and open questions.
2. Implement 3.1 (title card) behind `title_card_enabled`.
3. Implement 3.2 (intro sound) behind `intro.enabled`, ideally timed with the title card.
4. Run with `DEBUG=True` locally; review output videos manually.
5. Enable in production config; monitor retention for 1–2 weeks vs. baseline.
6. Decide on follow-ups based on metrics.
