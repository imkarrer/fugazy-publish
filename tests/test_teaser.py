"""Cross-platform font resolution, ffmpeg discovery, and teaser rendering."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from fugazy_publish import teaser
from fugazy_publish.config import OverlayConfig, load_config

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def font(tmp_path: Path) -> Path:
    path = tmp_path / "font.ttf"
    path.write_bytes(b"not really a font")
    return path


@pytest.fixture(autouse=True)
def no_fallback_fonts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FUGAZY_FONT_FILE", raising=False)
    monkeypatch.setattr(teaser, "PLATFORM_FONTS", {})


def test_configured_font_wins(font: Path, tmp_path: Path, monkeypatch) -> None:
    other = tmp_path / "other.ttf"
    other.write_bytes(b"")
    monkeypatch.setenv("FUGAZY_FONT_FILE", str(other))
    assert teaser.resolve_font_file(str(font)) == str(font)


def test_missing_configured_font_falls_back_to_flox_font(font: Path, monkeypatch) -> None:
    monkeypatch.setenv("FUGAZY_FONT_FILE", str(font))
    assert teaser.resolve_font_file("C:/Windows/Fonts/arial.ttf") == str(font)


def test_falls_back_to_platform_font(font: Path, monkeypatch) -> None:
    monkeypatch.setattr(teaser, "PLATFORM_FONTS", {"darwin": ["/nope.ttf", str(font)]})
    assert teaser.resolve_font_file("", platform="darwin") == str(font)


def test_no_font_anywhere_raises() -> None:
    with pytest.raises(teaser.FontNotFoundError):
        teaser.resolve_font_file("/does/not/exist.ttf")


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("C:\\Windows\\Fonts\\arial.ttf", "C\\:/Windows/Fonts/arial.ttf"),
        ("/nix/store/abc-dejavu/DejaVuSans.ttf", "/nix/store/abc-dejavu/DejaVuSans.ttf"),
    ],
)
def test_ffmpeg_path_escaping(path: str, expected: str) -> None:
    assert teaser._ffmpeg_path(path) == expected


@pytest.mark.parametrize(
    ("platform", "hint"),
    [("win32", "winget install FFmpeg"), ("darwin", "flox activate"), ("linux", "flox activate")],
)
def test_missing_ffmpeg_hint_matches_platform(monkeypatch, platform: str, hint: str) -> None:
    monkeypatch.setattr(teaser.shutil, "which", lambda _: None)
    monkeypatch.setattr(teaser.sys, "platform", platform)
    with pytest.raises(teaser.FFmpegNotFoundError, match=hint):
        teaser.check_ffmpeg()


def test_drawtext_uses_resolved_font(font: Path, monkeypatch) -> None:
    monkeypatch.setenv("FUGAZY_FONT_FILE", str(font))
    vf = teaser._build_drawtext_filters(
        OverlayConfig(font_file=""),
        lines=["Full run on YouTube"],
        font_size=28,
        line_spacing=8,
        frame_height=1080,
    )
    assert f"fontfile='{font}'" in vf


requires_ffmpeg = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
    reason="ffmpeg not on PATH; run inside flox activate",
)


@requires_ffmpeg
def test_ffmpeg_has_drawtext() -> None:
    out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True)
    assert " drawtext " in out.stdout


@requires_ffmpeg
def test_create_teaser_renders_with_example_config(tmp_path: Path, monkeypatch) -> None:
    """End to end: example config, auto-detected font, overlay + audio cleanup."""
    monkeypatch.undo()  # use the real environment's font and platform fallbacks
    source = tmp_path / "run.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30:duration=4",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
            "-c:v", "libx264", "-c:a", "aac", "-shortest", str(source),
        ],
        check=True,
    )
    config = load_config(ROOT / "config.example.yaml")
    config = replace(config, teaser=replace(config.teaser, duration_seconds=2.0))

    out = teaser.create_teaser(source, tmp_path / "teaser.mp4", config, title="Run 3")

    duration = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)],
        capture_output=True, text=True, check=True,
    ).stdout
    assert float(duration) == pytest.approx(2.0, abs=0.2)
