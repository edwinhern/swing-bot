"""Semantic Stocks API - Stock Research Pipeline.

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
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from app.api.routes import router as api_router
from app.data.sp500 import SP500Company, get_sp500_companies
from app.services.polygon.screening import analyze_stock
from app.services.research.gates import GateConfig, check_discovery_gate
from app.services.research.pipeline import ResearchPipeline

# Load environment variables
env_path = Path(__file__).parent.parent / ".env"
if not env_path.exists():
    env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)

# Rich console for pretty output
console = Console()


# =============================================================================
# FastAPI Application
# =============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan handler for startup/shutdown."""
    console.print("🚀 [bold green]Semantic Stocks API starting up...[/]")
    companies = get_sp500_companies()
    console.print(f"📊 Loaded [cyan]{len(companies)}[/] S&P 500 companies")
    yield
    console.print("👋 [bold yellow]Semantic Stocks API shutting down...[/]")


app = FastAPI(
    title="Semantic Stocks API",
    description="Stock research pipeline for swing trading analysis",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint."""
    return {"service": "Semantic Stocks API", "version": "0.1.0", "docs": "/docs"}


# =============================================================================
# CLI Runner
# =============================================================================


def run_cli() -> None:
    """Run the pipeline from command line."""
    parser = argparse.ArgumentParser(
        description="Semantic Stocks Stock Research Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Analyze single stock:   python -m app.main --ticker AAPL
  With full pipeline:     python -m app.main --ticker AAPL --full
  Scan S&P 500:          python -m app.main --scan --limit 20
  Filter by sector:       python -m app.main --scan --sector Technology
        """,
    )

    parser.add_argument("--ticker", type=str, help="Analyze a single stock ticker")
    parser.add_argument("--full", action="store_true", help="Run full pipeline including Perplexity")
    parser.add_argument("--scan", action="store_true", help="Scan S&P 500 for opportunities")
    parser.add_argument("--limit", type=int, default=500, help="Maximum stocks to analyze (default: 500)")
    parser.add_argument("--sector", type=str, help="Filter by sector (e.g., 'Technology')")
    parser.add_argument("--min-score", type=int, default=50, help="Minimum technical score (default: 50)")

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

    # Get company name
    companies = get_sp500_companies()
    company_name = ticker
    sector = "Unknown"
    for c in companies:
        if c.ticker == ticker:
            company_name = c.company_name
            sector = c.sector
            break

    console.print(
        Panel(
            f"[bold]{company_name}[/] ([cyan]{ticker}[/])\n"
            f"Sector: [dim]{sector}[/]\n"
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            title="📊 Stock Analysis",
            border_style="blue",
        )
    )

    # Stage 0-1: Technical Analysis
    with console.status("[bold green]Fetching technical data from Polygon..."):
        config = GateConfig()
        analysis = analyze_stock(ticker, gate_threshold=config.min_technical_score)

    if analysis is None:
        console.print("[bold red]❌ Could not fetch data for this ticker[/]")
        return

    # Display technical data in a table
    tech_table = Table(title="Technical Indicators", show_header=True, header_style="bold cyan")
    tech_table.add_column("Metric", style="dim")
    tech_table.add_column("Value", justify="right")
    tech_table.add_column("Interpretation")

    tech_table.add_row("Price", f"${analysis.price:.2f}", "")
    tech_table.add_row("52-Week Low", f"${analysis.fifty_two_week_low:.2f}", "")
    tech_table.add_row("52-Week High", f"${analysis.fifty_two_week_high:.2f}", "")
    tech_table.add_row(
        "% From Low",
        f"{analysis.percent_from_low:.1f}%",
        "[green]✓ In range[/]" if 5 <= analysis.percent_from_low <= 20 else "[yellow]Outside range[/]",
    )
    tech_table.add_row("RSI", f"{analysis.rsi:.1f}", f"[cyan]{analysis.rsi_interpretation}[/]")
    tech_table.add_row("SMA-20", f"${analysis.sma_20:.2f}", "")
    tech_table.add_row("SMA-50", f"${analysis.sma_50:.2f}", analysis.sma_interpretation)
    tech_table.add_row(
        "Technical Score",
        f"[bold]{analysis.technical_score}[/]/100",
        "[green]PASS[/]" if analysis.passes_gate else "[red]FAIL[/]",
    )

    console.print(tech_table)

    # Signals
    if analysis.signals:
        console.print(f"\n[bold]Signals:[/] {', '.join(analysis.signals)}")

    # Check gates
    discovery_gate = check_discovery_gate(analysis.percent_from_low, config)

    console.print()
    if discovery_gate.passed:
        console.print("[green]✓[/] Discovery Gate: [green]PASSED[/]")
    else:
        console.print(f"[red]✗[/] Discovery Gate: [red]FAILED[/] - {discovery_gate.reason}")

    if analysis.passes_gate:
        console.print("[green]✓[/] Technical Gate: [green]PASSED[/]")
    else:
        console.print(
            f"[red]✗[/] Technical Gate: [red]FAILED[/] - Score {analysis.technical_score} < {config.min_technical_score}"
        )

    # Full pipeline if requested
    if full_pipeline and discovery_gate.passed and analysis.passes_gate:
        console.print()
        console.print(Panel("[bold]Running Perplexity Research Pipeline...[/]", border_style="magenta"))

        pipeline = ResearchPipeline(gate_config=config)

        # Stage 2: Quick Scan
        with console.status("[bold]Stage 2: Quick Scan (checking for critical issues)..."):
            quick_scan, scan_gate = await pipeline.run_quick_scan(ticker, company_name)

        console.print("\n[bold]Stage 2: Quick Scan[/] (Perplexity sonar)")
        console.print(f"  Critical Issues: {'[red]Yes[/]' if quick_scan.has_critical_issues else '[green]No[/]'}")
        console.print(f"  Risk Level: {quick_scan.risk_level}")
        console.print(f"  Gate: {'[green]PASSED[/]' if scan_gate.passed else '[red]FAILED[/]'}")

        if not scan_gate.passed:
            console.print(f"  [red]Reason: {scan_gate.reason}[/]")
            return

        # Stage 3: Deep Research
        with console.status("[bold]Stage 3: Deep Research (analyzing news & sentiment)..."):
            deep_research = await pipeline.run_deep_research(ticker, company_name, analysis)

        console.print("\n[bold]Stage 3: Deep Research[/] (Perplexity sonar-pro)")
        console.print(f"  Decline Type: {deep_research.decline_type}")
        console.print(f"  Reason: {deep_research.decline_reason[:100]}...")
        console.print(f"  Twitter: {deep_research.twitter_sentiment} | Reddit: {deep_research.reddit_sentiment}")
        console.print(f"  Recovery Likelihood: [bold]{deep_research.recovery_likelihood}[/]")
        console.print(f"  Sentiment Score: [bold]{deep_research.sentiment_score}[/]/100")

        # Stage 4: Final Scoring
        with console.status("[bold]Stage 4: Final Scoring (generating recommendation)..."):
            rec = await pipeline.run_final_scoring(ticker, company_name, analysis, deep_research)

        # Final recommendation panel
        rec_color = {
            "strong_buy": "green",
            "buy": "green",
            "hold": "yellow",
            "avoid": "red",
        }.get(rec.recommendation, "white")

        console.print(
            Panel(
                f"[bold {rec_color}]{rec.recommendation.upper()}[/]\n\n"
                f"Composite Score: [bold]{rec.composite_score}[/]/100\n"
                f"  • Technical:   {rec.technical_score}/100\n"
                f"  • Sentiment:   {rec.sentiment_score}/100\n"
                f"  • Fundamental: {rec.fundamental_score}/100\n\n"
                f"📈 Target: [green]${rec.target_price:.2f}[/] ({rec.upside_percent:.1f}% upside)\n"
                f"🛑 Stop Loss: [red]${rec.stop_loss:.2f}[/]\n"
                f"⏱️  Timeline: {rec.timeline}\n"
                f"🎯 Confidence: {rec.confidence}",
                title="📊 Final Recommendation",
                border_style=rec_color,
            )
        )

        # Bull/Bear case
        console.print(f"\n[green]Bull Case:[/] {rec.bull_case}")
        console.print(f"[red]Bear Case:[/] {rec.bear_case}")

        if rec.citations:
            console.print(f"\n[dim]Sources: {', '.join(rec.citations[:3])}[/]")


