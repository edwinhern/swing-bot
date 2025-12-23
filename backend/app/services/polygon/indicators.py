"""Technical indicator calculations for stock analysis."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from massive.rest.aggs import Agg


def calculate_sma(bars: list["Agg"], period: int) -> float | None:
    """Calculate Simple Moving Average for a given period.

    Args:
        bars: List of Agg objects with close prices (most recent last)
        period: Number of periods for the SMA calculation

    Returns:
        SMA value or None if insufficient data
    """
    if len(bars) < period:
        return None

    # Use the most recent 'period' bars
    recent_bars = bars[-period:]
    closes = [bar.close for bar in recent_bars]
    return sum(closes) / period


def calculate_rsi(bars: list["Agg"], period: int = 14) -> float | None:
    """Calculate Relative Strength Index.

    Uses the standard RSI formula:
    RSI = 100 - (100 / (1 + RS))
    where RS = Average Gain / Average Loss over the period

    Args:
        bars: List of Agg objects with close prices (most recent last)
        period: RSI period (default 14)

    Returns:
        RSI value (0-100) or None if insufficient data
    """
    if len(bars) < period + 1:
        return None

    # Calculate price changes
    changes: list[float] = []
    for i in range(1, len(bars)):
        changes.append(bars[i].close - bars[i - 1].close)

    if len(changes) < period:
        return None

    # Use the most recent 'period' changes
    recent_changes = changes[-period:]

    gains = [change if change > 0 else 0 for change in recent_changes]
    losses = [abs(change) if change < 0 else 0 for change in recent_changes]

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    if avg_loss == 0:
        return 100.0  # No losses = maximum RSI

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    return round(rsi, 2)


def calculate_average_volume(bars: list["Agg"], period: int = 20) -> int | None:
    """Calculate average trading volume over a period.

    Args:
        bars: List of Agg objects with volume data (most recent last)
        period: Number of periods to average

    Returns:
        Average volume or None if insufficient data
    """
    if len(bars) < period:
        return None

    recent_bars = bars[-period:]
    volumes = [bar.volume for bar in recent_bars]
    return int(sum(volumes) / period)


def get_price_vs_sma_signal(price: float, sma_20: float, sma_50: float) -> str:
    """Determine price position relative to SMAs.

    Args:
        price: Current price
        sma_20: 20-day simple moving average
        sma_50: 50-day simple moving average

    Returns:
        Signal string describing the position
    """
    if price > sma_20 > sma_50:
        return "bullish_alignment"
    elif price > sma_20:
        return "above_sma20"
    elif sma_20 > sma_50:
        return "golden_cross_forming"
    elif price < sma_20 < sma_50:
        return "bearish_alignment"
    else:
        return "neutral"


def get_rsi_signal(rsi: float) -> str:
    """Interpret RSI value into a trading signal.

    Args:
        rsi: RSI value (0-100)

    Returns:
        Signal string describing the RSI condition
    """
    if rsi < 25:
        return "extremely_oversold"
    elif 25 <= rsi < 35:
        return "oversold"
    elif 35 <= rsi < 50:
        return "recovering"
    elif 50 <= rsi < 60:
        return "neutral"
    elif 60 <= rsi < 70:
        return "overbought_warning"
    else:
        return "overbought"
