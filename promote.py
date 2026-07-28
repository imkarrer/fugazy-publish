#!/usr/bin/env python3
"""Promote existing YouTube videos: download, teaser, fan out to social."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from fugazy_publish.config import load_config
from fugazy_publish.pipeline import promote_existing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create lead-in teaser from an existing YouTube video and post to social",
    )
    parser.add_argument(
        "youtube",
        nargs="*",
        help="YouTube URL(s) or video ID(s)",
    )
    parser.add_argument(
        "--title",
        default=None,
        help="Override campaign title (default: video title from YouTube)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to config.yaml",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned actions without downloading or posting",
    )
    parser.add_argument(
        "--review",
        "--pause",
        dest="review",
        action="store_true",
        help="Clean audio + build teaser, then pause before posting so you "
        "can review the files (they are kept on disk instead of deleted)",
    )
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Re-download even if cached in output/downloads/",
    )
    parser.add_argument(
        "--local-file",
        type=Path,
        default=None,
        help="Use this local MP4 instead of downloading (single video only)",
    )
    parser.add_argument(
        "--file",
        dest="url_file",
        type=Path,
        default=None,
        help="Text file with one YouTube URL/ID per line",
    )

    args = parser.parse_args(argv)

    urls: list[str] = list(args.youtube)
    if args.url_file:
        lines = args.url_file.read_text(encoding="utf-8").splitlines()
        urls.extend(line.strip() for line in lines if line.strip() and not line.startswith("#"))

    if not urls:
        parser.error("provide at least one YouTube URL/ID or --file")

    if args.local_file and len(urls) != 1:
        parser.error("--local-file requires exactly one YouTube URL/ID")
    if args.review and args.dry_run:
        parser.error("--review and --dry-run cannot be combined")

    cfg = load_config(args.config)
    results: list[dict] = []
    exit_code = 0

    for url in urls:
        try:
            result = promote_existing(
                url,
                title=args.title,
                config=cfg,
                dry_run=args.dry_run,
                force_download=args.force_download,
                local_file=args.local_file,
                review=args.review,
            )
            results.append(result)
        except Exception as exc:  # noqa: BLE001
            exit_code = 1
            results.append({"youtube_input": url, "error": str(exc)})
            print(f"Error ({url}): {exc}", file=sys.stderr)

    print(json.dumps(results if len(results) > 1 else results[0], indent=2, default=str))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
