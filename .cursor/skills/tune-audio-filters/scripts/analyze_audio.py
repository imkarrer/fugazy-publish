#!/usr/bin/env python3
"""Analyze a video's onboard audio and recommend wind/whine filter settings.

Measures the audio spectrum and detects a fixed-frequency camera whine, then
prints a paste-ready ``audio:`` config block plus optional A/B test clips.

Requires: ffmpeg/ffprobe on PATH, numpy. Meant to run from the fugazy-publish
repo so it can reuse the real pipeline filter chain (fugazy_publish.teaser).

Usage:
    py .cursor/skills/tune-audio-filters/scripts/analyze_audio.py VIDEO
    py .../analyze_audio.py VIDEO --ab-dir output/ab --json
    py .../analyze_audio.py VIDEO --start 40 --duration 20
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import wave
from dataclasses import replace
from pathlib import Path

import numpy as np

# Reuse the repo's canonical config + filter-chain builder so A/B clips match
# exactly what the publishing pipeline would render.
REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))
try:
    from fugazy_publish.config import AudioConfig, NotchConfig, load_config
    from fugazy_publish.teaser import _build_audio_filters
    _HAVE_PIPELINE = True
except Exception:  # noqa: BLE001 — script must still run standalone
    _HAVE_PIPELINE = False


def _require(tool: str) -> str:
    exe = shutil.which(tool)
    if not exe:
        sys.exit(f"error: {tool} not found on PATH")
    return exe


def extract_wav(video: Path, dest: Path, start: float | None, duration: float | None) -> int:
    """Extract mono 48 kHz PCM. Returns the sample rate."""
    ffmpeg = _require("ffmpeg")
    cmd = [ffmpeg, "-y"]
    if start is not None:
        cmd += ["-ss", str(start)]
    cmd += ["-i", str(video)]
    if duration is not None:
        cmd += ["-t", str(duration)]
    cmd += ["-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le", str(dest)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit(f"ffmpeg audio extract failed:\n{proc.stderr[-2000:]}")
    return 48000


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as w:
        sr = w.getframerate()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    return data.astype(np.float64) / 32768.0, sr


def avg_spectrum(data: np.ndarray, sr: int, seg: int = 16384) -> tuple[np.ndarray, np.ndarray]:
    """Welch-style averaged magnitude spectrum. Returns (freqs, magnitude)."""
    win = np.hanning(seg)
    acc = np.zeros(seg // 2 + 1)
    count = 0
    for start in range(0, max(1, len(data) - seg), seg // 2):
        chunk = data[start:start + seg]
        if len(chunk) < seg:
            break
        acc += np.abs(np.fft.rfft(chunk * win))
        count += 1
    if count:
        acc /= count
    return np.fft.rfftfreq(seg, 1.0 / sr), acc


def band_level_db(freqs: np.ndarray, mag: np.ndarray, lo: float, hi: float) -> float:
    i0, i1 = np.searchsorted(freqs, lo), np.searchsorted(freqs, hi)
    if i1 <= i0:
        return -120.0
    return float(20 * np.log10(mag[i0:i1].mean() + 1e-12))


def detect_whine(data: np.ndarray, sr: int, freqs: np.ndarray) -> dict:
    """Scan ~4s windows for a recurring narrowband tonal peak (camera whine).

    A whine sits at a fixed frequency and recurs across many windows (even ones
    without screaming), which distinguishes it from moving voice harmonics.
    Search band 1.5-9 kHz where camera DSP whines typically live.
    """
    seg = 16384
    win = np.hanning(seg)
    kern = np.ones(41) / 41
    wlen = sr * 4
    lo_i = np.searchsorted(freqs, 1500)
    hi_i = np.searchsorted(freqs, 9000)

    peaks: list[tuple[float, float]] = []  # (freq, prominence_db)
    windows = 0
    for wstart in range(0, max(1, len(data) - wlen), wlen):
        acc = np.zeros(seg // 2 + 1)
        c = 0
        for s in range(wstart, wstart + wlen - seg, seg // 2):
            acc += np.abs(np.fft.rfft(data[s:s + seg] * win))
            c += 1
        if c == 0:
            continue
        windows += 1
        db = 20 * np.log10(acc / c + 1e-12)
        prom = db - np.convolve(db, kern, mode="same")
        j = lo_i + int(np.argmax(prom[lo_i:hi_i]))
        if prom[j] > 3.0:
            peaks.append((float(freqs[j]), float(prom[j])))

    if not peaks or windows == 0:
        return {"enabled": False, "windows": windows, "hits": 0}

    # Soft clustering: for each candidate peak, count how many other peaks fall
    # within +/-tol Hz. The whine is the center with the most recurring hits.
    # Tolerance-based grouping avoids splitting one tone across hard bin edges.
    tol = 250.0
    best_center, best_group = peaks[0][0], []
    for cf, _ in peaks:
        group = [(f, p) for f, p in peaks if abs(f - cf) <= tol]
        if len(group) > len(best_group):
            best_group, best_center = group, cf

    hits = len(best_group)
    center = float(np.average([f for f, _ in best_group],
                              weights=[p for _, p in best_group]))
    med_prom = float(np.median([p for _, p in best_group]))
    recurrence = hits / windows

    # Call it a whine only if it's a real recurring, prominent tone.
    enabled = recurrence >= 0.30 and hits >= 3 and med_prom >= 5.0
    return {
        "enabled": bool(enabled),
        "windows": windows,
        "hits": hits,
        "recurrence": round(recurrence, 2),
        "freq_hz": round(center, 1),
        "prominence_db": round(med_prom, 1),
    }


def recommend(data: np.ndarray, sr: int) -> dict:
    freqs, mag = avg_spectrum(data, sr)

    low = band_level_db(freqs, mag, 20, 150)          # wind rumble
    mid = band_level_db(freqs, mag, 300, 1200)        # exhaust/voice body
    wind_ratio = low - mid                             # how rumble-dominated

    # High-pass: cut more sub-bass when rumble dominates.
    if wind_ratio > 20:
        highpass = 260
    elif wind_ratio > 12:
        highpass = 200
    elif wind_ratio > 6:
        highpass = 150
    else:
        highpass = 100

    # Denoise strength scales with wind severity, clamped to a sane range.
    nr = int(round(min(22.0, max(8.0, 9.0 + wind_ratio * 0.6))))

    whine = detect_whine(data, sr, freqs)
    notch = {"enabled": False, "freq_hz": 3700.0, "width_hz": 700.0, "gain_db": -14.0}
    if whine.get("enabled"):
        f = whine["freq_hz"]
        width = int(min(1200, max(300, round(f * 0.18 / 50) * 50)))
        # Cut a bit deeper than the measured prominence for headroom.
        gain = int(round(-(whine["prominence_db"] + 3)))
        gain = max(-16, min(-8, gain))
        notch = {"enabled": True, "freq_hz": float(f), "width_hz": float(width),
                 "gain_db": float(gain)}

    return {
        "measurements": {
            "rumble_20_150hz_dbfs": round(low, 1),
            "body_300_1200hz_dbfs": round(mid, 1),
            "wind_ratio_db": round(wind_ratio, 1),
            "whine": whine,
        },
        "recommended": {
            "highpass_hz": highpass,
            "noise_reduction_db": nr,
            "notch": notch,
        },
    }


def to_audio_config(rec: dict, base: "AudioConfig") -> "AudioConfig":
    r = rec["recommended"]
    n = r["notch"]
    return replace(
        base,
        highpass_hz=r["highpass_hz"],
        noise_reduction_db=float(r["noise_reduction_db"]),
        notch=NotchConfig(
            enabled=n["enabled"], freq_hz=n["freq_hz"],
            width_hz=n["width_hz"], gain_db=n["gain_db"],
        ),
    )


def yaml_block(rec: dict, base: "AudioConfig | None") -> str:
    r = rec["recommended"]
    n = r["notch"]
    hp, nr = r["highpass_hz"], r["noise_reduction_db"]
    nf = base.noise_floor_db if base else -25
    tn = "true" if (base.track_noise if base else True) else "false"
    bq = "true" if (base.boost_quiet if base else True) else "false"
    ct = base.compress_threshold_db if base else -24
    cr = base.compress_ratio if base else 3
    norm = "true" if (base.normalize if base else True) else "false"
    tl = base.target_loudness if base else -16
    return f"""audio:
  enabled: true
  clean_youtube: true
  highpass_hz: {hp}
  lowpass_hz: 0
  noise_reduction_db: {nr}
  noise_floor_db: {nf}
  track_noise: {tn}
  boost_quiet: {bq}
  compress_threshold_db: {ct}
  compress_ratio: {cr}
  normalize: {norm}
  target_loudness: {tl}
  notch:
    enabled: {str(n['enabled']).lower()}
    freq_hz: {int(n['freq_hz'])}
    width_hz: {int(n['width_hz'])}
    gain_db: {int(n['gain_db'])}"""


def loudest_moment(data: np.ndarray, sr: int, win_s: float = 8.0) -> float:
    """Find the 8s window richest in high-frequency energy (i.e. screaming),
    not raw loudness — otherwise low-frequency wind rumble always wins."""
    wlen = int(sr * win_s)
    if len(data) <= wlen:
        return 0.0
    hf = np.diff(data)  # first difference emphasizes highs (crude high-pass)
    best_t, best_e = 0.0, -1.0
    for start in range(0, len(hf) - wlen, wlen // 2):
        e = float(np.mean(hf[start:start + wlen] ** 2))
        if e > best_e:
            best_e, best_t = e, start / sr
    return round(best_t, 1)


def make_ab_clips(video: Path, rec: dict, base: "AudioConfig", at: float, out_dir: Path) -> list[str]:
    ffmpeg = _require("ffmpeg")
    out_dir.mkdir(parents=True, exist_ok=True)
    chain = _build_audio_filters(to_audio_config(rec, base))
    stem = video.stem[:40]
    clips = []
    jobs = [(f"{stem}_A_original.mp4", None), (f"{stem}_B_recommended.mp4", chain)]
    for name, af in jobs:
        dest = out_dir / name
        cmd = [ffmpeg, "-y", "-ss", str(at), "-i", str(video), "-t", "8"]
        if af:
            cmd += ["-af", af]
        cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-c:a", "aac", "-b:a", "192k", str(dest)]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            sys.exit(f"ffmpeg A/B render failed:\n{proc.stderr[-1500:]}")
        clips.append(str(dest))
    return clips


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("video", type=Path)
    ap.add_argument("--start", type=float, default=None, help="analysis start (s)")
    ap.add_argument("--duration", type=float, default=None, help="analysis length (s)")
    ap.add_argument("--config", type=Path, default=None,
                    help="base config.yaml to inherit untuned params (default: repo config.yaml)")
    ap.add_argument("--ab-dir", type=Path, default=None,
                    help="also render A/B test clips into this dir")
    ap.add_argument("--json", action="store_true", help="print JSON only")
    args = ap.parse_args(argv)

    if not args.video.is_file():
        sys.exit(f"error: video not found: {args.video}")

    base = None
    if _HAVE_PIPELINE:
        try:
            cfg_path = args.config or (REPO_ROOT / "config.yaml")
            base = load_config(cfg_path).audio if cfg_path.is_file() else AudioConfig()
        except Exception:  # noqa: BLE001
            base = AudioConfig()

    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "audio.wav"
        sr = extract_wav(args.video, wav, args.start, args.duration)
        data, sr = read_wav(wav)
        rec = recommend(data, sr)
        at = loudest_moment(data, sr) + (args.start or 0.0)

    ab = []
    if args.ab_dir is not None:
        if not _HAVE_PIPELINE or base is None:
            print("warning: pipeline import unavailable; skipping A/B clips", file=sys.stderr)
        else:
            ab = make_ab_clips(args.video, rec, base, at, args.ab_dir)

    if args.json:
        print(json.dumps({**rec, "ab_clips": ab, "loudest_at_s": at}, indent=2))
        return 0

    m = rec["measurements"]
    w = m["whine"]
    print(f"\n=== Audio analysis: {args.video.name} ===")
    print(f"  rumble (20-150 Hz):  {m['rumble_20_150hz_dbfs']:6.1f} dBFS")
    print(f"  body   (300-1200 Hz):{m['body_300_1200hz_dbfs']:6.1f} dBFS")
    print(f"  wind ratio:          {m['wind_ratio_db']:6.1f} dB (higher = windier)")
    if w.get("enabled"):
        print(f"  whine detected:      {w['freq_hz']:.0f} Hz "
              f"(+{w['prominence_db']} dB, recurs {int(w['recurrence']*100)}% of clip)")
    else:
        print(f"  whine detected:      none (no steady tone; notch left off)")
    print("\n--- Recommended audio config (paste into config.yaml) ---\n")
    print(yaml_block(rec, base))
    if ab:
        print("\n--- A/B clips (listen, then apply if B wins) ---")
        for c in ab:
            print(f"  {c}")
    print("\nVerify by ear. Adjust noise_reduction_db down if it sounds watery,")
    print("or notch gain_db toward 0 if the scream/exhaust gets dulled.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
