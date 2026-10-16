"""Create short teaser clips with ffmpeg drawtext overlay."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from fugazy_publish.config import AppConfig, AudioConfig, OverlayConfig

# Fallback overlay fonts per platform, tried in order when neither the config
# nor the Flox environment (FUGAZY_FONT_FILE) supplies one that exists.
PLATFORM_FONTS: dict[str, list[str]] = {
    "win32": ["C:/Windows/Fonts/arial.ttf"],
    "darwin": [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
    ],
    "linux": [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
    ],
}


class FFmpegNotFoundError(RuntimeError):
    pass


class FontNotFoundError(RuntimeError):
    pass


def check_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        if sys.platform == "win32":
            hint = "Install with: winget install FFmpeg"
        else:
            hint = "Run inside the Flox environment: flox activate"
        raise FFmpegNotFoundError(f"ffmpeg not found on PATH. {hint}")
    return exe


def resolve_font_file(configured: str, platform: str | None = None) -> str:
    """Pick the overlay font: config, then FUGAZY_FONT_FILE, then OS defaults.

    A configured path that does not exist on this machine (e.g. a Windows font
    path in a config.yaml copied to a Mac) falls through rather than failing.
    """
    platform = platform or sys.platform
    candidates = [configured, os.environ.get("FUGAZY_FONT_FILE", "")]
    candidates += PLATFORM_FONTS.get(platform, [])
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise FontNotFoundError(
        "No overlay font found. Set teaser.overlay.font_file in config.yaml "
        "or run inside the Flox environment (flox activate)."
    )


def _escape_drawtext(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "\\%")
    )


def _ffmpeg_path(path: Path | str) -> str:
    return str(path).replace("\\", "/").replace(":", "\\:")


def _probe_video_size(video_path: Path) -> tuple[int, int]:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return 1920, 1080
    proc = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0",
            str(video_path),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return 1920, 1080
    parts = proc.stdout.strip().split(",")
    if len(parts) >= 2:
        return int(parts[0]), int(parts[1])
    return 1920, 1080


def _max_chars_per_line(width: int, font_size: int) -> int:
    char_width = font_size * 0.55
    return max(8, int((width * 0.82) / char_width))


def _wrap_text(text: str, max_chars: int) -> list[str]:
    normalized = " ".join(text.split())
    if not normalized:
        return []
    if len(normalized) <= max_chars:
        return [normalized]

    words = normalized.split()
    lines: list[str] = []
    current: list[str] = []
    length = 0
    for word in words:
        add = len(word) + (1 if current else 0)
        if current and length + add > max_chars:
            lines.append(" ".join(current))
            current = [word]
            length = len(word)
        else:
            current.append(word)
            length += add
    if current:
        lines.append(" ".join(current))
    return lines


def _compose_overlay_lines(
    title: str | None,
    link: str,
    overlay_text: str,
    max_chars: int,
) -> list[str]:
    lines: list[str] = []
    if title and title.strip():
        lines.extend(_wrap_text(title.strip(), max_chars))
    if link.strip():
        line = link.strip()
        if len(line) <= max_chars:
            lines.append(line)
        else:
            lines.extend(_wrap_text(line, max_chars))
    if overlay_text.strip():
        lines.extend(_wrap_text(overlay_text.strip(), max_chars))
    return lines


def _block_top_margin(overlay: OverlayConfig, height: int, block_height: int) -> int:
    pos = overlay.position.lower()
    margin = max(24, int(height * 0.04))
    if pos == "custom":
        return margin
    if pos in {"top", "top_center"}:
        return margin
    if pos == "center":
        return max(margin, int((height - block_height) / 2))
    return max(margin, height - block_height - margin)


def _fit_overlay_layout(
    width: int,
    height: int,
    base_font_size: int,
    title: str | None,
    link: str,
    overlay_text: str,
) -> tuple[list[str], int, int]:
    """Return wrapped lines, font size, and line spacing that fit the frame."""
    font_size = base_font_size
    lines: list[str] = []
    line_spacing = 8

    for _ in range(14):
        max_chars = _max_chars_per_line(width, font_size)
        lines = _compose_overlay_lines(title, link, overlay_text, max_chars)
        line_spacing = max(6, int(font_size * 0.28))
        line_height = font_size + line_spacing
        block_height = len(lines) * line_height - line_spacing if lines else 0
        longest = max((len(line) for line in lines), default=0)
        est_width = longest * font_size * 0.55

        if (
            lines
            and block_height <= height * 0.42
            and est_width <= width * 0.88
            and len(lines) <= 7
        ):
            return lines, font_size, line_spacing

        font_size = max(20, int(font_size * 0.88))

    return lines, font_size, line_spacing


def _build_drawtext_filters(
    overlay: OverlayConfig,
    *,
    lines: list[str],
    font_size: int,
    line_spacing: int,
    frame_height: int,
) -> str:
    font = _ffmpeg_path(resolve_font_file(overlay.font_file))
    # The teaser is trimmed with `-ss` before `-i`, which resets the output
    # timeline to 0. So the overlay window is relative to the teaser start, not
    # the source's start_seconds (otherwise a non-zero start_seconds pushes the
    # overlay past the end of the clip and it never shows).
    show_start = 0.0
    show_end = show_start + overlay.show_seconds
    line_height = font_size + line_spacing
    block_height = len(lines) * line_height - line_spacing
    top = _block_top_margin(overlay, frame_height, block_height)

    filters: list[str] = []
    for index, line in enumerate(lines):
        y_pos = top + index * line_height
        text = _escape_drawtext(line)
        filters.append(
            f"drawtext=fontfile='{font}':text='{text}'"
            f":fontsize={font_size}:fontcolor={overlay.font_color}"
            f":borderw=2:bordercolor=black"
            f":x=(w-text_w)/2:y={y_pos}"
            f":enable='between(t,{show_start},{show_end})'"
        )
    return ",".join(filters)


def _build_audio_filters(audio: AudioConfig) -> str:
    """Assemble an ffmpeg -af chain that suppresses wind and lifts other sounds.

    Order matters: cut the low-frequency wind rumble first, run the adaptive
    FFT denoiser on the broadband roar, then compress/normalize so exhaust and
    passengers come back up to an audible level.
    """
    if not audio.enabled:
        return ""

    parts: list[str] = []
    if audio.highpass_hz > 0:
        parts.append(f"highpass=f={audio.highpass_hz}")
    if audio.lowpass_hz > 0:
        parts.append(f"lowpass=f={audio.lowpass_hz}")

    notch = audio.notch
    if notch.enabled and notch.gain_db != 0:
        # Surgical parametric cut for a fixed-frequency whine (e.g. GoPro DSP).
        parts.append(
            f"equalizer=f={notch.freq_hz}:width_type=h"
            f":w={notch.width_hz}:g={notch.gain_db}"
        )

    afftdn = f"afftdn=nr={audio.noise_reduction_db}:nf={audio.noise_floor_db}"
    if audio.track_noise:
        afftdn += ":tn=1"
    parts.append(afftdn)

    if audio.boost_quiet:
        parts.append(
            f"acompressor=threshold={audio.compress_threshold_db}dB"
            f":ratio={audio.compress_ratio}:attack=20:release=250"
        )
    if audio.normalize:
        parts.append(f"loudnorm=I={audio.target_loudness}:TP=-1.5:LRA=11")

    return ",".join(parts)


def clean_audio_track(
    source_video: Path,
    output_path: Path,
    config: AppConfig,
) -> Path:
    """Re-encode only the audio with the wind-noise filter, copying video as-is.

    Used to clean the full-length YouTube upload without touching (or slowly
    re-encoding) the video stream. Returns the source path unchanged when audio
    cleanup is disabled so callers can upload the original file.
    """
    af = _build_audio_filters(config.audio)
    if not af:
        return Path(source_video)

    ffmpeg = check_ffmpeg()
    source_video = Path(source_video)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(source_video),
        "-af",
        af,
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(output_path),
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg audio cleanup failed (exit {proc.returncode}):\n{proc.stderr[-4000:]}"
        )
    if not output_path.is_file():
        raise RuntimeError("ffmpeg did not produce cleaned audio file")
    return output_path


def create_teaser(
    source_video: Path,
    output_path: Path,
    config: AppConfig,
    *,
    title: str | None = None,
) -> Path:
    ffmpeg = check_ffmpeg()
    source_video = Path(source_video)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    teaser = config.teaser
    start = teaser.start_seconds
    duration = teaser.duration_seconds
    overlay = teaser.overlay

    cmd = [
        ffmpeg,
        "-y",
        "-ss",
        str(start),
        "-i",
        str(source_video),
        "-t",
        str(duration),
    ]

    if overlay.enabled:
        width, height = _probe_video_size(source_video)
        lines, font_size, line_spacing = _fit_overlay_layout(
            width,
            height,
            overlay.font_size,
            title,
            overlay.link,
            overlay.text,
        )
        if lines:
            vf = _build_drawtext_filters(
                overlay,
                lines=lines,
                font_size=font_size,
                line_spacing=line_spacing,
                frame_height=height,
            )
            cmd.extend(["-vf", vf])

    af = _build_audio_filters(config.audio)
    if af:
        cmd.extend(["-af", af])

    cmd.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed (exit {proc.returncode}):\n{proc.stderr[-4000:]}"
        )
    if not output_path.is_file():
        raise RuntimeError("ffmpeg did not produce output file")
    return output_path
