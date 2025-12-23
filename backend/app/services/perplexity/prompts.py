"""Prompt templates for each stage of the stock research pipeline."""

from dataclasses import dataclass


@dataclass
class PromptTemplates:
    """Collection of prompt templates for each pipeline stage.

    All templates use format string syntax for variable injection.
    """

    # =========================================================================
    # Stage 2: Quick Sentiment Scan
    # =========================================================================

    QUICK_SCAN_SYSTEM = """You are a financial risk analyst performing a quick assessment of stocks.
Your job is to identify any critical issues that would make a stock dangerous to invest in.
Be concise and accurate. Only flag genuine critical issues, not normal market volatility."""

    QUICK_SCAN_PROMPT = """Perform a quick risk assessment for {ticker} ({company_name}).

Check for any of these CRITICAL issues:
1. Bankruptcy risk or severe financial distress
2. Fraud investigations or SEC enforcement actions
3. Major lawsuits with material financial impact
4. Executive scandals (CEO/CFO resignation under investigation)
5. Product failures or recalls with significant liability
6. Delisting warnings or going concern notices

If issues are found, classify as:
- "temporary": Earnings miss, supply chain issues, one-time events
- "structural": Fundamental business problems, loss of competitive position, sustained decline

Respond with ONLY the structured JSON matching the schema. No explanation text."""

    # =========================================================================
    # Stage 3: Deep Research
    # =========================================================================

    DEEP_RESEARCH_SYSTEM = """You are a senior equity research analyst specializing in swing trading opportunities.
You combine technical analysis data with fundamental research and social sentiment to identify
undervalued stocks with recovery potential. Always provide citations for your claims."""

    DEEP_RESEARCH_PROMPT = """Analyze {ticker} ({company_name}) for swing trading potential.

TECHNICAL CONTEXT (from real market data):
- Current Price: ${price} | 52-Week Low: ${fifty_two_week_low} | {percent_from_low}% above low
- RSI: {rsi} ({rsi_interpretation})
- SMA-20: ${sma_20} | SMA-50: ${sma_50} | Signal: {sma_interpretation}
- Technical Score: {technical_score}/100
- Detected Signals: {signals}

RESEARCH TASKS:

1. NEWS CATALYSTS
   - What recent events explain the price decline?
   - Is it temporary (earnings miss, supply chain) or structural (loss of competitive advantage)?
   - Any upcoming catalysts (earnings, product launches, FDA approvals)?

2. SOCIAL SENTIMENT
   Check these sources and find additional credible voices:
   - Twitter: @unusual_whales, @stockmarketnews, @DeItaone, @zaborstock
   - Reddit: r/stocks, r/investing, r/wallstreetbets, r/options
   - Look for: sentiment trends, trending discussions, notable influencer opinions

3. ROOT CAUSE ANALYSIS
   - Is this decline company-specific or affecting the entire sector?
   - Is the core business demand still intact?
   - What is the company's competitive moat (strong/moderate/weak)?
   - Are insiders buying, selling, or neutral?

4. RECOVERY POTENTIAL
   Given the technical signals showing {technical_summary}, assess:
   - Likelihood of recovery in 1-3 months
   - Key factors that would accelerate or delay recovery

Provide specific citations (URLs) for all factual claims."""

    # =========================================================================
    # Stage 4: Final Scoring
    # =========================================================================

    SCORING_SYSTEM = """You are a quantitative portfolio analyst synthesizing multiple data sources
into actionable investment recommendations. You balance technical analysis with fundamental
research and assign precise numerical scores based on evidence."""

    SCORING_PROMPT = """Generate a final investment recommendation for {ticker} ({company_name}).

=== TECHNICAL DATA (from Polygon.io) ===
{technical_data_json}

=== RESEARCH DATA (from Deep Analysis) ===
{deep_research_json}

=== SCORING METHODOLOGY ===

1. TECHNICAL SCORE (already calculated): {technical_score}/100
   - Based on RSI, SMA positions, 52-week low proximity, volume

2. SENTIMENT SCORE (from research): {sentiment_score}/100
   - Based on news sentiment, social media, recovery likelihood

3. FUNDAMENTAL SCORE (assess now): 0-100
   - Consider: competitive moat, demand intact, insider activity, sector position
   - Strong moat + demand intact + insider buying = 80-100
   - Moderate moat + demand intact = 60-79
   - Weak moat or demand concerns = 40-59
   - Structural problems = 0-39

4. COMPOSITE SCORE (weighted average):
   - Technical: 40% weight
   - Sentiment: 35% weight
   - Fundamental: 25% weight

=== RECOMMENDATION THRESHOLDS ===
- strong_buy: composite >= 75, no structural issues
- buy: composite >= 60, decline is temporary
- hold: composite >= 45 or mixed signals
- avoid: composite < 45 or structural issues

=== PRICE TARGETS ===
Calculate based on:
- Target: If technical + sentiment bullish, estimate recovery to SMA-50 or higher
- Stop-loss: Set 5-8% below current price or below recent support

Provide the complete structured JSON response with all fields."""

    # =========================================================================
    # Helper methods for prompt formatting
    # =========================================================================

    @staticmethod
    def format_quick_scan(ticker: str, company_name: str) -> str:
        """Format the quick scan prompt with stock details."""
        return PromptTemplates.QUICK_SCAN_PROMPT.format(
            ticker=ticker,
            company_name=company_name,
        )

    @staticmethod
    def format_deep_research(
        ticker: str,
        company_name: str,
        price: float,
        fifty_two_week_low: float,
        percent_from_low: float,
        rsi: float,
        rsi_interpretation: str,
        sma_20: float,
        sma_50: float,
        sma_interpretation: str,
        technical_score: int,
        signals: list[str],
    ) -> str:
        """Format the deep research prompt with technical context."""
        signals_str = ", ".join(signals) if signals else "none detected"

        # Build technical summary
        if technical_score >= 70:
            technical_summary = "strong bullish signals"
        elif technical_score >= 50:
            technical_summary = "moderately bullish signals"
        elif technical_score >= 30:
            technical_summary = "mixed signals"
        else:
            technical_summary = "bearish signals"

        return PromptTemplates.DEEP_RESEARCH_PROMPT.format(
            ticker=ticker,
            company_name=company_name,
            price=price,
            fifty_two_week_low=fifty_two_week_low,
            percent_from_low=percent_from_low,
            rsi=rsi,
            rsi_interpretation=rsi_interpretation,
            sma_20=sma_20,
            sma_50=sma_50,
            sma_interpretation=sma_interpretation,
            technical_score=technical_score,
            signals=signals_str,
            technical_summary=technical_summary,
        )

    @staticmethod
    def format_scoring(
        ticker: str,
        company_name: str,
        technical_data_json: str,
        deep_research_json: str,
        technical_score: int,
        sentiment_score: int,
    ) -> str:
        """Format the final scoring prompt with all data."""
        return PromptTemplates.SCORING_PROMPT.format(
            ticker=ticker,
            company_name=company_name,
            technical_data_json=technical_data_json,
            deep_research_json=deep_research_json,
            technical_score=technical_score,
            sentiment_score=sentiment_score,
        )
