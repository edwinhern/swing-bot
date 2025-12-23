"""Pydantic models for Perplexity API responses at each pipeline stage."""

from typing import Literal

from pydantic import BaseModel, Field


# =============================================================================
# Stage 0: Discovery - Stock candidates near 52-week lows
# =============================================================================


class StockCandidate(BaseModel):
    """A stock candidate identified as being near its 52-week low."""

    ticker: str = Field(description="Stock ticker symbol (e.g., AAPL)")
    company_name: str = Field(description="Full company name")
    sector: str = Field(description="Industry sector (e.g., Technology, Healthcare)")
    current_price: float = Field(description="Current stock price in USD")
    fifty_two_week_low: float = Field(description="52-week low price in USD")
    fifty_two_week_high: float = Field(description="52-week high price in USD")
    percent_from_low: float = Field(description="Percentage above 52-week low")
    market_cap: float | None = Field(default=None, description="Market capitalization in USD")


class StockDiscoveryResult(BaseModel):
    """Result of the stock discovery stage."""

    stocks: list[StockCandidate] = Field(description="List of stock candidates found")
    search_date: str = Field(description="Date of the search")
    total_found: int = Field(description="Total number of stocks found matching criteria")


# =============================================================================
# Stage 2: Quick Sentiment Scan - Fast fail check for critical issues
# =============================================================================


class QuickSentimentScan(BaseModel):
    """Result of a quick sentiment scan for critical issues."""

    ticker: str = Field(description="Stock ticker symbol")
    has_critical_issues: bool = Field(description="Whether critical issues were found")
    issue_type: Literal["none", "temporary", "structural"] = Field(
        default="none",
        description="Type of issue: none, temporary (earnings miss), or structural (fundamental problems)",
    )
    issue_summary: str | None = Field(
        default=None,
        description="Brief summary of the critical issue if found",
    )
    risk_level: Literal["low", "medium", "high", "critical"] = Field(
        default="low",
        description="Overall risk level based on findings",
    )
    passes_gate: bool = Field(description="Whether the stock passes the quick scan gate")


# =============================================================================
# Stage 3: Deep Research - Comprehensive analysis
# =============================================================================


class SocialSentiment(BaseModel):
    """Social media sentiment analysis result."""

    platform: Literal["twitter", "reddit"] = Field(description="Social media platform")
    sentiment: Literal["bullish", "neutral", "bearish"] = Field(description="Overall sentiment")
    trending_topics: list[str] = Field(default_factory=list, description="Trending topics/discussions")
    notable_mentions: list[str] = Field(
        default_factory=list,
        description="Notable mentions from credible sources",
    )
    engagement_level: Literal["low", "medium", "high"] = Field(
        default="medium",
        description="Level of engagement/discussion volume",
    )


class DeepResearchResult(BaseModel):
    """Result of deep research analysis on a stock."""

    ticker: str = Field(description="Stock ticker symbol")

    # News Analysis
    decline_reason: str = Field(description="Primary reason for the stock's price decline")
    decline_type: Literal["temporary", "structural", "mixed"] = Field(description="Classification of the decline cause")
    key_events: list[str] = Field(description="Key events that contributed to the decline")

    # Social Sentiment
    twitter_sentiment: Literal["bullish", "neutral", "bearish"] = Field(description="Overall Twitter sentiment")
    reddit_sentiment: Literal["bullish", "neutral", "bearish"] = Field(description="Overall Reddit sentiment")
    trending_topics: list[str] = Field(description="Trending topics related to the stock")
    notable_mentions: list[str] = Field(description="Notable mentions from influencers or credible sources")

    # Root Cause Analysis
    is_sector_wide: bool = Field(description="Whether the decline is affecting the entire sector")
    demand_intact: bool = Field(description="Whether core business demand remains strong")
    competitive_moat: Literal["strong", "moderate", "weak"] = Field(
        description="Strength of the company's competitive advantage"
    )
    insider_activity: Literal["buying", "neutral", "selling"] | None = Field(
        default=None,
        description="Recent insider trading activity",
    )

    # Assessment
    recovery_likelihood: Literal["high", "medium", "low"] = Field(
        description="Likelihood of price recovery in 1-3 months"
    )
    sentiment_score: int = Field(ge=0, le=100, description="Overall sentiment score 0-100")

    # Sources
    citations: list[str] = Field(description="URLs or references for the research findings")


# =============================================================================
# Stage 4: Final Scoring - Investment recommendation
# =============================================================================


class FinalRecommendation(BaseModel):
    """Final investment recommendation combining all analysis."""

    ticker: str = Field(description="Stock ticker symbol")
    company_name: str = Field(description="Full company name")

    # Scores
    technical_score: int = Field(ge=0, le=100, description="Technical analysis score from Polygon data")
    sentiment_score: int = Field(ge=0, le=100, description="Sentiment score from deep research")
    fundamental_score: int = Field(ge=0, le=100, description="Fundamental assessment score")
    composite_score: int = Field(ge=0, le=100, description="Weighted composite score")

    # Recommendation
    recommendation: Literal["strong_buy", "buy", "hold", "avoid"] = Field(description="Final investment recommendation")
    confidence: Literal["high", "medium", "low"] = Field(description="Confidence level in the recommendation")

    # Targets
    current_price: float = Field(description="Current stock price")
    target_price: float = Field(description="Estimated target price")
    upside_percent: float = Field(description="Potential upside percentage")
    stop_loss: float = Field(description="Recommended stop-loss price")

    # Timeline
    timeline: Literal["1-2_weeks", "1_month", "3_months"] = Field(description="Expected timeline for the target")

    # Catalysts & Risks
    key_catalysts: list[str] = Field(description="Potential catalysts for price movement")
    risk_factors: list[str] = Field(description="Key risk factors to monitor")

    # Reasoning
    bull_case: str = Field(description="Summary of the bull case")
    bear_case: str = Field(description="Summary of the bear case")

    # Sources
    citations: list[str] = Field(description="URLs or references supporting the recommendation")


# =============================================================================
# Pipeline Result - Complete analysis output
# =============================================================================


class PipelineResult(BaseModel):
    """Complete result from the full research pipeline."""

    ticker: str = Field(description="Stock ticker symbol")
    company_name: str = Field(description="Full company name")

    # Stage results
    technical_analysis: dict = Field(description="Technical analysis from Polygon")
    quick_scan: QuickSentimentScan = Field(description="Quick sentiment scan result")
    deep_research: DeepResearchResult = Field(description="Deep research result")
    recommendation: FinalRecommendation = Field(description="Final recommendation")

    # Pipeline metadata
    stages_completed: list[str] = Field(description="List of completed stages")
    total_cost_estimate: float = Field(description="Estimated API cost for this analysis")
    analysis_timestamp: str = Field(description="Timestamp of the analysis")
