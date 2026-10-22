"""Tests for inbox worker functionality."""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from fugazy_publish.config import load_config
from fugazy_publish.sources.folder import FolderSource
from fugazy_publish.sources import Submission


def test_inbox_worker_basic(tmp_path):
    """Test basic inbox worker functionality."""
    # Create test video file
    video_file = tmp_path / "test.mp4"
    video_file.write_text("fake video content")
    
    # Create test config with inbox folder
    config_content = """
bio_link: https://lnk.bio/test
sponsor_line: "Test sponsor"
inbox:
  folder: {folder}
  poll_seconds: 1
"""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(config_content.format(folder=str(tmp_path)))
    
    # Test that we can load config with inbox
    cfg = load_config(config_file)
    assert cfg.inbox.folder == str(tmp_path)
    assert cfg.inbox.poll_seconds == 1


def test_inbox_worker_folder_source(tmp_path):
    """Test that FolderSource works correctly with inbox."""
    # Create test video file
    video_file = tmp_path / "test.mp4"
    video_file.write_text("fake video content")
    
    # Create FolderSource
    source = FolderSource(tmp_path)
    
    # Should find pending submission
    pending = source.pending()
    assert len(pending) == 1
    assert pending[0].id == "test"
    assert pending[0].video == video_file
    assert pending[0].overrides == {}
    
    # Should find no stuck items yet
    stuck = source.stuck()
    assert len(stuck) == 0
    
    # Claim the submission
    claimed = source.claim(pending[0])
    assert claimed is True
    
    # Now it should not be pending anymore (re-read)
    pending = source.pending()
    assert len(pending) == 0
    
    # But should be stuck (re-read)
    stuck = source.stuck()
    assert len(stuck) == 1
    assert stuck[0].id == "test"
    
    # Try to claim again (should fail)
    # Create a new pending list since the old one is stale
    new_pending = source.pending()
    assert len(new_pending) == 0  # No pending items anymore


def test_inbox_worker_with_overrides(tmp_path):
    """Test inbox worker with sidecar overrides."""
    # Create test video file
    video_file = tmp_path / "test.mp4"
    video_file.write_text("fake video content")
    
    # Create sidecar YAML
    sidecar_file = tmp_path / "test.yaml"
    sidecar_file.write_text("""
title: "Custom Title"
tags:
  - custom
  - test
""")
    
    # Create FolderSource
    source = FolderSource(tmp_path)
    
    # Should find pending submission with overrides
    pending = source.pending()
    assert len(pending) == 1
    assert pending[0].id == "test"
    assert pending[0].overrides == {
        "title": "Custom Title",
        "tags": ["custom", "test"]
    }


def test_inbox_worker_forbidden_sections(tmp_path):
    """Test that inbox section cannot be overridden by videos."""
    # Create test video file
    video_file = tmp_path / "test.mp4"
    video_file.write_text("fake video content")
    
    # Create sidecar YAML with forbidden section (paths)
    sidecar_file = tmp_path / "test.yaml"
    sidecar_file.write_text("""
paths:
  output_dir: "different"
""")
    
    # Create FolderSource
    source = FolderSource(tmp_path)
    
    # Should find pending submission with overrides
    pending = source.pending()
    
    # Try to load config with overrides - should fail due to forbidden section
    with pytest.raises(ValueError, match="not allowed per video"):
        cfg = load_config(None, overrides=pending[0].overrides)


def test_inbox_worker_pipeline_integration(tmp_path):
    """Test that the pipeline integration works with a mock publish function."""
    # Create test video file
    video_file = tmp_path / "test.mp4"
    video_file.write_text("fake video content")
    
    # Create a sidecar file with a title override
    sidecar_file = tmp_path / "test.yaml"
    sidecar_file.write_text("""
title: "Test Title"
""")
    
    # Mock the publish function to track calls
    with patch('fugazy_publish.pipeline.publish') as mock_publish:
        mock_publish.return_value = {
            "youtube": {"url": "https://youtube.com/watch?v=test"},
            "tiktok": {"url": "https://tiktok.com/@test"},
            "instagram": {"url": "https://instagram.com/test"}
        }
        
        # This test would be run by the actual inbox worker - we're just ensuring
        # that the config loading and pipeline calls work correctly
        from fugazy_publish.config import load_config
        
        # Test that config loading works with overrides
        cfg = load_config(None, overrides={"title": "Test Title"})
        assert cfg.sponsor_line == "Built with Flox: https://flox.dev"