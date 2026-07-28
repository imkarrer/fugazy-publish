---
name: tune-audio-filters
description: >-
  Analyze an onboard/autocross video's audio and recommend optimal wind-noise
  and camera-whine filter settings for the fugazy-publish pipeline. Measures the
  spectrum, auto-detects a fixed-frequency camera whine, and outputs a
  paste-ready audio: config block plus A/B test clips. Use when picking or tuning
  audio filter settings for a specific camera, car, or video, when a clip has
  too much wind noise or a high-pitched whine, or when the user mentions tuning
  highpass_hz, noise_reduction_db, or the notch.
---

# Tune Audio Filters

Pick optimal wind/whine cleanup settings for a video by measuring its audio
instead of guessing. Produces a ready-to-use `audio:` block for `config.yaml`
and short A/B clips so the choice can be confirmed by ear.

## When to use

- Dialing in settings for a new camera, car, or mounting position.
- A clip has heavy wind roar burying exhaust/voices, or a high-pitched whine.
- The user wants to tune `highpass_hz`, `noise_reduction_db`, or the whine `notch`.

## Requirements

`ffmpeg`/`ffprobe` on PATH and `numpy` (`py -m pip install numpy`). Run from the
repo root so the analyzer can reuse the pipeline's real filter chain.

## Workflow

```
- [ ] 1. Analyze the video (+ render A/B clips)
- [ ] 2. Review the recommendation and listen to A/B
- [ ] 3. Apply settings (camera default vs one-off video)
- [ ] 4. Fine-tune by ear if needed
```

### Step 1 — Analyze

Run the analyzer on the target video, writing A/B clips to `output/ab/`:

```
py .cursor/skills/tune-audio-filters/scripts/analyze_audio.py "PATH/TO/video.mp4" --ab-dir output/ab
```

It prints measured wind ratio, whether a whine was detected (and its frequency),
and a paste-ready `audio:` block. Add `--json` for machine-readable output, or
`--start 40 --duration 20` to analyze a specific window.

### Step 2 — Review and verify by ear

- Present the recommended `audio:` block and the measurements to the user.
- Point them to the two clips in `output/ab/`: `*_A_original.mp4` (untouched) vs
  `*_B_recommended.mp4` (recommended chain). Ask them to confirm B sounds better
  (wind/whine down, exhaust + screaming clearer) before applying.

### Step 3 — Apply

Ask whether this is a **camera default** or a **one-off video**:

- **Camera default** (same GoPro/car for all runs): edit the `audio:` section of
  `config.yaml` with the recommended values.
- **One-off video**: copy `config.yaml` to e.g. `config.<name>.yaml`, put the
  recommended `audio:` block there, and run the pipeline with `--config`:

```
py publish.py "PATH/TO/video.mp4" --config config.<name>.yaml --review
```

Use `--review` first so the cleaned file + teaser are kept for a final check
before uploading.

### Step 4 — Fine-tune by ear

The analyzer gives a solid starting point; adjust only if a symptom appears:

| Symptom | Adjustment |
|---------|-----------|
| Wind rumble still present | raise `highpass_hz` (e.g. +40) |
| Broadband wind hiss remains | raise `noise_reduction_db` (max ~22) |
| Sounds watery / "underwater" | lower `noise_reduction_db` |
| Whine still audible | deepen notch `gain_db` (more negative) or widen `width_hz` |
| Scream/exhaust dulled | raise notch `gain_db` toward 0, or narrow `width_hz` |
| No whine but analyzer added a notch | set notch `enabled: false` |

Re-run Step 1 after big changes to re-measure.

## How the recommendation is derived

See [reference.md](reference.md) for the exact measurements, thresholds, and
whine-detection logic.
