"""Tests for per-video overrides functionality."""
import pytest
from fugazy_publish.config import (
    merge_overrides,
    override_errors,
    load_config,
    title_from,
)


def test_merge_overrides():
    # Test basic merge
    base = {"a": 1, "b": {"c": 2}}
    override = {"b": {"d": 3}}
    result = merge_overrides(base, override)
    assert result == {"a": 1, "b": {"c": 2, "d": 3}}

    # Test list replacement
    base = {"tags": ["a", "b"]}
    override = {"tags": ["c", "d"]}
    result = merge_overrides(base, override)
    assert result == {"tags": ["c", "d"]}

    # Test nested override
    base = {"teaser": {"overlay": {"text": "old"}}}
    override = {"teaser": {"overlay": {"text": "new"}}}
    result = merge_overrides(base, override)
    assert result == {"teaser": {"overlay": {"text": "new"}}}

    # Test untouched keys
    base = {"a": 1, "b": 2}
    override = {"a": 3}
    result = merge_overrides(base, override)
    assert result == {"a": 3, "b": 2}


def test_override_errors():
    # Test forbidden key
    errors = override_errors({"paths": {"credentials_dir": "/tmp"}})
    assert errors == ["paths.credentials_dir: not allowed per video"]

    # Test unknown key
    errors = override_errors({"teaser": {"overlay": {"txt": "X"}}})
    assert errors == ["teaser.overlay.txt: unknown setting"]

    # Test valid key
    errors = override_errors({"teaser": {"start_seconds": 41}})
    assert errors == []

    # Test multiple errors
    errors = override_errors({
        "paths": {"credentials_dir": "/tmp"},
        "teaser": {"overlay": {"txt": "X"}}
    })
    assert len(errors) == 2
    assert "paths.credentials_dir" in errors[0]
    assert "teaser.overlay.txt" in errors[1]


def test_load_config_with_overrides():
    # Test valid override
    config = load_config("config.example.yaml", overrides={"teaser": {"start_seconds": 41}})
    assert config.teaser.start_seconds == 41

    # Test forbidden key raises error
    with pytest.raises(ValueError, match="not allowed per video"):
        load_config("config.example.yaml", overrides={"paths": {"credentials_dir": "/tmp"}})

    # Test unknown key raises error
    with pytest.raises(ValueError, match="unknown setting"):
        load_config("config.example.yaml", overrides={"teaser": {"overlay": {"txt": "X"}}})


def test_title_from():
    # Test title from overrides
    assert title_from({"title": "Test Title"}) == "Test Title"
    assert title_from({}) is None
    assert title_from(None) is None