"""Source interface for video publishing."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass
class Submission:
    """A video submission with optional sidecar configuration."""
    id: str
    video: Path | None
    ref: str
    overrides: dict
    submitter: str = ""


class Source(Protocol):
    """Protocol for video sources."""
    
    def pending(self) -> list[Submission]:
        """Get list of pending submissions."""
        ...
    
    def stuck(self) -> list[Submission]:
        """Get list of stuck (claimed) submissions."""
        ...
    
    def claim(self, submission: Submission) -> bool:
        """Attempt to claim a submission. Returns True if successful."""
        ...
    
    def fetch(self, submission: Submission, dest_dir: Path) -> Path:
        """Fetch the video file for a submission."""
        ...
    
    def report_published(self, submission: Submission, result: dict) -> None:
        """Report that a submission was published successfully."""
        ...
    
    def report_failed(self, submission: Submission, error: str) -> None:
        """Report that a submission failed to publish."""
        ...