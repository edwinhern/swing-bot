"""Main pipeline orchestrator for stock research.

Implements the "Polygon First, Perplexity Smart" strategy:
1. Use FREE Polygon data to filter candidates
2. Apply gates to reduce API costs
3. Only spend on Perplexity for pre-qualified stocks
"""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from ..perplexity import PerplexityClient, get_perplexity_client
from ..perplexity.models import DeepResearchResult, FinalRecommendation, PipelineResult, QuickSentimentScan
from ..perplexity.prompts import PromptTemplates
from ..polygon import PolygonClient, TechnicalAnalysis, get_polygon_client
from ..polygon.screening import analyze_stock
from .gates import GateConfig, GateResult, check_discovery_gate, check_quick_scan_gate, check_technical_gate


@dataclass
class StageResult:
    """Result from a pipeline stage."""

    stage: str
    passed: bool
    data: dict | None = None
    error: str | None = None
    cost_estimate: float = 0.0


class ResearchPipeline:
    """Orchestrates the multi-stage stock research pipeline.

    Flow:
    Stage 0: Discovery (Polygon) - Find stocks near 52-week lows
    Stage 1: Technical Screening (Polygon) - Compute technical score
    Stage 2: Quick Scan (Perplexity sonar) - Check for critical issues
    Stage 3: Deep Research (Perplexity sonar-pro) - Comprehensive analysis
    Stage 4: Final Scoring (Perplexity sonar-reasoning) - Generate recommendation
    """

    def __init__(
        self,
        polygon_client: PolygonClient | None = None,
        perplexity_client: PerplexityClient | None = None,
        gate_config: GateConfig | None = None,
    ) -> None:
        """Initialize the research pipeline.

        Args:
            polygon_client: Polygon client instance (uses singleton if None)
            perplexity_client: Perplexity client instance (uses singleton if None)
            gate_config: Gate configuration (uses defaults if None)
        """
        self._polygon = polygon_client or get_polygon_client()
        self._perplexity = perplexity_client or get_perplexity_client()
        self._config = gate_config or GateConfig()
        self._prompts = PromptTemplates()

    # =========================================================================
    # Stage 0 & 1: Technical Analysis (FREE - Polygon)
    # =========================================================================

    def run_technical_analysis(
        self,
        ticker: str,
        company_name: str | None = None,
    ) -> tuple[TechnicalAnalysis | None, list[GateResult]]:
        """Run Stages 0 and 1: Discovery and Technical Screening.

        This uses only Polygon data (FREE) to compute technical indicators
        and filter candidates before expensive Perplexity research.

        Args:
            ticker: Stock ticker symbol
            company_name: Optional company name for context

        Returns:
            Tuple of (TechnicalAnalysis or None, list of GateResults)
        """
        gates: list[GateResult] = []

        # Analyze stock using Polygon data
        analysis = analyze_stock(
            ticker=ticker,
            gate_threshold=self._config.min_technical_score,
            client=self._polygon,
        )

        if analysis is None:
            gates.append(
                GateResult(
                    passed=False,
                    gate_name="data_availability",
                    reason="Insufficient data from Polygon for analysis",
                )
            )
            return None, gates

        # Stage 0: Discovery Gate - Check 52-week low proximity
        discovery_gate = check_discovery_gate(
            percent_from_low=analysis.percent_from_low,
            config=self._config,
        )
        gates.append(discovery_gate)

        if not discovery_gate.passed:
            return analysis, gates

        # Stage 1: Technical Gate - Check technical score
        technical_gate = check_technical_gate(
            technical_score=analysis.technical_score,
            config=self._config,
        )
        gates.append(technical_gate)

        return analysis, gates

    # =========================================================================
    # Stage 2: Quick Sentiment Scan (CHEAP - Perplexity sonar)
    # =========================================================================

    async def run_quick_scan(
        self,
        ticker: str,
        company_name: str,
    ) -> tuple[QuickSentimentScan, GateResult]:
        """Run Stage 2: Quick Sentiment Scan.

        This uses Perplexity's cheapest model (sonar) to quickly check
        for catastrophic issues before expensive deep research.

        Args:
            ticker: Stock ticker symbol
            company_name: Company name for context

        Returns:
            Tuple of (QuickSentimentScan result, GateResult)
        """
        prompt = self._prompts.format_quick_scan(
            ticker=ticker,
            company_name=company_name,
        )

        scan_result = await self._perplexity.achat_structured(
            prompt=prompt,
            response_model=QuickSentimentScan,
            model="sonar",  # Cheapest model
            system_message=self._prompts.QUICK_SCAN_SYSTEM,
            temperature=0.1,
            max_tokens=512,
        )

        # Check gate
        gate_result = check_quick_scan_gate(
            has_critical_issues=scan_result.has_critical_issues,
            issue_type=scan_result.issue_type,
            config=self._config,
        )

        # Update passes_gate based on gate result
        scan_result.passes_gate = gate_result.passed

        return scan_result, gate_result

    # =========================================================================
    # Stage 3: Deep Research (TARGETED - Perplexity sonar-pro)
    # =========================================================================

    async def run_deep_research(
        self,
        ticker: str,
        company_name: str,
        technical_analysis: TechnicalAnalysis,
    ) -> DeepResearchResult:
        """Run Stage 3: Deep Research.

        This uses Perplexity's sonar-pro model for comprehensive analysis,
        with technical context from Polygon injected into the prompt.

        Args:
            ticker: Stock ticker symbol
            company_name: Company name for context
            technical_analysis: Technical analysis from Stage 1

        Returns:
            DeepResearchResult with comprehensive analysis
        """
        prompt = self._prompts.format_deep_research(
            ticker=ticker,
            company_name=company_name,
            price=technical_analysis.price,
            fifty_two_week_low=technical_analysis.fifty_two_week_low,
            percent_from_low=technical_analysis.percent_from_low,
            rsi=technical_analysis.rsi,
            rsi_interpretation=technical_analysis.rsi_interpretation,
            sma_20=technical_analysis.sma_20,
            sma_50=technical_analysis.sma_50,
            sma_interpretation=technical_analysis.sma_interpretation,
            technical_score=technical_analysis.technical_score,
            signals=technical_analysis.signals,
        )

        return await self._perplexity.achat_structured(
            prompt=prompt,
            response_model=DeepResearchResult,
            model="sonar-pro",  # Complex research model
            system_message=self._prompts.DEEP_RESEARCH_SYSTEM,
            temperature=0.2,
            max_tokens=2048,
        )

    # =========================================================================
    # Stage 4: Final Scoring (Perplexity sonar-reasoning)
    # =========================================================================

    async def run_final_scoring(
        self,
        ticker: str,
        company_name: str,
        technical_analysis: TechnicalAnalysis,
        deep_research: DeepResearchResult,
    ) -> FinalRecommendation:
        """Run Stage 4: Final Scoring.

        This uses Perplexity's sonar-reasoning model to synthesize all data
        into a final investment recommendation.

        Args:
            ticker: Stock ticker symbol
            company_name: Company name for context
            technical_analysis: Technical analysis from Stage 1
            deep_research: Deep research from Stage 3

        Returns:
            FinalRecommendation with investment advice
        """
        # Convert to JSON for prompt
        technical_json = technical_analysis.model_dump_json(indent=2)
        research_json = deep_research.model_dump_json(indent=2)

        prompt = self._prompts.format_scoring(
            ticker=ticker,
            company_name=company_name,
            technical_data_json=technical_json,
            deep_research_json=research_json,
            technical_score=technical_analysis.technical_score,
            sentiment_score=deep_research.sentiment_score,
        )

        return await self._perplexity.achat_structured(
            prompt=prompt,
            response_model=FinalRecommendation,
            model="sonar-reasoning",  # Reasoning model for synthesis
            system_message=self._prompts.SCORING_SYSTEM,
            temperature=0.1,
            max_tokens=2048,
        )

    # =========================================================================
    # Full Pipeline Execution
    # =========================================================================

    async def run_full_analysis(
        self,
        ticker: str,
        company_name: str,
    ) -> PipelineResult | None:
        """Run the complete research pipeline for a single stock.

        This orchestrates all stages with gate checks to optimize costs.
        Stages are skipped if previous gates fail.

        Args:
            ticker: Stock ticker symbol
            company_name: Company name for context

        Returns:
            PipelineResult with complete analysis, or None if all gates fail
        """
        stages_completed: list[str] = []
        total_cost = 0.0

        # Stage 0 & 1: Technical Analysis (FREE)
        technical_analysis, tech_gates = self.run_technical_analysis(ticker, company_name)

        if technical_analysis is None:
            return None

        stages_completed.append("technical_analysis")

        # Check if any technical gates failed
        if not all(gate.passed for gate in tech_gates):
            # Return early - stock didn't pass technical gates
            return None

        # Stage 2: Quick Scan (CHEAP - ~$0.001)
        quick_scan, scan_gate = await self.run_quick_scan(ticker, company_name)
        stages_completed.append("quick_scan")
        total_cost += 0.001

        if not scan_gate.passed:
            # Return early - critical issues found
            return None

        # Stage 3: Deep Research (TARGETED - ~$0.02)
        deep_research = await self.run_deep_research(ticker, company_name, technical_analysis)
        stages_completed.append("deep_research")
        total_cost += 0.02

        # Stage 4: Final Scoring (~$0.01)
        recommendation = await self.run_final_scoring(ticker, company_name, technical_analysis, deep_research)
        stages_completed.append("final_scoring")
        total_cost += 0.01

        return PipelineResult(
            ticker=ticker,
            company_name=company_name,
            technical_analysis=technical_analysis.model_dump(),
            quick_scan=quick_scan,
            deep_research=deep_research,
            recommendation=recommendation,
            stages_completed=stages_completed,
            total_cost_estimate=total_cost,
            analysis_timestamp=datetime.now().isoformat(),
        )


