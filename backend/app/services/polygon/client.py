"""Polygon.io API client for fetching stock market data."""

import os
from datetime import datetime, timedelta
from typing import Any

from massive import RESTClient


class PolygonClient:
    """Client for interacting with Polygon.io API."""

    def __init__(self, api_key: str | None = None) -> None:
        """Initialize the Polygon client.

        Args:
            api_key: Polygon.io API key. If not provided, uses MASSIVE_API_KEY env var.
        """
        self._api_key = api_key or os.getenv("MASSIVE_API_KEY")
        if not self._api_key:
            raise ValueError("Polygon API key is required. Set MASSIVE_API_KEY env var or pass api_key.")
        self._client = RESTClient(api_key=self._api_key)

    def get_daily_bars(
        self,
        ticker: str,
        days: int = 365,
        limit: int = 5000,
    ) -> list[Any]:
        """Fetch daily price bars for a ticker.

        Args:
            ticker: Stock ticker symbol (e.g., "AAPL")
            days: Number of days of historical data to fetch
            limit: Maximum number of bars to return

        Returns:
            List of Agg objects containing OHLCV data
        """
        bars = self._client.list_aggs(
            ticker,
            multiplier=1,
            timespan="day",
            from_=datetime.now() - timedelta(days=days),
            to=datetime.now(),
            limit=limit,
        )
        return list(bars)

    def get_minute_bars(
        self,
        ticker: str,
        days: int = 7,
        limit: int = 5000,
    ) -> list[Any]:
        """Fetch minute-level price bars for a ticker.

        Args:
            ticker: Stock ticker symbol (e.g., "AAPL")
            days: Number of days of historical data to fetch
            limit: Maximum number of bars to return

        Returns:
            List of Agg objects containing OHLCV data
        """
        bars = self._client.list_aggs(
            ticker,
            multiplier=1,
            timespan="minute",
            from_=datetime.now() - timedelta(days=days),
            to=datetime.now(),
            limit=limit,
        )
        return list(bars)

    def get_previous_close(self, ticker: str) -> Any | None:
        """Get the previous day's close for a ticker.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Agg object with previous close data, or None if not available
        """
        bars = self.get_daily_bars(ticker, days=5, limit=2)
        return bars[-1] if bars else None

    def get_52_week_high_low(self, ticker: str) -> tuple[float, float] | None:
        """Get the 52-week high and low for a ticker.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Tuple of (52_week_high, 52_week_low) or None if insufficient data
        """
        bars = self.get_daily_bars(ticker, days=365, limit=260)
        if len(bars) < 20:  # Need at least some data
            return None

        highs = [bar.high for bar in bars]
        lows = [bar.low for bar in bars]
        return max(highs), min(lows)


# Singleton instance
_polygon_client: PolygonClient | None = None


def get_polygon_client() -> PolygonClient:
    """Get or create the singleton Polygon client instance."""
    global _polygon_client
    if _polygon_client is None:
        _polygon_client = PolygonClient()
    return _polygon_client
