import requests
import sys
from typing import Any


def notify_published(webhook_url: str, title: str, result: dict[str, Any]) -> None:
    if not webhook_url:
        return
    lines = [title]
    youtube_url = result.get("youtube_url")
    if youtube_url:
        lines.append(youtube_url)
    for platform in ("tiktok", "instagram"):
        link = result.get("social", {}).get("results", {}).get(platform, {}).get("url")
        if link:
            lines.append(link)
    content = "\n".join(lines)
    try:
        requests.post(webhook_url, json={"content": content}, timeout=10)
    except Exception as exc:
        print(f"Discord notify failed: {exc}", file=sys.stderr)