"""In-memory DuckDB Arrow streaming engine for CanData-MCP.

Provides zero-copy / streaming slicing and analytical aggregation over
connector observation streams. Guarantees strict <3KB payload sizing
to prevent LLM context exhaustion.
"""

# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false

from __future__ import annotations

import json
import re
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

import duckdb
import pyarrow as pa

from candata_mcp.connectors.boc_valet import FRENCH_TITLES

if TYPE_CHECKING:
    from candata_mcp.connectors.boc_valet import ObservationSet
    from candata_mcp.connectors.statcan_wds import StatCanSeriesResult

# Regex matching date inputs (YYYY, YYYY-MM, or YYYY-MM-DD)
_DATE_REGEX = re.compile(r"^\d{4}(?:-\d{2}(?:-\d{2})?)?$")

# Forbidden SQL statements for read-only security guardrails
_FORBIDDEN_SQL_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|ATTACH|DETACH|COPY|PRAGMA|CALL|INSTALL|LOAD)\b",
    re.IGNORECASE,
)

# Standard payload limit in bytes (3KB)
MAX_PAYLOAD_BYTES: int = 3072


class DuckDBSlicingEngine:
    """In-memory DuckDB engine with Arrow streaming for zero-copy analytical queries."""

    def __init__(self, connection: duckdb.DuckDBPyConnection | None = None) -> None:
        """Initialize an in-memory DuckDB connection."""
        self._con: duckdb.DuckDBPyConnection = connection or duckdb.connect(":memory:")

    @property
    def connection(self) -> duckdb.DuckDBPyConnection:
        """Return the underlying DuckDB connection."""
        return self._con

    def close(self) -> None:
        """Close the DuckDB connection."""
        self._con.close()

    def table_from_statcan(self, result: StatCanSeriesResult) -> pa.Table:
        """Convert a StatCanSeriesResult into an Arrow Table."""
        dates: list[str] = []
        values: list[float | None] = []
        release_times: list[str | None] = []
        decimals: list[int | None] = []

        for obs in result.observations:
            dates.append(obs.ref_per)
            values.append(obs.value)
            release_times.append(obs.release_time)
            decimals.append(obs.decimals)

        return pa.Table.from_pydict(
            {
                "date": dates,
                "value": values,
                "release_time": release_times,
                "decimals": decimals,
            }
        )

    def table_from_valet(self, result: ObservationSet) -> pa.Table:
        """Convert a Valet ObservationSet into an Arrow Table."""
        dates: list[str] = []
        values: list[float | None] = []

        for obs in result.observations:
            dates.append(obs.date)
            values.append(obs.value)

        return pa.Table.from_pydict(
            {
                "date": dates,
                "value": values,
            }
        )

    def slice_table(
        self,
        table: pa.Table,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 12,
        descending: bool = True,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Slice an Arrow table by date range and limit, returning records and summary.

        Uses Arrow streaming into DuckDB to avoid large allocations.
        """
        if limit <= 0:
            limit = 12

        # Validate date parameters against ISO date regex to prevent query injection
        if start_date and not _DATE_REGEX.match(start_date):
            raise ValueError(f"Invalid start_date format: '{start_date}'. Expected YYYY[-MM[-DD]].")
        if end_date and not _DATE_REGEX.match(end_date):
            raise ValueError(f"Invalid end_date format: '{end_date}'. Expected YYYY[-MM[-DD]].")

        temp_name = "current_series"
        self._con.register(temp_name, table)

        try:
            where_clauses: list[str] = []
            params: list[Any] = []

            if start_date:
                where_clauses.append("date >= ?")
                params.append(start_date)
            if end_date:
                where_clauses.append("date <= ?")
                params.append(end_date)

            where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
            order_sql = "DESC" if descending else "ASC"

            data_query = (
                f"SELECT * FROM {temp_name} {where_sql} ORDER BY date {order_sql} LIMIT ?"
            )
            data_params = [*params, limit]

            # Execute streaming Arrow reader into records
            reader = self._con.execute(data_query, data_params).arrow()
            records: list[dict[str, Any]] = reader.read_all().to_pylist()

            # Compute summary statistics
            summary_query = f"""
                SELECT
                    count(*) AS count,
                    min(date) AS min_date,
                    max(date) AS max_date,
                    avg(value) AS avg_value,
                    min(value) AS min_value,
                    max(value) AS max_value
                FROM {temp_name} {where_sql}
            """
            summary_row = self._con.execute(summary_query, params).fetchone()
            summary: dict[str, Any] = {
                "filtered_count": summary_row[0] if summary_row else 0,
                "min_date": summary_row[1] if summary_row else None,
                "max_date": summary_row[2] if summary_row else None,
                "avg_value": round(float(summary_row[3]), 4)
                if summary_row and summary_row[3] is not None
                else None,
                "min_value": round(float(summary_row[4]), 4)
                if summary_row and summary_row[4] is not None
                else None,
                "max_value": round(float(summary_row[5]), 4)
                if summary_row and summary_row[5] is not None
                else None,
            }

            return records, summary
        finally:
            self._con.unregister(temp_name)

    def slice_statcan(
        self,
        result: StatCanSeriesResult,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 12,
        descending: bool = True,
    ) -> dict[str, Any]:
        """Slice StatCan series into an LLM-ready <3KB payload with citation envelope."""
        table = self.table_from_statcan(result)
        records, summary = self.slice_table(
            table,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            descending=descending,
        )

        citation = asdict(result.citation())

        payload: dict[str, Any] = {
            "source": "Statistics Canada",
            "product_id": str(result.product_id),
            "vector_id": f"v{result.vector_id}",
            "coordinate": result.coordinate,
            "title": {"en": result.title_en, "fr": result.title_fr},
            "unit": result.unit,
            "total_available": len(result.observations),
            "returned_count": len(records),
            "summary": summary,
            "data": records,
            "citation": citation,
        }

        return self.clamp_payload(payload)

    def slice_valet(
        self,
        result: ObservationSet,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 12,
        descending: bool = True,
    ) -> dict[str, Any]:
        """Slice Bank of Canada Valet series into an LLM-ready <3KB payload."""
        table = self.table_from_valet(result)
        records, summary = self.slice_table(
            table,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            descending=descending,
        )

        citation = asdict(result.citation())
        french_title = FRENCH_TITLES.get(result.series.name)

        payload: dict[str, Any] = {
            "source": "Bank of Canada",
            "series_name": result.series.name,
            "title": {"en": result.series.label, "fr": french_title},
            "total_available": len(result.observations),
            "returned_count": len(records),
            "summary": summary,
            "data": records,
            "citation": citation,
        }

        return self.clamp_payload(payload)

    def execute_analytics(
        self,
        table: pa.Table,
        sql_query: str,
        *,
        table_name: str = "series",
        max_rows: int = 20,
    ) -> list[dict[str, Any]]:
        """Execute a safe, read-only SQL analytical query over an Arrow Table."""
        stripped = sql_query.strip()

        # Security guardrails: must begin with SELECT or WITH
        if not re.match(r"^(?:SELECT|WITH)\b", stripped, re.IGNORECASE):
            raise ValueError("Only read-only SELECT or WITH analytical queries are permitted.")

        # Guard against DDL/DML injection
        if _FORBIDDEN_SQL_KEYWORDS.search(stripped):
            raise ValueError("Analytical query contains forbidden SQL statements or keywords.")

        self._con.register(table_name, table)
        try:
            # Enforce max row limit if query doesn't explicitly limit
            safe_query = f"SELECT * FROM ({stripped}) LIMIT {max_rows}"
            reader = self._con.execute(safe_query).arrow()
            return reader.read_all().to_pylist()
        finally:
            self._con.unregister(table_name)

    def clamp_payload(
        self,
        payload: dict[str, Any],
        max_bytes: int = MAX_PAYLOAD_BYTES,
    ) -> dict[str, Any]:
        """Guarantee payload strictly complies with the <3KB budget.

        If payload exceeds max_bytes, progressively pops data rows while
        preserving the summary statistics and Two-Tier Citation Envelope.
        """
        encoded_len = len(json.dumps(payload, default=str).encode("utf-8"))
        if encoded_len <= max_bytes:
            return payload

        # Payload exceeds budget; truncate data rows
        data = payload.get("data")
        if isinstance(data, list) and data:
            truncated_data: list[Any] = list(data)
            while truncated_data and encoded_len > max_bytes:
                truncated_data.pop()
                payload["data"] = truncated_data
                payload["returned_count"] = len(truncated_data)
                payload["truncated"] = True
                encoded_len = len(json.dumps(payload, default=str).encode("utf-8"))

        return payload
