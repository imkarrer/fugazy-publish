"""Tests for sheet_rows module."""

import pytest
from fugazy_publish.sources.sheet_rows import row_to_submission_parts


def test_row_to_submission_parts():
    """Test the row_to_submission_parts function with various scenarios."""
    
    # Test case 1: teaser.start_seconds '41' becomes 41.0
    headers = ['file', 'title', 'teaser.start_seconds']
    row = ['video.mp4', 'Test Title', '41']
    fields, overrides, errors = row_to_submission_parts(headers, row)
    assert fields == {'file': 'video.mp4', 'title': 'Test Title'}
    assert overrides == {'title': 'Test Title', 'teaser': {'start_seconds': 41.0}}
    assert errors == []
    
    # Test case 2: social.platforms 'tiktok, youtube' becomes a list
    headers = ['file', 'social.platforms']
    row = ['video.mp4', 'tiktok, youtube']
    fields, overrides, errors = row_to_submission_parts(headers, row)
    assert fields == {'file': 'video.mp4'}
    assert overrides == {'social': {'platforms': ['tiktok', 'youtube']}}
    assert errors == []
    
    # Test case 3: audio.enabled 'FALSE' becomes False
    headers = ['file', 'audio.enabled']
    row = ['video.mp4', 'FALSE']
    fields, overrides, errors = row_to_submission_parts(headers, row)
    assert fields == {'file': 'video.mp4'}
    assert overrides == {'audio': {'enabled': False}}
    assert errors == []
    
    # Test case 4: config cell overriding a column
    headers = ['file', 'config', 'title']
    row = ['video.mp4', 'teaser:\n  start_seconds: 30\n', 'Custom Title']
    fields, overrides, errors = row_to_submission_parts(headers, row)
    assert fields == {'file': 'video.mp4', 'title': 'Custom Title'}
    assert overrides == {'title': 'Custom Title', 'teaser': {'start_seconds': 30.0}}
    assert errors == []
    
    # Test case 5: unknown non-empty column producing an error
    headers = ['file', 'titel']  # typo in title
    row = ['video.mp4', 'some value']
    fields, overrides, errors = row_to_submission_parts(headers, row)
    assert fields == {'file': 'video.mp4'}
    assert overrides == {}
    assert errors == ['Unknown column "titel"']
    
    # Test case 6: '#notes' column ignored
    headers = ['file', '#notes', 'title']
    row = ['video.mp4', 'some note', 'Test Title']
    fields, overrides, errors = row_to_submission_parts(headers, row)
    assert fields == {'file': 'video.mp4', 'title': 'Test Title'}
    assert overrides == {'title': 'Test Title'}
    assert errors == []


def test_empty_cells():
    """Test behavior with empty cells."""
    headers = ['file', 'teaser.start_seconds', 'title']
    row = ['video.mp4', '', 'Test Title']
    fields, overrides, errors = row_to_submission_parts(headers, row)
    assert fields == {'file': 'video.mp4', 'title': 'Test Title'}
    # Empty teaser.start_seconds should be skipped, not set to None/empty
    assert overrides == {'title': 'Test Title'}
    assert errors == []


def test_config_header_errors():
    """Test error handling for config header."""
    # Test invalid YAML in config cell
    headers = ['file', 'config']
    row = ['video.mp4', 'invalid: yaml: content']
    fields, overrides, errors = row_to_submission_parts(headers, row)
    assert fields == {'file': 'video.mp4'}
    assert overrides == {}
    assert len(errors) == 1
    assert 'Invalid YAML' in errors[0]
    
    # Test non-mapping YAML in config cell
    headers = ['file', 'config']
    row = ['video.mp4', 'not_a_mapping: [1, 2, 3]']
    fields, overrides, errors = row_to_submission_parts(headers, row)
    assert fields == {'file': 'video.mp4'}
    assert overrides == {}
    assert len(errors) == 1
    assert 'YAML mapping' in errors[0]


def test_boolean_parsing():
    """Test boolean parsing behavior."""
    # Test various true values
    for true_val in ['true', 'TRUE', 'yes', 'YES', '1']:
        headers = ['file', 'audio.enabled']
        row = ['video.mp4', true_val]
        fields, overrides, errors = row_to_submission_parts(headers, row)
        assert overrides == {'audio': {'enabled': True}}
        assert errors == []
    
    # Test various false values
    for false_val in ['false', 'FALSE', 'no', 'NO', '0']:
        headers = ['file', 'audio.enabled']
        row = ['video.mp4', false_val]
        fields, overrides, errors = row_to_submission_parts(headers, row)
        assert overrides == {'audio': {'enabled': False}}
        assert errors == []


def test_number_parsing():
    """Test number parsing behavior."""
    # Test int parsing
    headers = ['file', 'teaser.duration_seconds']
    row = ['video.mp4', '42']
    fields, overrides, errors = row_to_submission_parts(headers, row)
    assert overrides == {'teaser': {'duration_seconds': 42}}
    assert errors == []
    
    # Test float parsing
    headers = ['file', 'teaser.start_seconds']
    row = ['video.mp4', '41.5']
    fields, overrides, errors = row_to_submission_parts(headers, row)
    assert overrides == {'teaser': {'start_seconds': 41.5}}
    assert errors == []


def test_list_parsing():
    """Test list parsing behavior."""
    headers = ['file', 'youtube.default_tags']
    row = ['video.mp4', 'tag1, tag2, tag3']
    fields, overrides, errors = row_to_submission_parts(headers, row)
    assert overrides == {'youtube': {'default_tags': ['tag1', 'tag2', 'tag3']}}
    assert errors == []
    
    # Test list with numeric values
    headers = ['file', 'teaser.audio.notch.freq_hz']
    row = ['video.mp4', '3700, 3800, 3900']
    fields, overrides, errors = row_to_submission_parts(headers, row)
    assert overrides == {'teaser': {'audio': {'notch': {'freq_hz': [3700, 3800, 3900]}}}}
    assert errors == []

def test_short_row_is_padded_with_empty_cells():
    fields, overrides, errors = row_to_submission_parts(
        ["file", "title", "teaser.start_seconds"], ["video.mp4"]
    )
    assert fields["file"] == "video.mp4"
    assert fields == {"file": "video.mp4", "title": ""}
    assert "title" not in overrides
    assert overrides == {}
    assert errors == []
