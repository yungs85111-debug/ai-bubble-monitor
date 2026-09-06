"""
HTTP client for Bubble Monitor.

Rate-limited, cached, retrying HTTP client with offline mode support.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from diskcache import Cache
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from bm.config import get_config

logger = logging.getLogger(__name__)


class OfflineModeError(Exception):
    """Attempted network call in offline mode."""

    pass


class RateLimitError(Exception):
    """Rate limit exceeded."""

    pass


@dataclass
class RateLimiter:
    """Per-domain rate limiter using token bucket algorithm."""

    requests_per_second: float
    _tokens: float = field(init=False)
    _last_update: float = field(init=False)

    def __post_init__(self) -> None:
        self._tokens = self.requests_per_second
        self._last_update = time.monotonic()

    def acquire(self) -> None:
        """Acquire a token, blocking if necessary."""
        now = time.monotonic()
        elapsed = now - self._last_update
        self._tokens = min(
            self.requests_per_second,
            self._tokens + elapsed * self.requests_per_second,
        )
        self._last_update = now

        if self._tokens < 1:
            sleep_time = (1 - self._tokens) / self.requests_per_second
            logger.debug(f"Rate limiting: sleeping {sleep_time:.2f}s")
            time.sleep(sleep_time)
            self._tokens = 0
        else:
            self._tokens -= 1


# Domain-specific rate limits
DOMAIN_RATE_LIMITS: dict[str, float] = {
    "sec.gov": 8.0,  # SEC requires max 10 req/s, we use 8 for safety
    "data.sec.gov": 8.0,
    "efts.sec.gov": 8.0,
    "api.stlouisfed.org": 10.0,  # FRED
    "default": 5.0,
}


class HttpClient:
    """
    HTTP client with caching, rate limiting, and retry logic.

    Features:
    - Per-domain rate limiting
    - Disk caching with configurable TTL
    - Exponential backoff for retries
    - Offline mode support
    """

    def __init__(
        self,
        cache_dir: Path | None = None,
        offline: bool = False,
        user_agent: str | None = None,
        default_timeout: float = 30.0,
        cache_ttl: int = 86400,  # 24 hours default
    ):
        config = get_config()

        self.offline = offline or config.offline
        self.user_agent = user_agent or config.sec_user_agent
        self.default_timeout = default_timeout
        self.cache_ttl = cache_ttl

        cache_path = cache_dir or config.cache_dir
        cache_path.mkdir(parents=True, exist_ok=True)
        self._cache = Cache(str(cache_path))

        self._rate_limiters: dict[str, RateLimiter] = {}
        self._client: httpx.Client | None = None

        # Track network calls for testing
        self._network_call_count = 0

    def _get_client(self) -> httpx.Client:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.Client(
                timeout=self.default_timeout,
                headers={"User-Agent": self.user_agent},
                follow_redirects=True,
            )
        return self._client

    def _get_rate_limiter(self, domain: str) -> RateLimiter:
        """Get rate limiter for domain."""
        if domain not in self._rate_limiters:
            rate = DOMAIN_RATE_LIMITS.get(domain, DOMAIN_RATE_LIMITS["default"])
            self._rate_limiters[domain] = RateLimiter(rate)
        return self._rate_limiters[domain]

    def _cache_key(self, url: str, params: dict[str, Any] | None = None) -> str:
        """Generate cache key for URL and params."""
        key_data = url
        if params:
            key_data += json.dumps(params, sort_keys=True)
        return hashlib.sha256(key_data.encode()).hexdigest()

    def _should_retry(self, response: httpx.Response) -> bool:
        """Check if response should trigger retry."""
        return response.status_code in (429, 500, 502, 503, 504)

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, RateLimitError)),
        wait=wait_exponential(multiplier=1, min=1, max=60),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    def _fetch(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Fetch URL with retry logic."""
        parsed = urlparse(url)
        domain = parsed.netloc

        # Apply rate limiting
        limiter = self._get_rate_limiter(domain)
        limiter.acquire()

        client = self._get_client()
        response = client.get(url, params=params, headers=headers)
        self._network_call_count += 1

        if self._should_retry(response):
            if response.status_code == 429:
                # Get retry-after header if available
                retry_after = response.headers.get("Retry-After", "5")
                try:
                    wait_time = int(retry_after)
                except ValueError:
                    wait_time = 5
                logger.warning(f"Rate limited by {domain}, waiting {wait_time}s")
                time.sleep(wait_time)
                raise RateLimitError(f"Rate limited by {domain}")
            else:
                raise httpx.TransportError(
                    f"Server error: {response.status_code}"
                )

        return response

    def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        use_cache: bool = True,
        cache_ttl: int | None = None,
    ) -> httpx.Response:
        """
        Make GET request with caching and rate limiting.

        Args:
            url: Request URL
            params: Query parameters
            headers: Additional headers
            use_cache: Whether to use cache
            cache_ttl: Cache TTL in seconds (overrides default)

        Returns:
            HTTP response

        Raises:
            OfflineModeError: If offline mode is enabled and cache miss
        """
        cache_key = self._cache_key(url, params)

        # Check cache first
        if use_cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                logger.debug(f"Cache hit: {url}")
                return self._deserialize_response(cached)

        # In offline mode, cache miss is an error
        if self.offline:
            raise OfflineModeError(
                f"Offline mode: no cached response for {url}"
            )

        # Fetch from network
        logger.debug(f"Fetching: {url}")
        response = self._fetch(url, params, headers)

        # Cache successful responses
        if use_cache and response.status_code == 200:
            ttl = cache_ttl or self.cache_ttl
            self._cache.set(
                cache_key,
                self._serialize_response(response),
                expire=ttl,
            )

        return response

    def get_json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        """Make GET request and parse JSON response."""
        response = self.get(url, params, **kwargs)
        response.raise_for_status()
        return response.json()

    def _serialize_response(self, response: httpx.Response) -> dict[str, Any]:
        """Serialize response for caching."""
        # Store raw bytes to avoid encoding issues with gzipped content
        import base64
        return {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "content_b64": base64.b64encode(response.content).decode("ascii"),
            "url": str(response.url),
        }

    def _deserialize_response(self, data: dict[str, Any]) -> httpx.Response:
        """Deserialize cached response."""
        import base64
        # Remove Content-Encoding header since httpx has already decoded
        headers = data["headers"].copy()
        headers.pop("content-encoding", None)
        headers.pop("Content-Encoding", None)

        # Create a minimal request object for the response
        request = httpx.Request("GET", data["url"])

        return httpx.Response(
            status_code=data["status_code"],
            headers=headers,
            content=base64.b64decode(data["content_b64"]),
            request=request,
        )

    def clear_cache(self) -> None:
        """Clear all cached responses."""
        self._cache.clear()
        logger.info("Cache cleared")

    def cache_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        return {
            "size": len(self._cache),
            "volume": self._cache.volume(),
        }

    @property
    def network_call_count(self) -> int:
        """Number of actual network calls made."""
        return self._network_call_count

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            self._client.close()
            self._client = None
        self._cache.close()


# Module-level client instance
_client: HttpClient | None = None


def get_http_client() -> HttpClient:
    """Get the global HTTP client instance."""
    global _client
    if _client is None:
        _client = HttpClient()
    return _client


def reset_http_client() -> None:
    """Reset the global HTTP client (for testing)."""
    global _client
    if _client:
        _client.close()
    _client = None
