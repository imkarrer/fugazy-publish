#!/usr/bin/env python3
"""CLI entrypoint for fugazy publish pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from fugazy_publish.config import load_config
from fugazy_publish.pipeline import publish


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Upload video and fan out teaser")
    parser.add_argument("video", type=Path, help="Path to source video file")
    parser.add_argument(
        "--title",
        default=None,
        help="YouTube / campaign title (default: source file name)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to config.yaml (default: project root config.yaml)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print planned actions without uploading",
    )
    parser.add_argument(
        "--review",
        "--pause",
        dest="review",
        action="store_true",
        help="Clean audio + build teaser, then pause before uploading so you "
        "can review the files (they are kept on disk instead of deleted)",
    )
    parser.add_argument(
        "--teaser-only",
        action="store_true",
        help="Skip YouTube upload; requires --youtube-url",
    )
    parser.add_argument(
        "--youtube-url",
        default=None,
        help="Existing YouTube watch URL (required with --teaser-only)",
    )

    args = parser.parse_args(argv)

    if args.teaser_only and not args.youtube_url:
        parser.error("--teaser-only requires --youtube-url")
    if args.review and args.dry_run:
        parser.error("--review and --dry-run cannot be combined")

    cfg = load_config(args.config)
    title = args.title or args.video.stem

    try:
        result = publish(
            args.video,
            title,
            config=cfg,
            config_path=args.config,
            dry_run=args.dry_run,
            skip_youtube=args.teaser_only,
            youtube_url=args.youtube_url,
            review=args.review,
        )
    except Exception as exc:  # noqa: BLE001 — CLI boundary
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