def _process_company(
    company: SP500Company,
    min_score: int,
    config: GateConfig,
    passed: list[dict],
    failed_data: int,
    failed_discovery: int,
    failed_technical: int,
) -> tuple[int, int, int]:
    """Process a single company and update counters."""
    try:
        analysis = analyze_stock(company.ticker, gate_threshold=min_score)

        if analysis is None:
            return failed_data + 1, failed_discovery, failed_technical

        discovery_gate = check_discovery_gate(analysis.percent_from_low, config)
        if not discovery_gate.passed:
            return failed_data, failed_discovery + 1, failed_technical

        if not analysis.passes_gate:
            return failed_data, failed_discovery, failed_technical + 1

        passed.append({
            "ticker": company.ticker,
            "name": company.company_name,
            "sector": company.sector,
            "score": analysis.technical_score,
            "rsi": analysis.rsi,
            "pct_from_low": analysis.percent_from_low,
            "signals": analysis.signals,
        })
        return failed_data, failed_discovery, failed_technical

    except Exception:
        return failed_data + 1, failed_discovery, failed_technical


def _get_rsi_formatting(rsi: float) -> tuple[str, str]:
    """Get RSI color and icon based on value."""
    if rsi < 30:
        return "green", "▼"  # Oversold - buy signal
    if rsi < 50:
        return "yellow", "↗"  # Recovering
    if rsi < 70:
        return "white", "─"  # Neutral
    return "red", "▲"  # Overbought - caution


