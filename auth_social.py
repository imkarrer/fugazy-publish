#!/usr/bin/env python3
"""One-time OAuth for native social platform APIs."""

from __future__ import annotations

import argparse
import json
import sys

from fugazy_publish import instagram_client, tiktok_client
from fugazy_publish.config import load_config

PLATFORMS = {
    "tiktok": tiktok_client.authorize,
    "instagram": instagram_client.authorize,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Authorize TikTok or Instagram APIs")
    parser.add_argument(
        "platform",
        choices=sorted(PLATFORMS),
        help="Platform to authorize",
    )
    parser.add_argument("--config", default=None, help="Path to config.yaml")
    parser.add_argument("--port", type=int, default=8765, help="Local OAuth callback port")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    authorize = PLATFORMS[args.platform]
    token = authorize(cfg, port=args.port)
    safe = {k: v for k, v in token.items() if k not in {"access_token", "refresh_token"}}
    print(f"Authorized {args.platform}.")
    print(json.dumps(safe, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
