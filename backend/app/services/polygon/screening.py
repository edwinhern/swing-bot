"""Technical screening and scoring logic for stock analysis."""

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

from .client import PolygonClient, get_polygon_client
from .indicators import (
    calculate_average_volume,
    calculate_rsi,
    calculate_sma,
    get_price_vs_sma_signal,
    get_rsi_signal,
)

if TYPE_CHECKING:
    from massive.rest.aggs import Agg


class TechnicalData(BaseModel):
    """Raw technical indicator data for a stock."""

    ticker: str
    price: float
    sma_20: float
    sma_50: float
    rsi: float
    avg_volume: int
    recent_volume: int
    fifty_two_week_high: float
    fifty_two_week_low: float
    percent_from_low: float = Field(description="Percentage above 52-week low")
    percent_from_high: float = Field(description="Percentage below 52-week high")


class TechnicalAnalysis(BaseModel):
    """Complete technical analysis result with scoring."""

    ticker: str
    price: float
    sma_20: float
    sma_50: float
    rsi: float
    avg_volume: int
    recent_volume: int
    fifty_two_week_high: float
    fifty_two_week_low: float
    percent_from_low: float
    percent_from_high: float
    technical_score: int = Field(ge=0, le=100, description="Technical score 0-100")
    signals: list[str] = Field(description="List of technical signals detected")
    passes_gate: bool = Field(description="Whether the stock passes the technical gate")
    rsi_interpretation: str = Field(description="Human-readable RSI interpretation")
    sma_interpretation: str = Field(description="Human-readable SMA interpretation")


def compute_technical_score(data: TechnicalData) -> int:
    """Compute a technical score based on mean reversion + momentum strategy.

    Scoring breakdown:
    - RSI Score: 0-30 points (oversold conditions favored)
    - SMA Position: 0-25 points (bullish alignment favored)
    - 52-Week Low Proximity: 0-25 points (5-15% sweet spot)
    - Volume: 0-20 points (accumulation signals)

    Args:
        data: TechnicalData object with all indicators

    Returns:
        Technical score from 0-100
    """
    score = 0

    # RSI Score (0-30 points)
    # Favor oversold but recovering conditions
    if 25 <= data.rsi <= 35:
        score += 30  # Oversold, ideal entry zone
    elif 35 < data.rsi <= 50:
        score += 20  # Recovering from oversold
    elif 50 < data.rsi <= 60:
        score += 10  # Neutral
    # RSI < 25 (freefall) or > 60 (losing momentum) = 0 points

    # SMA Position (0-25 points)
    # Favor bullish alignment and golden cross formations
    if data.price > data.sma_20 > data.sma_50:
        score += 25  # Full bullish alignment
    elif data.price > data.sma_20:
        score += 15  # Above short-term trend
    elif data.sma_20 > data.sma_50:
        score += 10  # Golden cross forming

    # 52-Week Low Proximity (0-25 points)
    # Sweet spot is 5-15% above the low (bounced but still undervalued)
    pct = data.percent_from_low
    if 5 <= pct <= 10:
        score += 25  # Ideal zone - bounced, room to grow
    elif 10 < pct <= 15:
        score += 20  # Still good entry
    elif 15 < pct <= 20:
        score += 10  # Moderate opportunity
    # < 5% (still falling) or > 20% (already recovered) = 0 points

    # Volume (0-20 points)
    # Look for accumulation signals (higher than average volume)
    if data.recent_volume > data.avg_volume * 1.2:
        score += 20  # Strong accumulation signal
    elif data.recent_volume >= data.avg_volume:
        score += 10  # Normal/healthy volume

    return min(score, 100)  # Cap at 100


