# Sound Effects

Custom `.wav` or `.mp3` SFX files live here and are tracked in the repo so every
contributor gets a working setup out of the box. For royalty-free options, the
[YouTube Audio Library](https://studio.youtube.com) (Sound Effects tab) is a good
source — files from there are pre-cleared for YouTube uploads.

## Intro stinger

Plays at the very start of every video to hook the viewer before narration begins.
From the YouTube Audio Library, pre-cleared for monetization.

| Filename | Character |
|---|---|
| `Emergency Radio Alert.mp3` | Urgent alert / EAS tone |

Configure volume and enable/disable in `configs/sfx_config.yaml` under `intro`.

When the in-video thumbnail intro is enabled (`thumbnail.enabled` in `youtube_config.yaml`), the intro stinger is delayed until after the title narration finishes so it does not mask the spoken hook.

## Thumbnail intro pop

Plays at `t=0` when the Reddit post card fades in on part 1. Pairs with the visual card overlay.

| Filename | Character |
|---|---|
| `Rake Swing Whoosh Close.mp3` | Short whoosh / pop |

Mapped in `configs/sfx_config.yaml` as `sfx.thumbnail_pop`. Volume is capped in `youtube_config.yaml` under `thumbnail.sfx_volume`.

## Contextual SFX (keyword-triggered)

| Filename | Effect | Suggested sound |
|---|---|---|
| `Fart Toot.mp3` | Profanity | Fart toot (replaces TV bleep) |
| `gasp.wav` | Shocking / OMG | Dramatic gasp or sting |
| `rimshot.wav` | Funny / Comedic | Rimshot, vine boom, or bruh |
| `sad_sting.wav` | Sad / Emotional | Short sad violin or piano sting |
| `riser.wav` | Tension / Suspense | Low drone or suspense riser |

## Notes

- File names must match the paths configured in `configs/sfx_config.yaml`
- Short clips (0.5–3s) work best so they don't overlap each other
