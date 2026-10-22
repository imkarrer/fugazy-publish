#!/usr/bin/env python3
"""Inbox worker that processes videos from a folder."""

import argparse
import sys
import time
from pathlib import Path
from typing import cast

from fugazy_publish.config import load_config
from fugazy_publish.sources.folder import FolderSource
from fugazy_publish.sources import sheet
from fugazy_publish.pipeline import publish
from fugazy_publish.notify import notify_published


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inbox worker for publishing videos")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to config.yaml (default: project root config.yaml)",
    )
    parser.add_argument(
        "--source",
        choices=["folder", "sheet"],
        default="folder",
        help="Where submissions come from (default: folder)",
    )
    parser.add_argument(
        "--folder",
        type=Path,
        default=None,
        help="Folder to watch for videos (default: config.inbox.folder)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one pass and exit",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print planned actions without uploading",
    )

    args = parser.parse_args(argv)

    # Load configuration
    cfg = load_config(args.config)

    # Create source
    if args.source == "sheet":
        source = sheet.create_source(cfg)
    else:
        folder_path = args.folder or Path(cfg.inbox.folder)
        if not folder_path.exists():
            print(f"Error: Folder does not exist: {folder_path}", file=sys.stderr)
            return 1
        source = FolderSource(folder_path)

    while True:
        # Print stuck items as warnings
        stuck_items = source.stuck()
        if stuck_items:
            print("Warning: Found stuck items (processing marker exists but video is missing):")
            for item in stuck_items:
                print(f"  {item.id}")
        
        # Process pending items
        pending_items = source.pending()
        for item in pending_items:
            # Attempt to claim the item
            if not source.claim(item):
                print(f"Warning: Could not claim item {item.id}, skipping...")
                continue
            
            try:
                # Load config with overrides
                try:
                    item_config = load_config(args.config, overrides=item.overrides)
                except ValueError as e:
                    # Override error - mark as failed and continue
                    source.report_failed(item, str(e))
                    print(f"Error in overrides for {item.id}: {e}")
                    continue
                
                # Fetch video into output directory
                video_path = source.fetch(item, Path(item_config.paths.output_dir))
                
                # Determine title
                title = item.overrides.get("title") or video_path.stem
                
                # Publish the video
                result = publish(
                    video_path,
                    title,
                    config=item_config,
                    dry_run=args.dry_run,
                )
                
                # Report success
                source.report_published(item, result)
                notify_published(item_config.inbox.notify_webhook, title, result)
                print(f"Published {item.id}")
                
            except Exception as e:
                # Report failure
                source.report_failed(item, str(e))
                print(f"Failed to publish {item.id}: {e}")
        
        # Check if we should exit
        if args.once:
            break
            
        # Sleep before next pass
        time.sleep(cfg.inbox.poll_seconds)
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())