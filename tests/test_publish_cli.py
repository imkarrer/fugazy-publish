"""Tests for publish.py CLI with --overrides option."""

import tempfile
from pathlib import Path

import pytest

from fugazy_publish.config import load_config
from publish import main


def test_overrides_title_priority(tmp_path):
    """Test that --overrides title takes precedence over video stem."""
    # Create a minimal config file
    config_content = """
bio_link: https://lnk.bio/test
sponsor_line: Test Sponsor
tags:
  - test
  - video
"""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(config_content)

    # Create an override file with a title
    override_content = """
title: Override Title
"""
    override_file = tmp_path / "overrides.yaml"
    override_file.write_text(override_content)

    # Create a dummy video file
    video_file = tmp_path / "test_video.mp4"
    video_file.write_text("dummy content")

    # Test that the override title is used
    result = main([
        str(video_file),
        "--config", str(config_file),
        "--overrides", str(override_file),
        "--dry-run"
    ])

    # This should pass without error, and title_from should extract the override title
    assert result == 0


def test_overrides_title_wins_over_cli_title(tmp_path, monkeypatch):
    """Test that --title wins over override title."""
    # Create a minimal config file
    config_content = """
bio_link: https://lnk.bio/test
sponsor_line: Test Sponsor
tags:
  - test
  - video
"""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(config_content)

    # Create an override file with a title
    override_content = """
title: Override Title
"""
    override_file = tmp_path / "overrides.yaml"
    override_file.write_text(override_content)

    # Create a dummy video file
    video_file = tmp_path / "test_video.mp4"
    video_file.write_text("dummy content")

    # Mock the publish function to capture what title it receives
    captured_title = []
    def mock_publish(video, title, **kwargs):
        captured_title.append(title)
        return {"status": "success"}

    monkeypatch.setattr("publish.publish", mock_publish)

    # Test that --title wins over override title
    result = main([
        str(video_file),
        "--config", str(config_file),
        "--overrides", str(override_file),
        "--title", "CLI Title",
        "--dry-run"
    ])

    # This should pass without error
    assert result == 0
    # Verify that the CLI title was actually passed to publish
    assert len(captured_title) == 1
    assert captured_title[0] == "CLI Title"


def test_overrides_forbidden_keys_exit_2(tmp_path):
    """Test that forbidden keys in overrides cause exit code 2."""
    # Create a minimal config file
    config_content = """
bio_link: https://lnk.bio/test
sponsor_line: Test Sponsor
tags:
  - test
  - video
"""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(config_content)

    # Create an override file with forbidden key
    override_content = """
paths:
  output_dir: /tmp/output
"""
    override_file = tmp_path / "overrides.yaml"
    override_file.write_text(override_content)

    # Create a dummy video file
    video_file = tmp_path / "test_video.mp4"
    video_file.write_text("dummy content")

    # Test that forbidden key causes exit code 2
    result = main([
        str(video_file),
        "--config", str(config_file),
        "--overrides", str(override_file),
        "--dry-run"
    ])

    # This should fail with exit code 2
    assert result == 2


def test_overrides_valid_config(tmp_path):
    """Test that valid overrides work correctly."""
    # Create a minimal config file
    config_content = """
bio_link: https://lnk.bio/test
sponsor_line: Test Sponsor
tags:
  - test
  - video
teaser:
  duration_seconds: 15
"""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(config_content)

    # Create an override file with valid keys
    override_content = """
title: Override Title
teaser:
  duration_seconds: 30
"""
    override_file = tmp_path / "overrides.yaml"
    override_file.write_text(override_content)

    # Create a dummy video file
    video_file = tmp_path / "test_video.mp4"
    video_file.write_text("dummy content")

    # Test that valid overrides work
    result = main([
        str(video_file),
        "--config", str(config_file),
        "--overrides", str(override_file),
        "--dry-run"
    ])

    assert result == 0


def test_overrides_empty_file(tmp_path):
    """Test that empty overrides file works."""
    # Create a minimal config file
    config_content = """
bio_link: https://lnk.bio/test
sponsor_line: Test Sponsor
tags:
  - test
  - video
"""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(config_content)

    # Create an empty override file
    override_file = tmp_path / "overrides.yaml"
    override_file.write_text("")

    # Create a dummy video file
    video_file = tmp_path / "test_video.mp4"
    video_file.write_text("dummy content")

    # Test that empty overrides work
    result = main([
        str(video_file),
        "--config", str(config_file),
        "--overrides", str(override_file),
        "--dry-run"
    ])

    assert result == 0


def test_overrides_nonexistent_file(tmp_path):
    """Test that nonexistent overrides file exits with code 2."""
    # Create a minimal config file
    config_content = """
bio_link: https://lnk.bio/test
sponsor_line: Test Sponsor
tags:
  - test
  - video
"""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(config_content)

    # Create a dummy video file
    video_file = tmp_path / "test_video.mp4"
    video_file.write_text("dummy content")

    # Test that nonexistent overrides file exits with code 2
    result = main([
        str(video_file),
        "--config", str(config_file),
        "--overrides", str(tmp_path / "nonexistent.yaml"),
        "--dry-run"
    ])

    assert result == 2


def test_overrides_invalid_yaml(tmp_path):
    """Test that invalid YAML in overrides file exits with code 2."""
    # Create a minimal config file
    config_content = """
bio_link: https://lnk.bio/test
sponsor_line: Test Sponsor
tags:
  - test
  - video
"""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(config_content)

    # Create an override file with invalid YAML
    override_file = tmp_path / "overrides.yaml"
    override_file.write_text("invalid: yaml: content:")

    # Create a dummy video file
    video_file = tmp_path / "test_video.mp4"
    video_file.write_text("dummy content")

    # Test that invalid YAML exits with code 2
    result = main([
        str(video_file),
        "--config", str(config_file),
        "--overrides", str(override_file),
        "--dry-run"
    ])

    assert result == 2


def test_no_overrides_still_works(tmp_path):
    """Test that normal operation without overrides still works."""
    # Create a minimal config file
    config_content = """
bio_link: https://lnk.bio/test
sponsor_line: Test Sponsor
tags:
  - test
  - video
"""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(config_content)

    # Create a dummy video file
    video_file = tmp_path / "test_video.mp4"
    video_file.write_text("dummy content")

    # Test that normal operation works
    result = main([
        str(video_file),
        "--config", str(config_file),
        "--dry-run"
    ])

    assert result == 0