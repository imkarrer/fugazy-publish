"""End-to-end publish orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fugazy_publish.config import AppConfig, load_config, output_dir
from fugazy_publish.social import fan_out
from fugazy_publish.teaser import check_ffmpeg, clean_audio_track, create_teaser
from fugazy_publish import youtube_client
from fugazy_publish.youtube_download import (
    YouTubeVideoInfo,
    download_video,
    parse_video_id,
    watch_url,
)


def _youtube_watch_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def validate_video_file(path: Path) -> Path:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Video not found: {p}")
    if p.suffix.lower() not in {".mp4", ".mov", ".mkv", ".webm", ".avi"}:
        raise ValueError(f"Unsupported video extension: {p.suffix}")
    return p.resolve()


def publish(
    video_path: str | Path,
    title: str,
    *,
    config: AppConfig | None = None,
    config_path: str | Path | None = None,
    dry_run: bool = False,
    skip_youtube: bool = False,
    youtube_url: str | None = None,
    review: bool = False,
) -> dict[str, Any]:
    """Validate, upload YouTube, create teaser, fan out to social.

    When ``review`` is set, the pipeline still cleans the audio and builds the
    teaser but pauses before uploading anywhere, leaving the cleaned full-run
    video and teaser on disk for manual review. In the normal (non-review)
    flow the cleaned ``_clean.mp4`` is deleted after a successful upload.
    """
    if review and dry_run:
        raise ValueError("review and dry_run are mutually exclusive")

    cfg = config or load_config(config_path)
    if dry_run:
        source = Path(video_path).resolve()
    else:
        source = validate_video_file(video_path)

    summary: dict[str, Any] = {
        "source": str(source),
        "title": title,
        "dry_run": dry_run,
        "skip_youtube": skip_youtube,
        "review": review,
    }

    if not dry_run:
        check_ffmpeg()

    yt_result: dict[str, Any] | None = None
    watch_url = youtube_url

    if skip_youtube:
        if not watch_url:
            raise ValueError("--youtube-url is required when skipping YouTube upload")
        summary["youtube"] = {"skipped": True, "url": watch_url}
    else:
        if dry_run:
            watch_url = watch_url or "https://www.youtube.com/watch?v=DRY_RUN"
            summary["youtube"] = {"dry_run": True, "url": watch_url}
        else:
            upload_source = source
            cleaned_path: Path | None = None
            if cfg.audio.enabled and cfg.audio.clean_youtube:
                cleaned_path = clean_audio_track(
                    source, output_dir(cfg) / f"{source.stem}_clean.mp4", cfg
                )
                upload_source = cleaned_path
                summary["youtube_audio_cleaned"] = str(cleaned_path)

            if review:
                summary["youtube"] = {
                    "pending_review": True,
                    "url": youtube_url,
                    "upload_source": str(upload_source),
                }
            else:
                yt_result = youtube_client.upload_video(upload_source, title, cfg)
                video_id = yt_result.get("id")
                if not video_id:
                    raise RuntimeError(f"YouTube response missing video id: {yt_result}")
                watch_url = _youtube_watch_url(video_id)
                summary["youtube"] = {"id": video_id, "url": watch_url, "response": yt_result}
                # Upload succeeded — drop the temporary cleaned copy.
                if cleaned_path and cleaned_path != source and cleaned_path.exists():
                    cleaned_path.unlink()
                    summary["youtube_audio_cleaned_removed"] = True

    out = output_dir(cfg)
    teaser_name = f"{source.stem}_teaser.mp4"
    teaser_path = out / teaser_name

    if dry_run:
        summary["teaser"] = {"dry_run": True, "path": str(teaser_path)}
    else:
        teaser_path = create_teaser(source, teaser_path, cfg, title=title)
        summary["teaser"] = {"path": str(teaser_path)}

    if review:
        summary["social"] = {"pending_review": True}
        summary["status"] = "paused_for_review"
        summary["review_files"] = {
            "cleaned_full_video": summary.get("youtube_audio_cleaned"),
            "teaser": str(teaser_path),
        }
        summary["youtube_url"] = watch_url
        return summary

    assert watch_url is not None

    if dry_run:
        summary["social"] = fan_out(
            teaser_path if teaser_path.is_file() else source,
            cfg,
            watch_url,
            dry_run=True,
        )
    else:
        if not teaser_path.is_file():
            raise RuntimeError("Teaser file missing after creation")
        summary["social"] = fan_out(teaser_path, cfg, watch_url, dry_run=False)

    summary["youtube_url"] = watch_url
    return summary


def promote_existing(
    youtube_url_or_id: str,
    *,
    title: str | None = None,
    config: AppConfig | None = None,
    config_path: str | Path | None = None,
    dry_run: bool = False,
    force_download: bool = False,
    local_file: str | Path | None = None,
    review: bool = False,
) -> dict[str, Any]:
    """Download an existing YouTube video (or use local file), create teaser, fan out."""
    cfg = config or load_config(config_path)
    video_id = youtube_url_or_id.strip()
    if local_file:
        source = validate_video_file(local_file)
        try:
            vid = parse_video_id(youtube_url_or_id)
            yt_url = watch_url(vid)
        except ValueError:
            vid = source.stem
            yt_url = youtube_url_or_id
        info = YouTubeVideoInfo(
            video_id=vid,
            title=title or source.stem,
            watch_url=yt_url,
            local_path=source,
        )
    elif dry_run:
        vid = parse_video_id(youtube_url_or_id)
        info = YouTubeVideoInfo(
            video_id=vid,
            title=title or vid,
            watch_url=watch_url(vid),
            local_path=output_dir(cfg) / "downloads" / f"{vid}.mp4",
        )
    else:
        info = download_video(youtube_url_or_id, cfg, force=force_download)

    campaign_title = title or info.title
    return publish(
        info.local_path,
        campaign_title,
        config=cfg,
        dry_run=dry_run,
        skip_youtube=True,
        youtube_url=info.watch_url,
        review=review,
    )
