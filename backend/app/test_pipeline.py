"""Test script for the stock research pipeline.

Run this script to test each stage of the pipeline step by step.
Usage: uv run python -m app.test_pipeline
"""

import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env file
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)

from app.data.sp500 import get_sp500_companies
from app.services.polygon.screening import analyze_stock
from app.services.research.gates import GateConfig, check_discovery_gate


def test_sp500_data() -> None:
    """Test Stage 0: Fetching S&P 500 data."""
    print("\n" + "=" * 70)
    print("STAGE 0: S&P 500 Data Fetch")
    print("=" * 70)

    start = time.time()
    companies = get_sp500_companies()
    elapsed = time.time() - start

    print(f"\n✓ Loaded {len(companies)} S&P 500 companies in {elapsed:.2f}s")

    # Show sector breakdown
    print("\nSector breakdown:")
    sectors: dict[str, int] = {}
    for c in companies:
        sectors[c.sector] = sectors.get(c.sector, 0) + 1
    for sector, count in sorted(sectors.items(), key=lambda x: -x[1]):
        print(f"  {sector:40} {count:3} companies")

    # Show first 5
    print("\nFirst 5 companies:")
    for c in companies[:5]:
        print(f"  {c.ticker:6} | {c.company_name:30} | {c.sector}")

    return companies


def test_technical_screening(limit: int = 20) -> None:
    """Test Stage 0-1: Technical screening with Polygon.

    This tests both the discovery gate (52-week low proximity)
    and the technical screening (RSI, SMA, volume scoring).
    """
    print("\n" + "=" * 70)
    print("STAGE 0-1: Technical Screening (Polygon - FREE)")
    print("=" * 70)

    # Get S&P 500 companies
    companies = get_sp500_companies()

    # Use a subset for testing (configurable)
    test_companies = companies[:limit]
    print(f"\nTesting {len(test_companies)} companies (limited for testing)")

    config = GateConfig()
    passed_discovery: list[tuple[str, str, float]] = []
    passed_technical: list[dict] = []
    failed_data: list[str] = []
    failed_discovery: list[tuple[str, str]] = []
    failed_technical: list[tuple[str, int]] = []

    for i, company in enumerate(test_companies, 1):
        ticker = company.ticker
        name = company.company_name

        # Rate limiting: Polygon free tier is 5 calls/min
        # Sleep 13 seconds between stocks to stay under limit
        # (Each stock makes ~2-3 API calls)
        if i > 1:
            print("  ⏳ Waiting 13s for rate limit...")
            time.sleep(13)

        print(f"\n[{i}/{len(test_companies)}] Analyzing {ticker} ({name})...")

        try:
            # Run technical analysis
            analysis = analyze_stock(ticker, gate_threshold=config.min_technical_score)

            if analysis is None:
                failed_data.append(ticker)
                print(f"  ✗ Insufficient data")
                continue

            # Check discovery gate (52-week low proximity)
            discovery_gate = check_discovery_gate(
                percent_from_low=analysis.percent_from_low,
                config=config,
            )

            if not discovery_gate.passed:
                failed_discovery.append((ticker, discovery_gate.reason))
                print(f"  ✗ Discovery gate: {discovery_gate.reason}")
                continue

            passed_discovery.append((ticker, name, analysis.percent_from_low))

            # Check technical gate
            if not analysis.passes_gate:
                failed_technical.append((ticker, analysis.technical_score))
                print(f"  ✗ Technical gate: Score {analysis.technical_score}/100 < 50")
                continue

            # Passed all gates!
            passed_technical.append({
                "ticker": ticker,
                "name": name,
                "price": analysis.price,
                "pct_from_low": analysis.percent_from_low,
                "rsi": analysis.rsi,
                "technical_score": analysis.technical_score,
                "signals": analysis.signals,
            })
            print(
                f"  ✓ PASSED! Score: {analysis.technical_score}/100, "
                f"RSI: {analysis.rsi}, {analysis.percent_from_low:.1f}% from low"
            )

        except Exception as e:
            print(f"  ✗ Error: {e}")
            failed_data.append(ticker)

    # Summary
    print("\n" + "-" * 70)
    print("SUMMARY")
    print("-" * 70)
    print(f"Total analyzed:        {len(test_companies)}")
    print(f"Insufficient data:     {len(failed_data)}")
    print(f"Failed discovery gate: {len(failed_discovery)}")
    print(f"Failed technical gate: {len(failed_technical)}")
    print(f"PASSED ALL GATES:      {len(passed_technical)}")

    if passed_technical:
        print("\n" + "-" * 70)
        print("STOCKS THAT PASSED ALL GATES (Ready for Perplexity research)")
        print("-" * 70)
        for stock in sorted(passed_technical, key=lambda x: -x["technical_score"]):
            print(
                f"  {stock['ticker']:6} | Score: {stock['technical_score']:3}/100 | "
                f"RSI: {stock['rsi']:5.1f} | {stock['pct_from_low']:5.1f}% from low | "
                f"Signals: {', '.join(stock['signals'][:3])}"
            )

    # Cost estimate
    print("\n" + "-" * 70)
    print("COST ESTIMATE FOR NEXT STAGES")
    print("-" * 70)
    n = len(passed_technical)
    print(f"Stocks passing to Stage 2:  {n}")
    print(f"Stage 2 (Quick Scan):       ~${n * 0.001:.3f}")
    print(f"Stage 3 (Deep Research):    ~${n * 0.02:.3f}")
    print(f"Stage 4 (Final Scoring):    ~${n * 0.01:.3f}")
    print(f"TOTAL ESTIMATED COST:       ~${n * 0.031:.3f}")

    return passed_technical


def main() -> None:
    """Run all pipeline tests."""
    print("\n" + "#" * 70)
    print("#  STOCK RESEARCH PIPELINE TEST")
    print(f"#  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("#" * 70)

    # Test S&P 500 data fetch
    test_sp500_data()

    # Test technical screening
    # Start with 5 stocks for quick testing (Polygon free tier: 5 calls/min)
    # Increase to test more or all 500 (but will take longer due to rate limits)
    passed = test_technical_screening(limit=5)

    print("\n" + "#" * 70)
    print("#  TEST COMPLETE")
    print("#" * 70)


if __name__ == "__main__":
    main()
