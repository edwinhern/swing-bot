# Semantic Stocks

A stock scanner for swing traders. It finds S&P 500 stocks near their 52-week lows and runs AI research on the best candidates.

## The Problem

Stock screeners have three issues:

1. **No context** - They show numbers but don't explain why a stock matters
2. **No sentiment** - Charts don't tell you what the market thinks

## The Idea

Use free data to filter first. Pay for AI research only on stocks that pass.

```
Stage 0: Discovery Gate (FREE)
    └── Keep stocks within 20% of 52-week low

Stage 1: Technical Screen (FREE - Polygon API)
    └── Score by RSI, moving averages, volume

Stage 2: Quick Scan (CHEAP - Perplexity sonar)
    └── Check sentiment on filtered stocks

Stage 3: Deep Research (TARGETED - Perplexity sonar-deep-research)
    └── Full analysis with sources

Stage 4: Final Score (Perplexity sonar-reasoning-pro)
    └── Buy/hold/avoid with price targets
```

This filters 500 stocks → ~60 candidates → ~10 for deep research. AI costs drop 95%.

## Tech Stack

| Tool | Job |
|------|-----|
| **Polygon.io** | Stock prices, 52-week high/low, volume |
| **Perplexity AI** | Research and sentiment with citations |
| **Redis** | Cache for S&P 500 list and results |
| **PostgreSQL** | Store analysis history |
| **FastAPI** | REST API |
| **Rich** | Terminal UI |

## Quick Start

```bash
# Setup
cd backend
uv sync

# Add API keys to .env
cp .env.template .env
# POLYGON_API_KEY - get from polygon.io ($29/mo for unlimited calls)
# PERPLEXITY_API_KEY - get from perplexity.ai

# Start Redis and Postgres
docker compose up -d

# Run a scan
uv run python -m app.main --scan
```

## Commands

```bash
# Scan all S&P 500
uv run python -m app.main --scan

# Scan one sector
uv run python -m app.main --scan --sector Technology

# Check one stock
uv run python -m app.main --ticker AZO

# Full AI research on one stock
uv run python -m app.main --ticker AZO --full
```

## Reading the Output

```
┃ Ticker ┃ Company  ┃ Score ┃    RSI ┃  % Low ┃ Upside ┃ Signals           ┃
│ AZO    │ AutoZone │    65 │ ▼ 27.1 │ ● 9.5% │   +27% │ oversold, bearish │
```

| Column | Meaning |
|--------|---------|
| **Score** | Technical score, 0-100. Stocks need 50+ to pass. |
| **RSI** | Relative Strength Index. Below 30 = oversold. Above 70 = overbought. |
| **% Low** | How far above the 52-week low. Under 15% = good entry point. |
| **Upside** | Gain if stock returns to 52-week high. |
| **Signals** | Patterns found: golden_cross, oversold, bullish_trend, etc. |

### RSI Icons

| Icon | Range | Meaning |
|------|-------|---------|
| ▼ (green) | < 30 | Oversold - consider buying |
| ↗ (yellow) | 30-50 | Recovering |
| ─ (white) | 50-70 | Neutral |
| ▲ (red) | > 70 | Overbought - be careful |

### % Low Icons

| Icon | Range | Meaning |
|------|-------|---------|
| ● (green) | ≤ 15% | Near the low - good entry |
| ◐ (yellow) | 15-20% | Okay, less room to grow |
| ○ (red) | > 20% | Already bounced - may have missed it |
