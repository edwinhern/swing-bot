"""FastAPI routes for the stock research pipeline."""

import asyncio
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field

from app.data.sp500 import SP500Company, get_sp500_companies
from app.services.polygon.screening import TechnicalAnalysis, analyze_stock
from app.services.research.gates import GateConfig, check_discovery_gate, check_technical_gate
from app.services.research.pipeline import ResearchPipeline

router = APIRouter(prefix="/api", tags=["research"])


# =============================================================================
# Request/Response Models
# =============================================================================


class SP500Response(BaseModel):
    """Response model for S&P 500 companies list."""

    total: int
    companies: list[dict]


class TechnicalScreeningRequest(BaseModel):
    """Request model for technical screening."""

    tickers: list[str] | None = Field(
        default=None,
        description="List of tickers to analyze. If None, analyzes all S&P 500.",
    )
    limit: int = Field(
        default=50,
        ge=1,
        le=500,
        description="Maximum number of stocks to analyze",
    )
    sectors: list[str] | None = Field(
        default=None,
        description="Filter by sectors (e.g., ['Technology', 'Healthcare'])",
    )
    min_technical_score: int = Field(
        default=50,
        ge=0,
        le=100,
        description="Minimum technical score to pass gate",
    )


class TechnicalScreeningResponse(BaseModel):
    """Response model for technical screening."""

    analyzed: int
    passed_discovery: int
    passed_technical: int
    failed_data: int
    results: list[dict]


class SingleStockRequest(BaseModel):
    """Request model for single stock analysis."""

    ticker: str = Field(description="Stock ticker symbol")
    company_name: str | None = Field(
        default=None,
        description="Company name (will be looked up if not provided)",
    )
    run_full_pipeline: bool = Field(
        default=False,
        description="If True, runs full pipeline including Perplexity stages",
    )


class SingleStockResponse(BaseModel):
    """Response model for single stock analysis."""

    ticker: str
    company_name: str
    technical_analysis: dict | None
    quick_scan: dict | None = None
    deep_research: dict | None = None
    recommendation: dict | None = None
    stages_completed: list[str]
    gates_passed: list[str]
    gates_failed: list[str]


# =============================================================================
# Health Check
# =============================================================================


@router.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "swingbot-api",
    }


# =============================================================================
# S&P 500 Data
# =============================================================================


@router.get("/sp500", response_model=SP500Response)
async def get_sp500_list(
    sector: str | None = Query(None, description="Filter by sector"),
) -> SP500Response:
    """Get the list of S&P 500 companies.

    Cached for 24 hours. Data sourced from Wikipedia via GitHub datasets.
    """
    companies = get_sp500_companies()

    # Filter by sector if provided
    if sector:
        companies = [c for c in companies if c.sector.lower() == sector.lower()]

    return SP500Response(
        total=len(companies),
        companies=[
            {
                "ticker": c.ticker,
                "company_name": c.company_name,
                "sector": c.sector,
                "sub_industry": c.sub_industry,
            }
            for c in companies
        ],
    )


@router.get("/sp500/sectors")
async def get_sectors() -> dict:
    """Get list of sectors and company counts."""
    companies = get_sp500_companies()
    sectors: dict[str, int] = {}
    for c in companies:
        sectors[c.sector] = sectors.get(c.sector, 0) + 1
    return {"sectors": [{"name": name, "count": count} for name, count in sorted(sectors.items(), key=lambda x: -x[1])]}


# =============================================================================
# Technical Screening (Stage 0-1)
# =============================================================================


@router.post("/screen/technical", response_model=TechnicalScreeningResponse)
async def run_technical_screening(
    request: TechnicalScreeningRequest,
) -> TechnicalScreeningResponse:
    """Run technical screening on stocks (Stages 0-1).

    This uses Polygon data (FREE) to filter stocks based on:
    - 52-week low proximity (5-20% above low)
    - Technical score (RSI, SMA, volume)

    Note: Polygon free tier has 5 calls/minute rate limit.
    """
    # Get S&P 500 companies
    companies = get_sp500_companies()

    # Filter by sectors if provided
    if request.sectors:
        sector_lower = [s.lower() for s in request.sectors]
        companies = [c for c in companies if c.sector.lower() in sector_lower]

    # Filter by specific tickers if provided
    if request.tickers:
        ticker_set = {t.upper() for t in request.tickers}
        companies = [c for c in companies if c.ticker in ticker_set]

    # Limit the number of companies
    companies = companies[: request.limit]

    config = GateConfig(min_technical_score=request.min_technical_score)
    results: list[dict] = []
    failed_data = 0
    passed_discovery = 0
    passed_technical = 0

    for company in companies:
        try:
            analysis = analyze_stock(
                ticker=company.ticker,
                gate_threshold=config.min_technical_score,
            )

            if analysis is None:
                failed_data += 1
                continue

            # Check discovery gate
            discovery_gate = check_discovery_gate(
                percent_from_low=analysis.percent_from_low,
                config=config,
            )

            if not discovery_gate.passed:
                continue

            passed_discovery += 1

            # Check technical gate
            if not analysis.passes_gate:
                continue

            passed_technical += 1

            results.append({
                "ticker": company.ticker,
                "company_name": company.company_name,
                "sector": company.sector,
                "price": analysis.price,
                "percent_from_low": analysis.percent_from_low,
                "rsi": analysis.rsi,
                "sma_20": analysis.sma_20,
                "sma_50": analysis.sma_50,
                "technical_score": analysis.technical_score,
                "signals": analysis.signals,
                "rsi_interpretation": analysis.rsi_interpretation,
                "sma_interpretation": analysis.sma_interpretation,
            })

            # Rate limiting: sleep to avoid 429 errors
            await asyncio.sleep(0.5)

        except Exception:
            failed_data += 1
            continue

    # Sort by technical score
    results.sort(key=lambda x: x["technical_score"], reverse=True)

    return TechnicalScreeningResponse(
        analyzed=len(companies),
        passed_discovery=passed_discovery,
        passed_technical=passed_technical,
        failed_data=failed_data,
        results=results,
    )


