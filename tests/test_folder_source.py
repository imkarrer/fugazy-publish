"""Test folder source implementation."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml

from fugazy_publish.sources import Submission
from fugazy_publish.sources.folder import FolderSource


def test_pending_lists_video_with_sidecar(tmp_path):
    """Test that pending lists a video with a sidecar YAML."""
    # Create a video file
    video_file = tmp_path / "test.mp4"
    video_file.write_text("fake video content")
    
    # Create a sidecar YAML file
    sidecar_file = tmp_path / "test.yaml"
    sidecar_data = {"youtube": {"title": "Test Title"}}
    sidecar_file.write_text(yaml.dump(sidecar_data))
    
    source = FolderSource(tmp_path)
    pending = source.pending()
    
    assert len(pending) == 1
    submission = pending[0]
    assert submission.id == "test"
    assert submission.video == video_file
    assert submission.overrides == sidecar_data


def test_pending_lists_video_without_sidecar(tmp_path):
    """Test that pending lists a video without a sidecar."""
    # Create a video file
    video_file = tmp_path / "test.mp4"
    video_file.write_text("fake video content")
    
    source = FolderSource(tmp_path)
    pending = source.pending()
    
    assert len(pending) == 1
    submission = pending[0]
    assert submission.id == "test"
    assert submission.video == video_file
    assert submission.overrides == {}


def test_claimed_item_leaves_pending_and_shows_in_stuck(tmp_path):
    """Test that a claimed item leaves pending and shows in stuck."""
    # Create a video file
    video_file = tmp_path / "test.mp4"
    video_file.write_text("fake video content")
    
    source = FolderSource(tmp_path)
    
    # Initially should be pending
    pending = source.pending()
    assert len(pending) == 1
    
    # Claim it
    submission = pending[0]
    assert source.claim(submission)
    
    # Should no longer be pending
    pending = source.pending()
    assert len(pending) == 0
    
    # Should be stuck
    stuck = source.stuck()
    assert len(stuck) == 1
    assert stuck[0].id == "test"


def test_claim_twice_returns_false_second_time(tmp_path):
    """Test that claiming twice returns False the second time."""
    # Create a video file
    video_file = tmp_path / "test.mp4"
    video_file.write_text("fake video content")
    
    source = FolderSource(tmp_path)
    
    # Claim it first time
    pending = source.pending()
    submission = pending[0]
    assert source.claim(submission)
    
    # Try to claim again - should return False
    assert not source.claim(submission)


def test_published_item_leaves_both_lists(tmp_path):
    """Test that a published item leaves both lists."""
    # Create a video file
    video_file = tmp_path / "test.mp4"
    video_file.write_text("fake video content")
    
    source = FolderSource(tmp_path)
    
    # Claim it
    pending = source.pending()
    submission = pending[0]
    assert source.claim(submission)
    
    # Report published
    source.report_published(submission, {"video_id": "test_video_id"})
    
    # Should be in neither list
    pending = source.pending()
    stuck = source.stuck()
    assert len(pending) == 0
    assert len(stuck) == 0


def test_failed_item_leaves_both_lists(tmp_path):
    """Test that a failed item leaves both lists."""
    # Create a video file
    video_file = tmp_path / "test.mp4"
    video_file.write_text("fake video content")
    
    source = FolderSource(tmp_path)
    
    # Claim it
    pending = source.pending()
    submission = pending[0]
    assert source.claim(submission)
    
    # Report failed
    source.report_failed(submission, "Test error")
    
    # Should be in neither list
    pending = source.pending()
    stuck = source.stuck()
    assert len(pending) == 0
    assert len(stuck) == 0


def test_txt_file_is_not_an_item(tmp_path):
    """Test that a .txt file is not considered an item."""
    # Create a video file
    video_file = tmp_path / "test.mp4"
    video_file.write_text("fake video content")
    
    # Create a txt file
    txt_file = tmp_path / "test.txt"
    txt_file.write_text("fake text content")
    
    source = FolderSource(tmp_path)
    pending = source.pending()
    
    # Should only find the video, not the txt file
    assert len(pending) == 1
    assert pending[0].id == "test"
    assert pending[0].video == video_file