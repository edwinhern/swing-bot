"""PostgreSQL database service for storing analysis results."""

import os
from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg


class DatabaseService:
    """PostgreSQL database service for the stock research pipeline.

    Handles storing and retrieving:
    - Analysis run history
    - Individual stock analyses
    - Watchlist items
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        user: str | None = None,
        password: str | None = None,
        database: str | None = None,
    ) -> None:
        """Initialize database connection settings.

        Args:
            host: Database host
            port: Database port
            user: Database user
            password: Database password
            database: Database name
        """
        self._host = host or os.getenv("DATABASE__HOST", "localhost")
        self._port = port or int(os.getenv("DATABASE__PORT", "5432"))
        self._user = user or os.getenv("DATABASE__USER", "admin")
        self._password = password or os.getenv("DATABASE__PASSWORD", "")
        self._database = database or os.getenv("DATABASE__DATABASE", "semantic_stocks_db")
        self._pool: asyncpg.Pool | None = None  # type: ignore[no-any-unimported]

    async def connect(self) -> None:
        """Create database connection pool."""
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                host=self._host,
                port=self._port,
                user=self._user,
                password=self._password,
                database=self._database,
                min_size=2,
                max_size=10,
            )

    async def disconnect(self) -> None:
        """Close database connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def _get_pool(self) -> asyncpg.Pool:  # type: ignore[no-any-unimported]
        """Get connection pool, creating if necessary."""
        if self._pool is None:
            await self.connect()

        pool = self._pool
        if pool is None:
            raise RuntimeError("Failed to establish database connection pool")
        return pool

    # =========================================================================
    # Analysis Runs
    # =========================================================================

    async def create_analysis_run(self, config: dict | None = None) -> UUID:
        """Create a new analysis run record.

        Args:
            config: Gate configuration used for this run

        Returns:
            UUID of the created run
        """
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO analysis_runs (config_json)
                VALUES ($1)
                RETURNING id
                """,
                config,
            )
            return UUID(str(row["id"]))

    def _build_update_clause(
        self,
        updates: list[str],
        values: list[Any],
        param_num: int,
        status: str | None,
    ) -> int:
        """Build update clause for status field."""
        if status is not None:
            updates.append(f"status = ${param_num}")
            values.append(status)
            param_num += 1
            if status in ("completed", "failed", "cancelled"):
                updates.append(f"completed_at = ${param_num}")
                values.append(datetime.now())
                param_num += 1
        return param_num

    async def update_analysis_run(
        self,
        run_id: UUID,
        status: str | None = None,
        total_stocks_scanned: int | None = None,
        stocks_passed_discovery: int | None = None,
        stocks_passed_technical: int | None = None,
        stocks_passed_quick_scan: int | None = None,
        stocks_fully_analyzed: int | None = None,
        estimated_cost_usd: float | None = None,
        error_message: str | None = None,
    ) -> None:
        """Update an analysis run record."""
        pool = await self._get_pool()

        updates: list[str] = []
        values: list[Any] = []
        param_num = 1

        param_num = self._build_update_clause(updates, values, param_num, status)

        if total_stocks_scanned is not None:
            updates.append(f"total_stocks_scanned = ${param_num}")
            values.append(total_stocks_scanned)
            param_num += 1

        if stocks_passed_discovery is not None:
            updates.append(f"stocks_passed_discovery = ${param_num}")
            values.append(stocks_passed_discovery)
            param_num += 1

        if stocks_passed_technical is not None:
            updates.append(f"stocks_passed_technical = ${param_num}")
            values.append(stocks_passed_technical)
            param_num += 1

        if stocks_passed_quick_scan is not None:
            updates.append(f"stocks_passed_quick_scan = ${param_num}")
            values.append(stocks_passed_quick_scan)
            param_num += 1

        if stocks_fully_analyzed is not None:
            updates.append(f"stocks_fully_analyzed = ${param_num}")
            values.append(stocks_fully_analyzed)
            param_num += 1

        if estimated_cost_usd is not None:
            updates.append(f"estimated_cost_usd = ${param_num}")
            values.append(estimated_cost_usd)
            param_num += 1

        if error_message is not None:
            updates.append(f"error_message = ${param_num}")
            values.append(error_message)
            param_num += 1

        if not updates:
            return

        values.append(run_id)

        # Build query safely using parameterized placeholders
        set_clause = ", ".join(updates)
        # Use parameterized query - safe from SQL injection
        query = f"UPDATE analysis_runs SET {set_clause} WHERE id = ${param_num}"  # noqa: S608

        async with pool.acquire() as conn:
            await conn.execute(query, *values)

    async def get_analysis_run(self, run_id: UUID) -> dict | None:
        """Get an analysis run by ID."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM analysis_runs WHERE id = $1",
                run_id,
            )
            return dict(row) if row else None

    async def get_recent_runs(self, limit: int = 10) -> list[dict]:
        """Get recent analysis runs."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM analysis_runs
                ORDER BY started_at DESC
                LIMIT $1
                """,
                limit,
            )
            return [dict(row) for row in rows]

    # =========================================================================
    # Stock Analyses
    # =========================================================================

    async def save_stock_analysis(
        self,
        run_id: UUID | None,
        ticker: str,
        company_name: str,
        sector: str | None = None,
        sub_industry: str | None = None,
        technical_data: dict | None = None,
        quick_scan_data: dict | None = None,
        deep_research_data: dict | None = None,
        recommendation_data: dict | None = None,
    ) -> UUID:
        """Save a stock analysis result."""
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO stock_analyses (
                    run_id, ticker, company_name, sector, sub_industry,
                    current_price, fifty_two_week_low, fifty_two_week_high,
                    percent_from_low, rsi, sma_20, sma_50, technical_score,
                    sentiment_score, fundamental_score, composite_score,
                    recommendation, confidence, target_price, stop_loss, timeline,
                    passed_discovery_gate, passed_technical_gate, passed_quick_scan_gate,
                    completed_deep_research, completed_final_scoring,
                    technical_analysis_json, quick_scan_json, deep_research_json,
                    recommendation_json, key_catalysts, risk_factors, citations
                ) VALUES (
                    $1, $2, $3, $4, $5,
                    $6, $7, $8, $9, $10, $11, $12, $13,
                    $14, $15, $16, $17, $18, $19, $20, $21,
                    $22, $23, $24, $25, $26,
                    $27, $28, $29, $30, $31, $32, $33
                )
                RETURNING id
                """,
                run_id,
                ticker,
                company_name,
                sector,
                sub_industry,
                # Technical data
                technical_data.get("price") if technical_data else None,
                technical_data.get("fifty_two_week_low") if technical_data else None,
                technical_data.get("fifty_two_week_high") if technical_data else None,
                technical_data.get("percent_from_low") if technical_data else None,
                technical_data.get("rsi") if technical_data else None,
                technical_data.get("sma_20") if technical_data else None,
                technical_data.get("sma_50") if technical_data else None,
                technical_data.get("technical_score") if technical_data else None,
                # Sentiment/recommendation data
                recommendation_data.get("sentiment_score") if recommendation_data else None,
                recommendation_data.get("fundamental_score") if recommendation_data else None,
                recommendation_data.get("composite_score") if recommendation_data else None,
                recommendation_data.get("recommendation") if recommendation_data else None,
                recommendation_data.get("confidence") if recommendation_data else None,
                recommendation_data.get("target_price") if recommendation_data else None,
                recommendation_data.get("stop_loss") if recommendation_data else None,
                recommendation_data.get("timeline") if recommendation_data else None,
                # Gate flags
                technical_data.get("passes_gate", False) if technical_data else False,
                technical_data.get("passes_gate", False) if technical_data else False,
                quick_scan_data.get("passes_gate", False) if quick_scan_data else False,
                deep_research_data is not None,
                recommendation_data is not None,
                # JSON data
                technical_data,
                quick_scan_data,
                deep_research_data,
                recommendation_data,
                # Arrays
                recommendation_data.get("key_catalysts", []) if recommendation_data else [],
                recommendation_data.get("risk_factors", []) if recommendation_data else [],
                recommendation_data.get("citations", []) if recommendation_data else [],
            )
            return UUID(str(row["id"]))

    async def get_stock_analysis(self, ticker: str, limit: int = 1) -> list[dict]:
        """Get the most recent analyses for a ticker."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM stock_analyses
                WHERE ticker = $1
                ORDER BY analyzed_at DESC
                LIMIT $2
                """,
                ticker.upper(),
                limit,
            )
            return [dict(row) for row in rows]

    async def get_top_recommendations(
        self,
        min_score: int = 60,
        recommendation_filter: list[str] | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """Get top stock recommendations by composite score."""
        pool = await self._get_pool()

        query = """
            SELECT DISTINCT ON (ticker) *
            FROM stock_analyses
            WHERE composite_score >= $1
            AND completed_final_scoring = TRUE
        """
        params: list[Any] = [min_score]

        if recommendation_filter:
            query += f" AND recommendation = ANY(${len(params) + 1})"
            params.append(recommendation_filter)

        query += """
            ORDER BY ticker, analyzed_at DESC
        """

        async with pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        # Sort by composite score and limit
        results = [dict(row) for row in rows]
        results.sort(key=lambda x: x.get("composite_score", 0) or 0, reverse=True)
        return results[:limit]


# Singleton instance
_database_service: DatabaseService | None = None


def get_database_service() -> DatabaseService:
    """Get or create the singleton database service instance."""
    global _database_service
    if _database_service is None:
        _database_service = DatabaseService()
    return _database_service
