#!/usr/bin/env python3
"""List recent videos from a YouTube channel."""

from __future__ import annotations

import argparse
import sys

import yt_dlp


def main() -> int:
    parser = argparse.ArgumentParser(description="List YouTube channel video URLs")
    parser.add_argument(
        "channel",
        nargs="?",
        default="https://www.youtube.com/@fugazymiata/videos",
        help="Channel URL (default: @fugazymiata)",
    )
    parser.add_argument("-n", "--limit", type=int, default=20, help="Max videos")
    parser.add_argument("-o", "--output", help="Write URLs to file")
    args = parser.parse_args()

    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "playlistend": args.limit,
    }

    urls: list[str] = []
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(args.channel, download=False)
        for entry in info.get("entries") or []:
            if not entry:
                continue
            url = entry.get("url") or entry.get("webpage_url")
            if not url and entry.get("id"):
                url = f"https://youtu.be/{entry['id']}"
            if url:
                urls.append(url)

    for url in urls:
        print(url)

    if args.output:
        Path = __import__("pathlib").Path
        Path(args.output).write_text("\n".join(urls) + "\n", encoding="utf-8")
        print(f"Wrote {len(urls)} URLs to {args.output}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
