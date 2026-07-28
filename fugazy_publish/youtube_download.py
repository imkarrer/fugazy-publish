"""Download existing YouTube videos for teaser generation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yt_dlp

from fugazy_publish.config import AppConfig, output_dir

_VIDEO_ID_PATTERNS = (
    re.compile(r"(?:youtu\.be/|youtube\.com/watch\?v=|youtube\.com/shorts/)([A-Za-z0-9_-]{11})"),
    re.compile(r"^([A-Za-z0-9_-]{11})$"),
)


@dataclass
class YouTubeVideoInfo:
    video_id: str
    title: str
    watch_url: str
    local_path: Path


def parse_video_id(url_or_id: str) -> str:
    value = url_or_id.strip()
    for pattern in _VIDEO_ID_PATTERNS:
        match = pattern.search(value)
        if match:
            return match.group(1)
    raise ValueError(f"Could not parse YouTube video id from: {url_or_id}")


def watch_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def _downloads_dir(config: AppConfig) -> Path:
    d = output_dir(config) / "downloads"
    d.mkdir(parents=True, exist_ok=True)
    return d


def download_video(
    url_or_id: str,
    config: AppConfig,
    *,
    force: bool = False,
) -> YouTubeVideoInfo:
    """Download (or reuse cached) MP4 for a YouTube video."""
    video_id = parse_video_id(url_or_id)
    dest = _downloads_dir(config) / f"{video_id}.mp4"

    if dest.is_file() and not force:
        title = _fetch_title_only(watch_url(video_id))
        return YouTubeVideoInfo(
            video_id=video_id,
            title=title,
            watch_url=watch_url(video_id),
            local_path=dest,
        )

    ydl_opts: dict[str, Any] = {
        "outtmpl": str(dest.with_suffix(".%(ext)s")),
        "format": (
            "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/"
            "best[height<=1080][ext=mp4]/best"
        ),
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "overwrites": force,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(watch_url(video_id), download=True)
        title = str(info.get("title") or video_id)

    if not dest.is_file():
        # yt-dlp may use a slightly different extension before merge
        candidates = list(_downloads_dir(config).glob(f"{video_id}.*"))
        mp4s = [p for p in candidates if p.suffix.lower() == ".mp4"]
        if mp4s:
            dest = mp4s[0]
        elif candidates:
            dest = candidates[0]
        else:
            raise RuntimeError(f"Download finished but file not found for {video_id}")

    return YouTubeVideoInfo(
        video_id=video_id,
        title=title,
        watch_url=watch_url(video_id),
        local_path=dest.resolve(),
    )


def _fetch_title_only(url: str) -> str:
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True}) as ydl:
        info = ydl.extract_info(url, download=False)
        return str(info.get("title") or parse_video_id(url))
