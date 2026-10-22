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


def test_title_from_missing_title():
    # Test title_from with missing title
    assert title_from({"other_key": "value"}) is None


def test_title_from_non_dict():
    # Test title_from with non-dict override
    assert title_from("not_a_dict") is None


def test_override_errors_empty_override():
    # Test override_errors with empty override
    assert override_errors({}) == []


def test_override_errors_nested_allowed_key():
    # Test override_errors with nested allowed key that isn't a leaf
    # teaser.overlay is a mapping, but teaser.overlay.text is a leaf
    errors = override_errors({"teaser": {"overlay": {"text": "test"}}})
    assert errors == []


def test_merge_overrides_list_replace():
    # Test merge_overrides with list replacement
    base = {"tags": ["old1", "old2"]}
    override = {"tags": ["new1", "new2"]}
    result = merge_overrides(base, override)
    assert result == {"tags": ["new1", "new2"]}


def test_merge_overrides_dict_replace():
    # Test merge_overrides with dict replacement
    base = {"audio": {"enabled": True}}
    override = {"audio": {"enabled": False}}
    result = merge_overrides(base, override)
    assert result == {"audio": {"enabled": False}}