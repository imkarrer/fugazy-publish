import pytest
from unittest.mock import Mock, patch

from fugazy_publish.notify import notify_published


def test_notify_published_empty_url():
    """Test that notify_published does nothing when webhook_url is empty."""
    with patch("fugazy_publish.notify.requests") as mock_requests:
        notify_published("", "Test Title", {})
        mock_requests.post.assert_not_called()


def test_notify_published_youtube_only():
    """Test that notify_published includes YouTube URL when present."""
    with patch("fugazy_publish.notify.requests") as mock_requests:
        mock_response = Mock()
        mock_requests.post.return_value = mock_response
        
        result = {
            "youtube_url": "https://www.youtube.com/watch?v=test123",
        }
        
        notify_published("https://discord.com/api/webhooks/test", "Test Title", result)
        
        mock_requests.post.assert_called_once_with(
            "https://discord.com/api/webhooks/test",
            json={
                "content": "Test Title\nhttps://www.youtube.com/watch?v=test123"
            },
            timeout=10
        )


def test_notify_published_with_social_links():
    """Test that notify_published includes social links when present."""
    with patch("fugazy_publish.notify.requests") as mock_requests:
        mock_response = Mock()
        mock_requests.post.return_value = mock_response
        
        result = {
            "youtube_url": "https://www.youtube.com/watch?v=test123",
            "social": {
                "results": {
                    "tiktok": {"url": "https://www.tiktok.com/@user/video/456"},
                    "instagram": {"url": "https://www.instagram.com/p/789/"}
                }
            }
        }
        
        notify_published("https://discord.com/api/webhooks/test", "Test Title", result)
        
        mock_requests.post.assert_called_once_with(
            "https://discord.com/api/webhooks/test",
            json={
                "content": "Test Title\nhttps://www.youtube.com/watch?v=test123\nhttps://www.tiktok.com/@user/video/456\nhttps://www.instagram.com/p/789/"
            },
            timeout=10
        )


def test_notify_published_request_failure():
    """Test that notify_published handles request failures gracefully."""
    with patch("fugazy_publish.notify.requests") as mock_requests:
        mock_requests.post.side_effect = Exception("Network error")
        
        notify_published("https://discord.com/api/webhooks/test", "Test Title", {})
        
        # Should not raise, just print to stderr
        mock_requests.post.assert_called_once_with(
            "https://discord.com/api/webhooks/test",
            json={"content": "Test Title"},
            timeout=10
        )