def get_technical_signals(data: TechnicalData) -> list[str]:
    """Generate a list of technical signals from the data.

    Args:
        data: TechnicalData object with all indicators

    Returns:
        List of signal strings
    """
    signals: list[str] = []

    # RSI signals
    rsi_signal = get_rsi_signal(data.rsi)
    if rsi_signal in ("oversold", "extremely_oversold"):
        signals.append("oversold")
    elif rsi_signal == "recovering":
        signals.append("recovering_momentum")
    elif rsi_signal in ("overbought", "overbought_warning"):
        signals.append("overbought_warning")

    # SMA signals
    sma_signal = get_price_vs_sma_signal(data.price, data.sma_20, data.sma_50)
    if sma_signal == "bullish_alignment":
        signals.append("bullish_trend")
    elif sma_signal == "above_sma20":
        signals.append("above_sma20")
    elif sma_signal == "golden_cross_forming":
        signals.append("golden_cross_forming")
    elif sma_signal == "bearish_alignment":
        signals.append("bearish_trend")

    # 52-week low signals
    if 5 <= data.percent_from_low <= 15:
        signals.append("near_52_week_low")
    elif data.percent_from_low < 5:
        signals.append("at_52_week_low")

    # Volume signals
    if data.recent_volume > data.avg_volume * 1.2:
        signals.append("volume_spike")
    elif data.recent_volume < data.avg_volume * 0.5:
        signals.append("low_volume")

    return signals


def analyze_stock(
    ticker: str,
    gate_threshold: int = 50,
    client: PolygonClient | None = None,
) -> TechnicalAnalysis | None:
    """Perform complete technical analysis on a stock.

    Args:
        ticker: Stock ticker symbol
        gate_threshold: Minimum technical score to pass the gate (default 50)
        client: Optional PolygonClient instance

    Returns:
        TechnicalAnalysis object or None if insufficient data
    """
    if client is None:
        client = get_polygon_client()

    # Fetch daily bars for indicator calculations
    bars = client.get_daily_bars(ticker, days=365)
    if len(bars) < 50:
        return None  # Not enough data for analysis

    # Get current price from most recent bar
    current_price = bars[-1].close

    # Calculate indicators
    sma_20 = calculate_sma(bars, 20)
    sma_50 = calculate_sma(bars, 50)
    rsi = calculate_rsi(bars, 14)
    avg_volume = calculate_average_volume(bars, 20)

    if sma_20 is None or sma_50 is None or rsi is None or avg_volume is None:
        return None  # Insufficient data for calculations

    # Get recent volume (last trading day)
    recent_volume = bars[-1].volume

    # Get 52-week high/low
    high_low = client.get_52_week_high_low(ticker)
    if high_low is None:
        return None

    fifty_two_week_high, fifty_two_week_low = high_low

    # Calculate percentages
    percent_from_low = ((current_price - fifty_two_week_low) / fifty_two_week_low) * 100
    percent_from_high = ((fifty_two_week_high - current_price) / fifty_two_week_high) * 100

    # Create TechnicalData object
    tech_data = TechnicalData(
        ticker=ticker,
        price=round(current_price, 2),
        sma_20=round(sma_20, 2),
        sma_50=round(sma_50, 2),
        rsi=round(rsi, 2),
        avg_volume=avg_volume,
        recent_volume=recent_volume,
        fifty_two_week_high=round(fifty_two_week_high, 2),
        fifty_two_week_low=round(fifty_two_week_low, 2),
        percent_from_low=round(percent_from_low, 2),
        percent_from_high=round(percent_from_high, 2),
    )

    # Compute score and signals
    technical_score = compute_technical_score(tech_data)
    signals = get_technical_signals(tech_data)

    # Determine if passes gate
    passes_gate = technical_score >= gate_threshold

    return TechnicalAnalysis(
        ticker=tech_data.ticker,
        price=tech_data.price,
        sma_20=tech_data.sma_20,
        sma_50=tech_data.sma_50,
        rsi=tech_data.rsi,
        avg_volume=tech_data.avg_volume,
        recent_volume=tech_data.recent_volume,
        fifty_two_week_high=tech_data.fifty_two_week_high,
        fifty_two_week_low=tech_data.fifty_two_week_low,
        percent_from_low=tech_data.percent_from_low,
        percent_from_high=tech_data.percent_from_high,
        technical_score=technical_score,
        signals=signals,
        passes_gate=passes_gate,
        rsi_interpretation=get_rsi_signal(tech_data.rsi),
        sma_interpretation=get_price_vs_sma_signal(tech_data.price, tech_data.sma_20, tech_data.sma_50),
    )
