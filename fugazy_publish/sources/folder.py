"""Folder source implementation."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import cast

from fugazy_publish.sources import Source, Submission


class FolderSource(Source):
    """Source that reads videos from a folder with optional sidecar YAML files."""
    
    def __init__(self, root: Path):
        self.root = root
        self._video_extensions = {".mp4", ".mov", ".m4v"}
    
    def pending(self) -> list[Submission]:
        """Get list of pending submissions (videos with no marker files)."""
        pending_submissions = []
        
        # Get all video files in the root directory
        for video_file in self.root.iterdir():
            if not video_file.is_file():
                continue
            
            # Check if it's a video file
            if video_file.suffix.lower() not in self._video_extensions:
                continue
            
            # Check if there's a marker file for this video
            stem = video_file.stem
            processing_file = self.root / f"{stem}.processing"
            published_file = self.root / f"{stem}.published.json"
            failed_file = self.root / f"{stem}.failed.txt"
            
            # If any marker file exists, this submission is not pending
            if processing_file.exists() or published_file.exists() or failed_file.exists():
                continue
            
            # Read sidecar YAML if it exists
            overrides = self._read_sidecar_yaml(stem)
            
            submission = Submission(
                id=stem,
                video=video_file,
                ref=str(video_file),
                overrides=overrides,
                submitter=""
            )
            pending_submissions.append(submission)
        
        # Sort by name for consistent ordering
        return sorted(pending_submissions, key=lambda s: s.id)
    
    def stuck(self) -> list[Submission]:
        """Get list of stuck submissions (those with .processing marker)."""
        stuck_submissions = []
        
        # Find all processing marker files
        for marker_file in self.root.glob("*.processing"):
            if not marker_file.is_file():
                continue
            
            stem = marker_file.stem
            # Skip if the video file doesn't exist
            video_file = self.root / f"{stem}.mp4"
            if not video_file.exists():
                video_file = self.root / f"{stem}.mov"
            if not video_file.exists():
                video_file = self.root / f"{stem}.m4v"
            
            if not video_file.exists():
                continue  # Video file doesn't exist, so we can't process this
            
            # Read sidecar YAML if it exists
            overrides = self._read_sidecar_yaml(stem)
            
            submission = Submission(
                id=stem,
                video=video_file,
                ref=str(video_file),
                overrides=overrides,
                submitter=""
            )
            stuck_submissions.append(submission)
        
        # Sort by name for consistent ordering
        return sorted(stuck_submissions, key=lambda s: s.id)
    
    def claim(self, submission: Submission) -> bool:
        """Attempt to claim a submission by creating a .processing marker file."""
        processing_file = self.root / f"{submission.id}.processing"
        
        try:
            # Try to create the marker file exclusively (atomically)
            with open(processing_file, "x") as _:
                pass  # File created successfully
            return True
        except FileExistsError:
            # File already exists, so someone else claimed it
            return False
    
    def fetch(self, submission: Submission, dest_dir: Path) -> Path:
        """Fetch the video file for a submission - in this case, just return the local path."""
        if submission.video is None:
            raise ValueError("Submission has no video path")
        return submission.video
    
    def report_published(self, submission: Submission, result: dict) -> None:
        """Report that a submission was published successfully."""
        processing_file = self.root / f"{submission.id}.processing"
        published_file = self.root / f"{submission.id}.published.json"
        
        # Remove processing marker
        if processing_file.exists():
            processing_file.unlink()
        
        # Write published result
        with open(published_file, "w") as f:
            json.dump(result, f)
    
    def report_failed(self, submission: Submission, error: str) -> None:
        """Report that a submission failed to publish."""
        processing_file = self.root / f"{submission.id}.processing"
        failed_file = self.root / f"{submission.id}.failed.txt"
        
        # Remove processing marker
        if processing_file.exists():
            processing_file.unlink()
        
        # Write error
        with open(failed_file, "w") as f:
            f.write(error)
    
    def _read_sidecar_yaml(self, stem: str) -> dict:
        """Read sidecar YAML file if it exists."""
        # Try both .yaml and .yml extensions
        for ext in [".yaml", ".yml"]:
            sidecar_file = self.root / f"{stem}{ext}"
            if sidecar_file.exists():
                try:
                    import yaml
                    with open(sidecar_file, "r") as f:
                        data = yaml.safe_load(f)
                        return data if isinstance(data, dict) else {}
                except Exception:
                    # YAML parsing error - treat as empty overrides
                    return {}
        return {}