# =============================================================================
# Single Stock Analysis
# =============================================================================


@router.post("/analyze/single", response_model=SingleStockResponse)
async def analyze_single_stock(
    request: SingleStockRequest,
) -> SingleStockResponse:
    """Analyze a single stock.

    By default, only runs technical analysis (free).
    Set run_full_pipeline=True to include Perplexity stages (costs money).
    """
    ticker = request.ticker.upper()

    # Look up company name if not provided
    company_name = request.company_name
    if not company_name:
        companies = get_sp500_companies()
        for c in companies:
            if c.ticker == ticker:
                company_name = c.company_name
                break
        if not company_name:
            company_name = ticker  # Fallback to ticker

    stages_completed: list[str] = []
    gates_passed: list[str] = []
    gates_failed: list[str] = []

    # Stage 0-1: Technical Analysis
    config = GateConfig()
    analysis = analyze_stock(ticker=ticker, gate_threshold=config.min_technical_score)

    if analysis is None:
        raise HTTPException(
            status_code=404,
            detail=f"Could not fetch data for {ticker}. Check if ticker is valid.",
        )

    stages_completed.append("technical_analysis")
    technical_dict = analysis.model_dump()

    # Check discovery gate
    discovery_gate = check_discovery_gate(
        percent_from_low=analysis.percent_from_low,
        config=config,
    )
    if discovery_gate.passed:
        gates_passed.append("discovery")
    else:
        gates_failed.append(f"discovery: {discovery_gate.reason}")

    # Check technical gate
    if analysis.passes_gate:
        gates_passed.append("technical")
    else:
        gates_failed.append(f"technical: score {analysis.technical_score} < 50")

    response = SingleStockResponse(
        ticker=ticker,
        company_name=company_name,
        technical_analysis=technical_dict,
        stages_completed=stages_completed,
        gates_passed=gates_passed,
        gates_failed=gates_failed,
    )

    # If full pipeline requested and gates passed, run Perplexity stages
    if request.run_full_pipeline and len(gates_failed) == 0:
        pipeline = ResearchPipeline(gate_config=config)

        # Stage 2: Quick Scan
        try:
            quick_scan, scan_gate = await pipeline.run_quick_scan(ticker, company_name)
            stages_completed.append("quick_scan")
            response.quick_scan = quick_scan.model_dump()

            if scan_gate.passed:
                gates_passed.append("quick_scan")
            else:
                gates_failed.append(f"quick_scan: {scan_gate.reason}")
                return response

        except Exception as e:
            gates_failed.append(f"quick_scan: error - {e!s}")
            return response

        # Stage 3: Deep Research
        try:
            deep_research = await pipeline.run_deep_research(ticker, company_name, analysis)
            stages_completed.append("deep_research")
            response.deep_research = deep_research.model_dump()

        except Exception as e:
            gates_failed.append(f"deep_research: error - {e!s}")
            return response

        # Stage 4: Final Scoring
        try:
            recommendation = await pipeline.run_final_scoring(ticker, company_name, analysis, deep_research)
            stages_completed.append("final_scoring")
            response.recommendation = recommendation.model_dump()

        except Exception as e:
            gates_failed.append(f"final_scoring: error - {e!s}")

    return response


# =============================================================================
# Results (from database)
# =============================================================================


@router.get("/results")
async def get_results(
    ticker: str | None = Query(None, description="Filter by ticker"),
    recommendation: str | None = Query(None, description="Filter by recommendation"),
    min_score: int = Query(60, ge=0, le=100, description="Minimum composite score"),
    limit: int = Query(20, ge=1, le=100, description="Maximum results"),
) -> dict:
    """Get stored analysis results.

    Note: Requires database connection to be configured.
    """
    # For now, return a placeholder - full implementation requires DB
    return {
        "message": "Database queries not yet implemented. Run docker-compose up to start Postgres.",
        "filters": {
            "ticker": ticker,
            "recommendation": recommendation,
            "min_score": min_score,
            "limit": limit,
        },
    }
