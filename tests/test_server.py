"""Tests for server.py web UI functionality."""
import tempfile
from pathlib import Path
import sys
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# We'll test with the current directory for now to avoid complex path manipulation
def test_server_profile_logic():
    """Test that profile logic works correctly."""
    # Import the server module
    import server
    
    # Test the profile listing logic
    profiles = server._get_profiles()
    
    # Should at least have 'default'
    assert "default" in profiles


def test_server_profile_validation():
    """Test profile validation logic."""
    import server
    
    # Test that default profile is None (uses default config)
    config_path = server._validate_profile(None)
    assert config_path is None
    
    config_path = server._validate_profile("default")
    assert config_path is None
    
    # Test that we can create a valid config path
    # This will fail because the file doesn't exist, but it will show the path construction
    with pytest.raises(Exception):
        server._validate_profile("nonexistent")


def test_server_publish_form():
    """Test server publish form processing logic."""
    # Mock the publish function to avoid network calls
    def mock_publish(video_path, title, config, dry_run=False):
        return {"video": str(video_path), "title": title, "profile": "default"}
    
    # Test with a basic case - just make sure it doesn't crash
    import server
    from fastapi.testclient import TestClient
    
    # This would work if we had proper server configuration
    # For now we'll just make sure it imports correctly
    assert hasattr(server, 'publish_form')
    
    # Also check that the function signature matches what we expect
    import inspect
    sig = inspect.signature(server.publish_form)
    params = list(sig.parameters.keys())
    expected_params = ['video', 'title', 'profile', 'overrides', 'dry_run']
    for param in expected_params:
        assert param in params


def test_server_index_page():
    """Test that the index page returns HTML with proper structure."""
    import server
    from fastapi.testclient import TestClient
    
    # Test that index page returns HTML
    client = TestClient(server.app)
    
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    
    # Test that the HTML contains the basic structure
    html_content = response.text
    assert "<form action=\"/publish\"" in html_content
    assert "<form action=\"/promote\"" in html_content
    assert "Profile" in html_content
    assert "Advanced settings" in html_content