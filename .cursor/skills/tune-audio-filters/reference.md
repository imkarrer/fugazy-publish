# Tune Audio Filters — Reference

How `scripts/analyze_audio.py` turns measurements into recommended settings.

## Measurements

The analyzer extracts a mono 48 kHz track and computes a Welch-averaged
magnitude spectrum, plus a windowed (4s) tonal scan.

- **rumble (20–150 Hz)** — average level where onboard wind roar concentrates.
- **body (300–1200 Hz)** — exhaust/voice fundamentals reference level.
- **wind_ratio = rumble − body** (dB) — how rumble-dominated the mix is. Higher
  means windier.

## High-pass (`highpass_hz`)

Cuts sub-bass wind rumble sitting below the exhaust/voice. Chosen from wind_ratio:

| wind_ratio (dB) | highpass_hz |
|-----------------|-------------|
| > 20            | 260         |
| > 12            | 200         |
| > 6             | 150         |
| otherwise       | 100         |

Going higher than ~300 starts hollowing out lower voices and the exhaust note.

## Denoise (`noise_reduction_db`)

Strength of the `afftdn` FFT denoiser against broadband wind hiss:

```
noise_reduction_db = clamp(round(9 + wind_ratio * 0.6), 8, 22)
```

Above ~22 the denoiser introduces watery "musical noise" artifacts that smear
consonants, so it is capped.

## Whine notch (`notch`)

A camera whine (e.g. the GoPro's own wind DSP) is a fixed-frequency tone. The
scan looks for the strongest narrowband peak (prominence over a smoothed
baseline) in **1.5–9 kHz** in each 4s window, then groups peaks within ±250 Hz.

A notch is recommended only when the dominant peak is a genuine recurring tone:

- recurs in **≥ 30%** of windows, **and**
- appears in **≥ 3** windows, **and**
- median prominence **≥ 5 dB**.

This recurrence test distinguishes a steady whine (present even in windows
without screaming) from moving voice/exhaust harmonics.

When found:

- `freq_hz` = prominence-weighted center of the peak cluster.
- `width_hz` = `clamp(round(freq * 0.18 / 50) * 50, 300, 1200)`.
- `gain_db` = `clamp(round(-(prominence + 3)), -16, -8)` (cut a bit deeper than
  the measured prominence for headroom).

If no qualifying tone is found, the notch is left `enabled: false`.

## A/B clips

With `--ab-dir`, the analyzer finds the 8s window richest in **high-frequency**
energy (screaming, not raw loudness — otherwise wind rumble always wins) and
renders two clips there:

- `*_A_original.mp4` — untouched.
- `*_B_recommended.mp4` — the recommended chain, built with the pipeline's own
  `fugazy_publish.teaser._build_audio_filters`, so it matches real output.

## Untuned parameters

`noise_floor_db`, `track_noise`, the compressor, and `loudnorm` are inherited
from the base `config.yaml` (or defaults) and passed through unchanged. The
analyzer only tunes `highpass_hz`, `noise_reduction_db`, and the `notch`.