def _get_pct_low_formatting(pct_low: float) -> tuple[str, str]:
    """Get percentage from low color and icon based on value."""
    if pct_low <= 15:
        return "green", "●"  # Sweet spot
    if pct_low <= 20:
        return "yellow", "◐"  # Still okay
    return "red", "○"  # Already recovered


def _build_results_table(passed: list[dict]) -> Table:
    """Build the results table with formatted stock data."""
    results_table = Table(title="🎯 Opportunities (sorted by score)", show_header=True, header_style="bold cyan")
    results_table.add_column("Ticker", style="bold")
    results_table.add_column("Score", justify="right")
    results_table.add_column("RSI", justify="right")
    results_table.add_column("% Low", justify="right")
    results_table.add_column("Sector")
    results_table.add_column("Signals", style="dim")

    for stock in sorted(passed, key=lambda x: -x["score"]):
        score_color = "green" if stock["score"] >= 60 else "yellow" if stock["score"] >= 50 else "white"
        signals_str = ", ".join(stock["signals"][:2])

        rsi_color, rsi_icon = _get_rsi_formatting(stock["rsi"])
        pct_color, pct_icon = _get_pct_low_formatting(stock["pct_from_low"])

        results_table.add_row(
            stock["ticker"],
            f"[{score_color}]{stock['score']}[/]",
            f"[{rsi_color}]{rsi_icon} {stock['rsi']:.1f}[/]",
            f"[{pct_color}]{pct_icon} {stock['pct_from_low']:.1f}%[/]",
            stock["sector"],
            signals_str,
        )

    return results_table


def _build_summary_table(
    total_scanned: int,
    failed_data: int,
    failed_discovery: int,
    failed_technical: int,
    passed_count: int,
    min_score: int,
) -> Table:
    """Build the summary table."""
    summary_table = Table(title="Scan Summary", show_header=False, box=None)
    summary_table.add_column("Metric", style="dim")
    summary_table.add_column("Value", justify="right")

    summary_table.add_row("Scanned", str(total_scanned))
    summary_table.add_row("No data", str(failed_data))
    summary_table.add_row("Failed discovery (>20% from low)", str(failed_discovery))
    summary_table.add_row(f"Failed technical (score < {min_score})", str(failed_technical))
    summary_table.add_row("[bold]PASSED[/]", f"[bold green]{passed_count}[/]")
    summary_table.add_row("", "")

    return summary_table


def run_scan(limit: int, sector: str | None, min_score: int) -> None:
    """Scan S&P 500 for opportunities with pretty progress bar."""

    # Header
    console.print(
        Panel(
            f"[bold]S&P 500 Technical Scan[/]\n"
            f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Min Score: {min_score} | Sector: {sector or 'All'}",
            title="🔍 Semantic Stocks Scanner",
            border_style="blue",
        )
    )

    # Get companies
    companies = get_sp500_companies()

    if sector:
        companies = [c for c in companies if c.sector.lower() == sector.lower()]
        console.print(f"Filtered to sector: [cyan]{sector}[/]")

    companies = companies[:limit]
    console.print(f"Scanning [cyan]{len(companies)}[/] stocks...\n")

    config = GateConfig(min_technical_score=min_score)
    passed: list[dict] = []
    failed_data = 0
    failed_discovery = 0
    failed_technical = 0

    # Progress bar with live stats
    with Progress(
        SpinnerColumn(style="cyan"),
        TextColumn("[bold blue]Analyzing:[/]"),
        TextColumn("[cyan]{task.fields[ticker]:6}[/]"),
        BarColumn(bar_width=30, style="blue", complete_style="green"),
        TextColumn("[bold]{task.percentage:>3.0f}%[/]"),
        TextColumn("│"),
        TextColumn("[dim]{task.completed}/{task.total} stocks[/]"),
        TextColumn("│"),
        TimeElapsedColumn(),
        TextColumn("│"),
        TextColumn("[green]✓{task.fields[passed]}[/]"),
        TextColumn("[yellow]⏭{task.fields[skipped]}[/]"),
        TextColumn("[red]✗{task.fields[failed]}[/]"),
        console=console,
        transient=False,
    ) as progress:
        task = progress.add_task("Scanning", total=len(companies), ticker="-----", passed=0, skipped=0, failed=0)

        for company in companies:
            progress.update(task, ticker=company.ticker)

            failed_data, failed_discovery, failed_technical = _process_company(
                company, min_score, config, passed, failed_data, failed_discovery, failed_technical
            )

            progress.update(task, passed=len(passed), skipped=failed_discovery + failed_technical, failed=failed_data)
            progress.advance(task)

    # Summary table
    console.print()
    summary_table = _build_summary_table(
        len(companies), failed_data, failed_discovery, failed_technical, len(passed), min_score
    )
    console.print(summary_table)

    # Results table
    if passed:
        console.print()
        results_table = _build_results_table(passed)
        console.print(results_table)
    else:
        console.print("[yellow]No stocks passed all gates.[/]")

    console.print()


if __name__ == "__main__":
    run_cli()
