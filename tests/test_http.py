"""Tests for HTTP client module."""

import tempfile
from pathlib import Path

import pytest

from bm.http import HttpClient, OfflineModeError


@pytest.fixture
def temp_cache():
    """Create a temporary cache directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_offline_mode_no_network_calls(temp_cache):
    """Test that offline mode makes zero network calls (T3 acceptance criteria)."""
    client = HttpClient(
        cache_dir=temp_cache,
        offline=True,
        user_agent="test-agent",
    )

    # Attempting to fetch without cache should raise OfflineModeError
    with pytest.raises(OfflineModeError):
        client.get("https://example.com/test")

    # Verify zero network calls
    assert client.network_call_count == 0

    client.close()


def test_cache_hit_no_network_call(temp_cache):
    """Test that cache hits don't make network calls."""
    import base64

    # Pre-populate cache
    client1 = HttpClient(
        cache_dir=temp_cache,
        offline=False,
        user_agent="test-agent",
    )

    # Manually add to cache with correct format
    cache_key = client1._cache_key("https://example.com/cached")
    content = b'{"data": "cached"}'
    client1._cache.set(
        cache_key,
        {
            "status_code": 200,
            "headers": {"content-type": "application/json"},
            "content_b64": base64.b64encode(content).decode("ascii"),
            "url": "https://example.com/cached",
        },
    )
    client1.close()

    # New client in offline mode should find cached response
    client2 = HttpClient(
        cache_dir=temp_cache,
        offline=True,
        user_agent="test-agent",
    )

    response = client2.get("https://example.com/cached")
    assert response.status_code == 200
    assert client2.network_call_count == 0

    client2.close()


def test_rate_limiter_basic():
    """Test that rate limiter exists and functions."""
    from bm.http import RateLimiter

    limiter = RateLimiter(requests_per_second=10.0)

    # First request should be immediate
    start = __import__("time").monotonic()
    limiter.acquire()
    elapsed = __import__("time").monotonic() - start

    # Should be near-instant for first token
    assert elapsed < 0.1


def test_domain_rate_limits():
    """Test that SEC domain has correct rate limit."""
    from bm.http import DOMAIN_RATE_LIMITS

    assert DOMAIN_RATE_LIMITS["sec.gov"] == 8.0
    assert DOMAIN_RATE_LIMITS["data.sec.gov"] == 8.0
    assert "default" in DOMAIN_RATE_LIMITS


def test_cache_key_uniqueness(temp_cache):
    """Test that cache keys are unique for different URLs/params."""
    client = HttpClient(cache_dir=temp_cache, offline=True)

    key1 = client._cache_key("https://example.com/a")
    key2 = client._cache_key("https://example.com/b")
    key3 = client._cache_key("https://example.com/a", {"param": "1"})
    key4 = client._cache_key("https://example.com/a", {"param": "2"})

    assert key1 != key2
    assert key1 != key3
    assert key3 != key4

    client.close()


def test_clear_cache(temp_cache):
    """Test cache clearing."""
    client = HttpClient(cache_dir=temp_cache, offline=True)

    # Add to cache
    cache_key = client._cache_key("https://example.com/test")
    client._cache.set(cache_key, {"status_code": 200, "headers": {}, "content": "", "url": ""})

    assert len(client._cache) > 0

    client.clear_cache()
    assert len(client._cache) == 0

    client.close()
