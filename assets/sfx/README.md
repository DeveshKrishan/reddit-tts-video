# Sound Effects

Custom `.wav` or `.mp3` SFX files live here and are tracked in the repo so every
contributor gets a working setup out of the box. For royalty-free options, the
[YouTube Audio Library](https://studio.youtube.com) (Sound Effects tab) is a good
source — files from there are pre-cleared for YouTube uploads.

## Intro stingers (randomized per video)

One of these is picked at random for the first second of every video to hook
the viewer before narration begins. Both are from the YouTube Audio Library and
are pre-cleared for monetization.

| Filename | Character |
|---|---|
| `Reverberating Slam.mp3` | Heavy dramatic impact |
| `Crash Metal Sweetener Distant.mp3` | Metallic crash, slightly lighter |

Configure volume and enable/disable in `configs/sfx_config.yaml` under `intro`.

## Contextual SFX (keyword-triggered)

| Filename | Effect | Suggested sound |
|---|---|---|
| `bleep.wav` | Profanity bleep | TV-style bleep tone |
| `gasp.wav` | Shocking / OMG | Dramatic gasp or sting |
| `rimshot.wav` | Funny / Comedic | Rimshot, vine boom, or bruh |
| `sad_sting.wav` | Sad / Emotional | Short sad violin or piano sting |
| `riser.wav` | Tension / Suspense | Low drone or suspense riser |

## Notes

- File names must match the paths configured in `configs/sfx_config.yaml`
- Short clips (0.5–3s) work best so they don't overlap each other
