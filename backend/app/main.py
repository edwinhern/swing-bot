"""SwingBot API - Stock Research Pipeline.

This module provides both:
1. FastAPI endpoints for API access
2. CLI runner for direct pipeline execution

Usage:
    API Server:  uv run uvicorn app.main:app --reload
    CLI Runner:  uv run python -m app.main --ticker AAPL
    Full Scan:   uv run python -m app.main --scan --limit 10
"""

import argparse
import asyncio
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Load environment variables
env_path = Path(__file__).parent.parent / ".env"
if not env_path.exists():
    env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)

from app.api.routes import router as api_router
from app.data.sp500 import get_sp500_companies
from app.services.polygon.screening import analyze_stock
from app.services.research.gates import GateConfig, check_discovery_gate
from app.services.research.pipeline import ResearchPipeline


# =============================================================================
# FastAPI Application
# =============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler for startup/shutdown."""
    # Startup
    print("🚀 SwingBot API starting up...")

    # Pre-load S&P 500 data
    companies = get_sp500_companies()
    print(f"📊 Loaded {len(companies)} S&P 500 companies")

    yield

    # Shutdown
    print("👋 SwingBot API shutting down...")


app = FastAPI(
    title="SwingBot API",
    description="Stock research pipeline for swing trading analysis",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router)


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint."""
    return {
        "service": "SwingBot API",
        "version": "0.1.0",
        "docs": "/docs",
    }


# =============================================================================
# CLI Runner
# =============================================================================


def run_cli() -> None:
    """Run the pipeline from command line."""
    parser = argparse.ArgumentParser(
        description="SwingBot Stock Research Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Analyze single stock:   python -m app.main --ticker AAPL
  With full pipeline:     python -m app.main --ticker AAPL --full
  Scan S&P 500:          python -m app.main --scan --limit 20
  Filter by sector:       python -m app.main --scan --sector Technology
        """,
    )

    parser.add_argument(
        "--ticker",
        type=str,
        help="Analyze a single stock ticker",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run full pipeline including Perplexity (costs money)",
    )
    parser.add_argument(
        "--scan",
        action="store_true",
        help="Scan S&P 500 for opportunities",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum stocks to analyze (default: 10)",
    )
    parser.add_argument(
        "--sector",
        type=str,
        help="Filter by sector (e.g., 'Technology')",
    )
    parser.add_argument(
        "--min-score",
        type=int,
        default=50,
        help="Minimum technical score (default: 50)",
    )

    args = parser.parse_args()

    if args.ticker:
        asyncio.run(analyze_single(args.ticker, args.full))
    elif args.scan:
        run_scan(args.limit, args.sector, args.min_score)
    else:
        parser.print_help()


