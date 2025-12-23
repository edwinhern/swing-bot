"""Gate/threshold logic for each stage of the research pipeline.

Gates act as quality filters to prevent expensive research on poor candidates.
This implements the "Polygon First, Perplexity Smart" cost optimization strategy.
"""

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field


@dataclass
class GateConfig:
    """Configuration for pipeline gates.

    All thresholds can be customized to adjust the aggressiveness
    of filtering at each stage.
    """

    # Stage 0: Discovery Gate
    min_percent_from_low: float = 5.0  # Exclude stocks still falling (< 5%)
    max_percent_from_low: float = 20.0  # Exclude already recovered (> 20%)

    # Stage 1: Technical Gate
    min_technical_score: int = 50  # Minimum technical score to proceed

    # Stage 2: Quick Scan Gate
    allow_temporary_issues: bool = True  # Allow stocks with temporary issues
    block_structural_issues: bool = True  # Block stocks with structural problems

    # Stage 3: Deep Research Gate (optional pre-scoring filter)
    min_sentiment_score: int = 40  # Minimum sentiment to proceed to scoring

    # Additional filters
    min_market_cap: float | None = None  # Minimum market cap (optional)
    required_sectors: list[str] = field(default_factory=list)  # Limit to specific sectors
    excluded_sectors: list[str] = field(default_factory=list)  # Exclude specific sectors


class GateResult(BaseModel):
    """Result of a gate check."""

    passed: bool = Field(description="Whether the stock passed the gate")
    gate_name: str = Field(description="Name of the gate")
    reason: str = Field(description="Reason for pass/fail")
    score: float | None = Field(default=None, description="Score used for gate decision")
    threshold: float | None = Field(default=None, description="Threshold applied")


def check_discovery_gate(
    percent_from_low: float,
    config: GateConfig | None = None,
    market_cap: float | None = None,
    sector: str | None = None,
) -> GateResult:
    """Check if a stock passes the discovery gate (Stage 0).

    This gate filters stocks based on their proximity to 52-week lows.
    The sweet spot is 5-20% above the low - bounced but still undervalued.

    Args:
        percent_from_low: Percentage above 52-week low
        config: Gate configuration (uses defaults if None)
        market_cap: Optional market cap for filtering
        sector: Optional sector for filtering

    Returns:
        GateResult indicating pass/fail and reason
    """
    if config is None:
        config = GateConfig()

    # Check 52-week low proximity
    if percent_from_low < config.min_percent_from_low:
        return GateResult(
            passed=False,
            gate_name="discovery",
            reason=f"Too close to 52-week low ({percent_from_low:.1f}% < {config.min_percent_from_low}%), may still be falling",
            score=percent_from_low,
            threshold=config.min_percent_from_low,
        )

    if percent_from_low > config.max_percent_from_low:
        return GateResult(
            passed=False,
            gate_name="discovery",
            reason=f"Already recovered ({percent_from_low:.1f}% > {config.max_percent_from_low}%), missed the entry",
            score=percent_from_low,
            threshold=config.max_percent_from_low,
        )

    # Check market cap if configured
    if config.min_market_cap is not None and market_cap is not None and market_cap < config.min_market_cap:
        return GateResult(
            passed=False,
            gate_name="discovery",
            reason=f"Market cap too small (${market_cap:,.0f} < ${config.min_market_cap:,.0f})",
            score=market_cap,
            threshold=config.min_market_cap,
        )

    # Check sector filters
    if sector:
        if config.excluded_sectors and sector.lower() in [s.lower() for s in config.excluded_sectors]:
            return GateResult(
                passed=False,
                gate_name="discovery",
                reason=f"Sector '{sector}' is excluded",
            )

        if config.required_sectors and sector.lower() not in [s.lower() for s in config.required_sectors]:
            return GateResult(
                passed=False,
                gate_name="discovery",
                reason=f"Sector '{sector}' not in required sectors",
            )

    return GateResult(
        passed=True,
        gate_name="discovery",
        reason=f"Stock is {percent_from_low:.1f}% above 52-week low (ideal range)",
        score=percent_from_low,
    )


def check_technical_gate(
    technical_score: int,
    config: GateConfig | None = None,
) -> GateResult:
    """Check if a stock passes the technical gate (Stage 1).

    This gate filters stocks based on technical analysis score
    computed from RSI, SMA positions, volume, and proximity to lows.

    Args:
        technical_score: Technical score from 0-100
        config: Gate configuration (uses defaults if None)

    Returns:
        GateResult indicating pass/fail and reason
    """
    if config is None:
        config = GateConfig()

    if technical_score < config.min_technical_score:
        return GateResult(
            passed=False,
            gate_name="technical",
            reason=f"Technical score too low ({technical_score} < {config.min_technical_score})",
            score=float(technical_score),
            threshold=float(config.min_technical_score),
        )

    # Provide context on the score quality
    if technical_score >= 75:
        quality = "excellent"
    elif technical_score >= 60:
        quality = "good"
    else:
        quality = "acceptable"

    return GateResult(
        passed=True,
        gate_name="technical",
        reason=f"Technical score is {quality} ({technical_score}/100)",
        score=float(technical_score),
        threshold=float(config.min_technical_score),
    )


def check_quick_scan_gate(
    has_critical_issues: bool,
    issue_type: Literal["none", "temporary", "structural"],
    config: GateConfig | None = None,
) -> GateResult:
    """Check if a stock passes the quick scan gate (Stage 2).

    This gate filters stocks based on a quick sentiment scan for
    catastrophic issues before expensive deep research.

    Args:
        has_critical_issues: Whether critical issues were found
        issue_type: Type of issue (none, temporary, structural)
        config: Gate configuration (uses defaults if None)

    Returns:
        GateResult indicating pass/fail and reason
    """
    if config is None:
        config = GateConfig()

    if not has_critical_issues:
        return GateResult(
            passed=True,
            gate_name="quick_scan",
            reason="No critical issues detected",
        )

    if issue_type == "structural" and config.block_structural_issues:
        return GateResult(
            passed=False,
            gate_name="quick_scan",
            reason="Structural issues detected - fundamental business problems",
        )

    if issue_type == "temporary":
        if config.allow_temporary_issues:
            return GateResult(
                passed=True,
                gate_name="quick_scan",
                reason="Temporary issues detected but allowed - proceed with caution",
            )
        return GateResult(
            passed=False,
            gate_name="quick_scan",
            reason="Temporary issues detected - config set to block",
        )

    return GateResult(
        passed=True,
        gate_name="quick_scan",
        reason="Issues detected but not classified as blocking",
    )


def check_sentiment_gate(
    sentiment_score: int,
    config: GateConfig | None = None,
) -> GateResult:
    """Check if a stock passes the sentiment gate (optional pre-Stage 4).

    This optional gate can filter stocks after deep research but before
    final scoring to save on reasoning model costs.

    Args:
        sentiment_score: Sentiment score from deep research (0-100)
        config: Gate configuration (uses defaults if None)

    Returns:
        GateResult indicating pass/fail and reason
    """
    if config is None:
        config = GateConfig()

    if sentiment_score < config.min_sentiment_score:
        return GateResult(
            passed=False,
            gate_name="sentiment",
            reason=f"Sentiment score too low ({sentiment_score} < {config.min_sentiment_score})",
            score=float(sentiment_score),
            threshold=float(config.min_sentiment_score),
        )

    return GateResult(
        passed=True,
        gate_name="sentiment",
        reason=f"Sentiment score acceptable ({sentiment_score}/100)",
        score=float(sentiment_score),
        threshold=float(config.min_sentiment_score),
    )