# =============================================================================
# Convenience Functions
# =============================================================================


async def run_single_stock_analysis(
    ticker: str,
    company_name: str,
    gate_config: GateConfig | None = None,
) -> PipelineResult | None:
    """Run the full research pipeline for a single stock.

    Convenience function that creates a pipeline and runs analysis.

    Args:
        ticker: Stock ticker symbol
        company_name: Company name for context
        gate_config: Optional gate configuration

    Returns:
        PipelineResult with complete analysis, or None if gates fail
    """
    pipeline = ResearchPipeline(gate_config=gate_config)
    return await pipeline.run_full_analysis(ticker, company_name)


async def run_full_pipeline(
    tickers: list[tuple[str, str]],
    gate_config: GateConfig | None = None,
    max_results: int = 5,
) -> list[PipelineResult]:
    """Run the research pipeline for multiple stocks.

    Processes stocks sequentially with gate filtering to optimize costs.

    Args:
        tickers: List of (ticker, company_name) tuples
        gate_config: Optional gate configuration
        max_results: Maximum number of passing results to return

    Returns:
        List of PipelineResults for stocks that passed all gates
    """
    pipeline = ResearchPipeline(gate_config=gate_config)
    results: list[PipelineResult] = []

    for ticker, company_name in tickers:
        if len(results) >= max_results:
            break

        result = await pipeline.run_full_analysis(ticker, company_name)
        if result is not None:
            results.append(result)

    return results
