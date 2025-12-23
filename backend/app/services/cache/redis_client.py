"""Redis client for caching S&P 500 data, technical analysis, and pipeline results."""

import json
import os
from typing import Any

import redis


class RedisCache:
    """Redis cache client for the stock research pipeline.

    Caching strategy:
    - S&P 500 list: 24 hour TTL (changes rarely)
    - Technical analysis per ticker: 1 hour TTL (market data)
    - Pipeline results: 4 hour TTL (for quick retrieval)
    """

    # Cache key prefixes
    PREFIX_SP500 = "sp500"
    PREFIX_TECHNICAL = "tech"
    PREFIX_QUICK_SCAN = "quick"
    PREFIX_DEEP_RESEARCH = "deep"
    PREFIX_RECOMMENDATION = "rec"

    # Default TTLs in seconds
    TTL_SP500 = 24 * 60 * 60  # 24 hours
    TTL_TECHNICAL = 1 * 60 * 60  # 1 hour
    TTL_QUICK_SCAN = 4 * 60 * 60  # 4 hours
    TTL_DEEP_RESEARCH = 4 * 60 * 60  # 4 hours
    TTL_RECOMMENDATION = 4 * 60 * 60  # 4 hours

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        password: str | None = None,
        db: int = 0,
    ) -> None:
        """Initialize Redis connection.

        Args:
            host: Redis host (default: localhost)
            port: Redis port (default: 6379)
            password: Redis password
            db: Redis database number
        """
        self._host = host or os.getenv("REDIS__HOST", "localhost")
        self._port = port or int(os.getenv("REDIS__PORT", "6379"))
        self._password = password or os.getenv("REDIS__PASSWORD")
        self._db = db

        self._client = redis.Redis(
            host=self._host,
            port=self._port,
            password=self._password,
            db=self._db,
            decode_responses=True,
        )

    def ping(self) -> bool:
        """Check if Redis is connected."""
        try:
            return self._client.ping()
        except redis.ConnectionError:
            return False

    def _make_key(self, prefix: str, key: str) -> str:
        """Create a namespaced cache key."""
        return f"swingbot:{prefix}:{key}"

    # =========================================================================
    # S&P 500 List Cache
    # =========================================================================

    def get_sp500_list(self) -> list[dict] | None:
        """Get cached S&P 500 companies list."""
        key = self._make_key(self.PREFIX_SP500, "list")
        data = self._client.get(key)
        if data:
            return json.loads(data)
        return None

    def set_sp500_list(self, companies: list[dict], ttl: int | None = None) -> None:
        """Cache S&P 500 companies list."""
        key = self._make_key(self.PREFIX_SP500, "list")
        self._client.setex(
            key,
            ttl or self.TTL_SP500,
            json.dumps(companies),
        )

    # =========================================================================
    # Technical Analysis Cache
    # =========================================================================

    def get_technical_analysis(self, ticker: str) -> dict | None:
        """Get cached technical analysis for a ticker."""
        key = self._make_key(self.PREFIX_TECHNICAL, ticker.upper())
        data = self._client.get(key)
        if data:
            return json.loads(data)
        return None

    def set_technical_analysis(
        self,
        ticker: str,
        analysis: dict,
        ttl: int | None = None,
    ) -> None:
        """Cache technical analysis for a ticker."""
        key = self._make_key(self.PREFIX_TECHNICAL, ticker.upper())
        self._client.setex(
            key,
            ttl or self.TTL_TECHNICAL,
            json.dumps(analysis),
        )

    # =========================================================================
    # Quick Scan Cache
    # =========================================================================

    def get_quick_scan(self, ticker: str) -> dict | None:
        """Get cached quick scan result for a ticker."""
        key = self._make_key(self.PREFIX_QUICK_SCAN, ticker.upper())
        data = self._client.get(key)
        if data:
            return json.loads(data)
        return None

    def set_quick_scan(
        self,
        ticker: str,
        scan_result: dict,
        ttl: int | None = None,
    ) -> None:
        """Cache quick scan result for a ticker."""
        key = self._make_key(self.PREFIX_QUICK_SCAN, ticker.upper())
        self._client.setex(
            key,
            ttl or self.TTL_QUICK_SCAN,
            json.dumps(scan_result),
        )

    # =========================================================================
    # Deep Research Cache
    # =========================================================================

    def get_deep_research(self, ticker: str) -> dict | None:
        """Get cached deep research result for a ticker."""
        key = self._make_key(self.PREFIX_DEEP_RESEARCH, ticker.upper())
        data = self._client.get(key)
        if data:
            return json.loads(data)
        return None

    def set_deep_research(
        self,
        ticker: str,
        research_result: dict,
        ttl: int | None = None,
    ) -> None:
        """Cache deep research result for a ticker."""
        key = self._make_key(self.PREFIX_DEEP_RESEARCH, ticker.upper())
        self._client.setex(
            key,
            ttl or self.TTL_DEEP_RESEARCH,
            json.dumps(research_result),
        )

    # =========================================================================
    # Recommendation Cache
    # =========================================================================

    def get_recommendation(self, ticker: str) -> dict | None:
        """Get cached recommendation for a ticker."""
        key = self._make_key(self.PREFIX_RECOMMENDATION, ticker.upper())
        data = self._client.get(key)
        if data:
            return json.loads(data)
        return None

    def set_recommendation(
        self,
        ticker: str,
        recommendation: dict,
        ttl: int | None = None,
    ) -> None:
        """Cache recommendation for a ticker."""
        key = self._make_key(self.PREFIX_RECOMMENDATION, ticker.upper())
        self._client.setex(
            key,
            ttl or self.TTL_RECOMMENDATION,
            json.dumps(recommendation),
        )

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def invalidate_ticker(self, ticker: str) -> int:
        """Invalidate all cached data for a ticker."""
        ticker = ticker.upper()
        keys = [
            self._make_key(self.PREFIX_TECHNICAL, ticker),
            self._make_key(self.PREFIX_QUICK_SCAN, ticker),
            self._make_key(self.PREFIX_DEEP_RESEARCH, ticker),
            self._make_key(self.PREFIX_RECOMMENDATION, ticker),
        ]
        return self._client.delete(*keys)

    def invalidate_all(self) -> int:
        """Invalidate all cached data (use with caution)."""
        pattern = "swingbot:*"
        keys = list(self._client.scan_iter(match=pattern))
        if keys:
            return self._client.delete(*keys)
        return 0


# Singleton instance
_redis_cache: RedisCache | None = None


def get_redis_cache() -> RedisCache:
    """Get or create the singleton Redis cache instance."""
    global _redis_cache
    if _redis_cache is None:
        _redis_cache = RedisCache()
    return _redis_cache