async def analyze_single(ticker: str, full_pipeline: bool = False) -> None:
    """Analyze a single stock from CLI."""
    ticker = ticker.upper()
    print(f"\n{'=' * 60}")
    print(f"Analyzing {ticker}")
    print(f"{'=' * 60}")

    # Get company name
    companies = get_sp500_companies()
    company_name = ticker
    for c in companies:
        if c.ticker == ticker:
            company_name = c.company_name
            break

    print(f"Company: {company_name}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Stage 0-1: Technical Analysis
    print("Stage 0-1: Technical Analysis (Polygon)...")
    config = GateConfig()
    analysis = analyze_stock(ticker, gate_threshold=config.min_technical_score)

    if analysis is None:
        print(f"❌ Could not fetch data for {ticker}")
        return

    print(f"  Price:           ${analysis.price:.2f}")
    print(f"  52-Week Low:     ${analysis.fifty_two_week_low:.2f}")
    print(f"  52-Week High:    ${analysis.fifty_two_week_high:.2f}")
    print(f"  % From Low:      {analysis.percent_from_low:.1f}%")
    print(f"  RSI:             {analysis.rsi:.1f} ({analysis.rsi_interpretation})")
    print(f"  SMA-20:          ${analysis.sma_20:.2f}")
    print(f"  SMA-50:          ${analysis.sma_50:.2f}")
    print(f"  Technical Score: {analysis.technical_score}/100")
    print(f"  Signals:         {', '.join(analysis.signals)}")
    print()

    # Check gates
    discovery_gate = check_discovery_gate(analysis.percent_from_low, config)
    print(f"Discovery Gate: {'✓ PASSED' if discovery_gate.passed else '✗ FAILED'}")
    if not discovery_gate.passed:
        print(f"  Reason: {discovery_gate.reason}")

    print(f"Technical Gate: {'✓ PASSED' if analysis.passes_gate else '✗ FAILED'}")
    if not analysis.passes_gate:
        print(f"  Reason: Score {analysis.technical_score} < {config.min_technical_score}")

    # Full pipeline if requested
    if full_pipeline and discovery_gate.passed and analysis.passes_gate:
        print()
        print("Running full pipeline with Perplexity...")
        pipeline = ResearchPipeline(gate_config=config)

        # Stage 2
        print("\nStage 2: Quick Scan (Perplexity sonar)...")
        quick_scan, scan_gate = await pipeline.run_quick_scan(ticker, company_name)
        print(f"  Critical Issues: {'Yes' if quick_scan.has_critical_issues else 'No'}")
        print(f"  Risk Level: {quick_scan.risk_level}")
        print(f"  Gate: {'✓ PASSED' if scan_gate.passed else '✗ FAILED'}")

        if not scan_gate.passed:
            print(f"  Reason: {scan_gate.reason}")
            return

        # Stage 3
        print("\nStage 3: Deep Research (Perplexity sonar-pro)...")
        deep_research = await pipeline.run_deep_research(ticker, company_name, analysis)
        print(f"  Decline Type: {deep_research.decline_type}")
        print(f"  Decline Reason: {deep_research.decline_reason}")
        print(f"  Twitter Sentiment: {deep_research.twitter_sentiment}")
        print(f"  Reddit Sentiment: {deep_research.reddit_sentiment}")
        print(f"  Recovery Likelihood: {deep_research.recovery_likelihood}")
        print(f"  Sentiment Score: {deep_research.sentiment_score}/100")

        # Stage 4
        print("\nStage 4: Final Scoring (Perplexity sonar-reasoning)...")
        rec = await pipeline.run_final_scoring(ticker, company_name, analysis, deep_research)
        print(f"  Technical Score:   {rec.technical_score}/100")
        print(f"  Sentiment Score:   {rec.sentiment_score}/100")
        print(f"  Fundamental Score: {rec.fundamental_score}/100")
        print(f"  COMPOSITE SCORE:   {rec.composite_score}/100")
        print()
        print(f"  📊 RECOMMENDATION: {rec.recommendation.upper()}")
        print(f"  📈 Target Price:   ${rec.target_price:.2f} ({rec.upside_percent:.1f}% upside)")
        print(f"  🛑 Stop Loss:      ${rec.stop_loss:.2f}")
        print(f"  ⏱️  Timeline:       {rec.timeline}")
        print(f"  🎯 Confidence:     {rec.confidence}")

    print()
    print("=" * 60)


def run_scan(limit: int, sector: str | None, min_score: int) -> None:
    """Scan S&P 500 for opportunities."""
    print(f"\n{'#' * 60}")
    print(f"#  S&P 500 TECHNICAL SCAN")
    print(f"#  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'#' * 60}")

    # Get companies
    companies = get_sp500_companies()

    if sector:
        companies = [c for c in companies if c.sector.lower() == sector.lower()]
        print(f"\nFiltered to sector: {sector}")

    companies = companies[:limit]
    print(f"Scanning {len(companies)} stocks...")
    print()

    config = GateConfig(min_technical_score=min_score)
    passed: list[dict] = []
    failed_data = 0
    failed_discovery = 0
    failed_technical = 0

    for i, company in enumerate(companies, 1):
        # Rate limiting
        if i > 1:
            time.sleep(13)  # Polygon free tier: 5 calls/min

        print(f"[{i}/{len(companies)}] {company.ticker}...", end=" ")

        try:
            analysis = analyze_stock(company.ticker, gate_threshold=min_score)

            if analysis is None:
                print("❌ No data")
                failed_data += 1
                continue

            # Check gates
            discovery_gate = check_discovery_gate(analysis.percent_from_low, config)
            if not discovery_gate.passed:
                print(f"⏭️  {analysis.percent_from_low:.0f}% from low")
                failed_discovery += 1
                continue

            if not analysis.passes_gate:
                print(f"📉 Score {analysis.technical_score}")
                failed_technical += 1
                continue

            print(f"✅ Score {analysis.technical_score}")
            passed.append({
                "ticker": company.ticker,
                "name": company.company_name,
                "sector": company.sector,
                "score": analysis.technical_score,
                "rsi": analysis.rsi,
                "pct_from_low": analysis.percent_from_low,
            })

        except Exception as e:
            print(f"❌ Error: {e}")
            failed_data += 1

    # Summary
    print()
    print("-" * 60)
    print("SUMMARY")
    print("-" * 60)
    print(f"Scanned:          {len(companies)}")
    print(f"No data:          {failed_data}")
    print(f"Failed discovery: {failed_discovery}")
    print(f"Failed technical: {failed_technical}")
    print(f"PASSED:           {len(passed)}")

    if passed:
        print()
        print("-" * 60)
        print("OPPORTUNITIES (sorted by score)")
        print("-" * 60)
        for stock in sorted(passed, key=lambda x: -x["score"]):
            print(
                f"  {stock['ticker']:6} | Score: {stock['score']:3} | "
                f"RSI: {stock['rsi']:5.1f} | {stock['pct_from_low']:5.1f}% from low | "
                f"{stock['sector']}"
            )

    print()


if __name__ == "__main__":
    run_cli()
