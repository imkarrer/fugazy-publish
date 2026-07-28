"""Fan-out teaser to TikTok and Instagram via native platform APIs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fugazy_publish import instagram_client, tiktok_client
from fugazy_publish.config import AppConfig, format_hashtags


def _substitute(
    template: str,
    youtube_url: str,
    bio_link: str = "",
    tags: str = "",
) -> str:
    return (
        template.replace("{youtube_url}", youtube_url)
        .replace("{bio_link}", bio_link)
        .replace("{tags}", tags)
    )


def fan_out(
    teaser_path: Path,
    config: AppConfig,
    youtube_url: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    teaser_path = Path(teaser_path)
    social = config.social
    platforms = social.platforms or ["tiktok", "instagram"]
    bio_link = config.bio_link
    hashtag_line = format_hashtags(config.tags)

    tiktok_caption = _substitute(social.tiktok.title, youtube_url, bio_link, hashtag_line)
    ig_caption = _substitute(config.instagram.caption, youtube_url, bio_link, hashtag_line)

    ig_first = _substitute(
        config.instagram.first_comment or social.first_comment,
        youtube_url,
        bio_link,
        hashtag_line,
    )

    summary: dict[str, Any] = {
        "platforms": platforms,
        "dry_run": dry_run,
        "youtube_url": youtube_url,
        "captions": {
            "tiktok": tiktok_caption,
            "instagram": ig_caption,
        },
        "results": {},
    }

    if dry_run:
        summary["status"] = "dry_run"
        return summary

    if not teaser_path.is_file():
        raise FileNotFoundError(teaser_path)

    errors: list[str] = []
    for platform in platforms:
        key = platform.lower()
        try:
            if key == "tiktok":
                summary["results"][key] = tiktok_client.post_video(
                    teaser_path,
                    tiktok_caption,
                    config,
                    dry_run=False,
                )
            elif key == "instagram":
                summary["results"][key] = instagram_client.post_video(
                    teaser_path,
                    ig_caption,
                    config,
                    first_comment=ig_first,
                    dry_run=False,
                )
            else:
                raise ValueError(f"Unsupported platform: {platform}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{key}: {exc}")
            summary["results"][key] = {"platform": key, "status": "error", "error": str(exc)}

    if errors:
        summary["status"] = "partial" if len(errors) < len(platforms) else "failed"
        summary["errors"] = errors
        if len(errors) == len(platforms):
            raise RuntimeError("; ".join(errors))
    else:
        summary["status"] = "submitted"
    return summary
