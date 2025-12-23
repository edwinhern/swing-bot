"""S&P 500 companies data fetcher.

Fetches the current S&P 500 constituents from the datasets/s-and-p-500-companies
GitHub repository, which scrapes Wikipedia and keeps the list up-to-date.

Source: https://github.com/datasets/s-and-p-500-companies
"""

import csv
import io
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import httpx

# Raw CSV URL from the datasets repo
SP500_CSV_URL = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"

# Local cache file
CACHE_DIR = Path(__file__).parent / ".cache"
CACHE_FILE = CACHE_DIR / "sp500_constituents.csv"
CACHE_MAX_AGE_HOURS = 24  # Refresh cache after 24 hours


@dataclass
class SP500Company:
    """Represents an S&P 500 company."""

    ticker: str
    company_name: str
    sector: str
    sub_industry: str
    headquarters: str
    date_added: str | None = None
    cik: str | None = None
    founded: str | None = None


def _is_cache_valid() -> bool:
    """Check if the local cache is still valid (not expired)."""
    if not CACHE_FILE.exists():
        return False

    # Check file age
    file_mtime = datetime.fromtimestamp(CACHE_FILE.stat().st_mtime)
    age = datetime.now() - file_mtime
    return age < timedelta(hours=CACHE_MAX_AGE_HOURS)


def _fetch_from_github() -> str:
    """Fetch the S&P 500 CSV from GitHub."""
    print("Fetching S&P 500 data from GitHub...")
    response = httpx.get(SP500_CSV_URL, timeout=30.0)
    response.raise_for_status()
    return response.text


def _save_to_cache(csv_content: str) -> None:
    """Save CSV content to local cache."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(csv_content)
    print(f"Cached S&P 500 data to {CACHE_FILE}")


def _load_from_cache() -> str:
    """Load CSV content from local cache."""
    return CACHE_FILE.read_text()


def _parse_csv(csv_content: str) -> list[SP500Company]:
    """Parse the CSV content into SP500Company objects."""
    companies: list[SP500Company] = []

    reader = csv.DictReader(io.StringIO(csv_content))
    for row in reader:
        company = SP500Company(
            ticker=row.get("Symbol", "").strip(),
            company_name=row.get("Security", "").strip(),
            sector=row.get("GICS Sector", "").strip(),
            sub_industry=row.get("GICS Sub-Industry", "").strip(),
            headquarters=row.get("Headquarters Location", "").strip(),
            date_added=row.get("Date added", "").strip() or None,
            cik=row.get("CIK", "").strip() or None,
            founded=row.get("Founded", "").strip() or None,
        )
        if company.ticker:  # Skip empty rows
            companies.append(company)

    return companies


def refresh_sp500_cache() -> list[SP500Company]:
    """Force refresh the S&P 500 cache from GitHub.

    Returns:
        List of SP500Company objects
    """
    csv_content = _fetch_from_github()
    _save_to_cache(csv_content)
    return _parse_csv(csv_content)


def get_sp500_companies(force_refresh: bool = False) -> list[SP500Company]:
    """Get the list of S&P 500 companies.

    Uses a local cache to avoid fetching from GitHub on every call.
    Cache is automatically refreshed after CACHE_MAX_AGE_HOURS.

    Args:
        force_refresh: If True, always fetch fresh data from GitHub

    Returns:
        List of SP500Company objects with ticker, name, sector, etc.
    """
    if force_refresh or not _is_cache_valid():
        return refresh_sp500_cache()

    # Load from cache
    print("Loading S&P 500 data from cache...")
    csv_content = _load_from_cache()
    return _parse_csv(csv_content)


def get_sp500_tickers() -> list[tuple[str, str, str]]:
    """Get S&P 500 tickers as simple tuples.

    Convenience function for pipeline input.

    Returns:
        List of (ticker, company_name, sector) tuples
    """
    companies = get_sp500_companies()
    return [(c.ticker, c.company_name, c.sector) for c in companies]


# Quick test
if __name__ == "__main__":
    companies = get_sp500_companies()
    print(f"\nLoaded {len(companies)} S&P 500 companies")
    print("\nFirst 10 companies:")
    for c in companies[:10]:
        print(f"  {c.ticker:6} | {c.company_name:30} | {c.sector}")

    print("\nSector breakdown:")
    sectors: dict[str, int] = {}
    for c in companies:
        sectors[c.sector] = sectors.get(c.sector, 0) + 1
    for sector, count in sorted(sectors.items(), key=lambda x: -x[1]):
        print(f"  {sector:40} {count:3} companies")
