"""In-memory DuckDB Arrow streaming engine for CanData-MCP.

Provides zero-copy / streaming slicing and analytical aggregation over
connector observation streams. Guarantees strict <3KB payload sizing
to prevent LLM context exhaustion.
"""

# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false

from __future__ import annotations

import copy
import datetime
import json
import re
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

import duckdb
import pyarrow as pa

from candata_mcp.bilingual import Language, localize_title
from candata_mcp.connectors.boc_valet import FRENCH_TITLES, VALET_BASE_URL
from candata_mcp.lineage import SourceCall, build_lineage

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

TRUNCATION_STEP = "truncated: rows dropped from the end to fit the 3072-byte payload budget"


def _slice_step(
    summary: dict[str, Any],
    *,
    returned: int,
    start_date: str | None,
    end_date: str | None,
    limit: int,
    descending: bool,
) -> str:
    order = "newest first" if descending else "oldest first"
    return (
        f"sliced in DuckDB: {start_date or 'earliest'} to {end_date or 'latest'}, {order}, "
        f"limit {limit}; {summary['filtered_count']} rows matched, {returned} returned"
    )


def normalize_date_bound(date_str: str, *, is_end: bool) -> tuple[str, str]:
    """Normalize a partial or full ISO date string into an operator and date literal.

    Returns:
        (operator, normalized_date) where operator is one of ('>=', '<=', '<').
    """
    clean_date = date_str.strip()
    if not _DATE_REGEX.match(clean_date):
        raise ValueError(f"Invalid date format: '{date_str}'. Expected YYYY[-MM[-DD]].")

    parts = clean_date.split("-")
    if not is_end:
        if len(parts) == 1:
            return ">=", f"{parts[0]}-01-01"
        elif len(parts) == 2:
            return ">=", f"{parts[0]}-{parts[1]}-01"
        else:
            return ">=", clean_date
    else:
        if len(parts) == 1:
            next_year = int(parts[0]) + 1
            return "<", f"{next_year:04d}-01-01"
        elif len(parts) == 2:
            year, month = int(parts[0]), int(parts[1])
            if month == 12:
                next_year, next_month = year + 1, 1
            else:
                next_year, next_month = year, month + 1
            return "<", f"{next_year:04d}-{next_month:02d}-01"
        else:
            return "<=", clean_date


class DuckDBSlicingEngine:
    """In-memory DuckDB engine with Arrow streaming for zero-copy analytical queries."""

    def __init__(self, connection: duckdb.DuckDBPyConnection | None = None) -> None:
        """Initialize in-memory DuckDB connection locked down against filesystem/network access."""
        if connection is not None:
            self._con: duckdb.DuckDBPyConnection = connection
        else:
            self._con: duckdb.DuckDBPyConnection = duckdb.connect(
                ":memory:",
                config={
                    "enable_external_access": False,
                    "lock_configuration": True,
                },
            )

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
        status_codes: list[int | None] = []
        symbol_codes: list[int | None] = []

        for obs in result.observations:
            dates.append(obs.ref_per)
            values.append(obs.value)
            release_times.append(obs.release_time)
            decimals.append(obs.decimals)
            status_codes.append(obs.status_code)
            symbol_codes.append(obs.symbol_code)

        metadata: dict[bytes, bytes] = {
            b"product_id": str(result.product_id).encode("utf-8"),
            b"vector_id": str(result.vector_id).encode("utf-8"),
            b"coordinate": result.coordinate.encode("utf-8"),
        }
        if result.unit:
            metadata[b"unit"] = result.unit.encode("utf-8")
        if getattr(result, "series_title_en", None):
            metadata[b"series_title_en"] = str(result.series_title_en).encode("utf-8")

        table = pa.Table.from_pydict(
            {
                "date": dates,
                "value": values,
                "release_time": release_times,
                "decimals": decimals,
                "status_code": status_codes,
                "symbol_code": symbol_codes,
            }
        )
        return table.replace_schema_metadata(metadata)

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

        Uses Arrow streaming into DuckDB to avoid large allocations and normalizes
        temporal boundaries to avoid period exclusion bugs.
        """
        if limit <= 0:
            limit = 12

        temp_name = "current_series"
        self._con.register(temp_name, table)

        try:
            date_expr = "TRY_CAST(substr(date || '-01-01', 1, 10) AS DATE)"
            where_clauses: list[str] = []
            params: list[Any] = []
            norm_start_str: str | None = None

            if start_date:
                op, norm_start_str = normalize_date_bound(start_date, is_end=False)
                where_clauses.append(f"{date_expr} {op} ?::DATE")
                params.append(norm_start_str)
            if end_date:
                op, norm_end = normalize_date_bound(end_date, is_end=True)
                where_clauses.append(f"{date_expr} {op} ?::DATE")
                params.append(norm_end)

            where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
            order_sql = "DESC" if descending else "ASC"

            data_query = f"SELECT * FROM {temp_name} {where_sql} ORDER BY date {order_sql} LIMIT ?"
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

            # Diagnostic note when requested date range precedes fetched observation window
            if start_date and norm_start_str:
                earliest_row = self._con.execute(
                    f"SELECT min({date_expr}) FROM {temp_name}"
                ).fetchone()
                earliest_fetched = earliest_row[0] if earliest_row else None
                if earliest_fetched is not None:
                    req_start = datetime.date.fromisoformat(norm_start_str)
                    if req_start < earliest_fetched:
                        summary["data_window_note"] = (
                            f"Requested start_date '{start_date}' precedes earliest fetched "
                            f"observation ('{earliest_fetched}'). Earlier data exists upstream."
                        )

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
        lang: Language = "en",
        source_call: SourceCall | None = None,
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

        envelope = result.citation()
        citation = asdict(envelope)
        fetch_step = f"fetched {len(result.observations)} observations"
        if source_call is not None:
            fetch_step += f" via {source_call.endpoint.rsplit('/', 1)[-1]}"

        payload: dict[str, Any] = {
            "source": "Statistics Canada",
            "product_id": str(result.product_id),
            "vector_id": f"v{result.vector_id}",
            "coordinate": result.coordinate,
            "title": {"en": result.title_en, "fr": result.title_fr},
            "series_title": (
                {"en": result.series_title_en, "fr": result.series_title_fr}
                if getattr(result, "series_title_en", None)
                else None
            ),
            "display": localize_title(envelope.enrichment.bilingual_title, lang).to_payload(),
            "unit": result.unit,
            "total_available": len(result.observations),
            "returned_count": len(records),
            "summary": summary,
            "data": records,
            "citation": citation,
            "lineage": build_lineage(
                publisher=envelope.publisher,
                fetched_at=result.fetched_at,
                upstream_release=envelope.enrichment.release_or_revision_date,
                source_call=source_call,
                title_source=f"getCubeMetadata productId {result.product_id}",
                steps=(
                    fetch_step,
                    _slice_step(
                        summary,
                        returned=len(records),
                        start_date=start_date,
                        end_date=end_date,
                        limit=limit,
                        descending=descending,
                    ),
                ),
            ),
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
        lang: Language = "en",
        source_call: SourceCall | None = None,
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

        envelope = result.citation()
        citation = asdict(envelope)
        french_title = FRENCH_TITLES.get(result.series.name)
        fetch_step = f"fetched {len(result.observations)} observations"
        if source_call is not None:
            fetch_step += f" via {source_call.endpoint.removeprefix(VALET_BASE_URL + '/')}"

        payload: dict[str, Any] = {
            "source": "Bank of Canada",
            "series_name": result.series.name,
            "title": {"en": result.series.label, "fr": french_title},
            "display": localize_title(envelope.enrichment.bilingual_title, lang).to_payload(),
            "total_available": len(result.observations),
            "returned_count": len(records),
            "summary": summary,
            "data": records,
            "citation": citation,
            "lineage": build_lineage(
                publisher=envelope.publisher,
                fetched_at=result.fetched_at,
                upstream_release=envelope.enrichment.release_or_revision_date,
                source_call=source_call,
                steps=(
                    fetch_step,
                    "release timestamp: not published by Valet",
                    _slice_step(
                        summary,
                        returned=len(records),
                        start_date=start_date,
                        end_date=end_date,
                        limit=limit,
                        descending=descending,
                    ),
                ),
            ),
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
        """Guarantee payload strictly complies with the <3KB budget immutably.

        If payload exceeds max_bytes, progressively pops data rows while
        preserving summary statistics and the Two-Tier Citation Envelope.
        """
        clamped = copy.deepcopy(payload)
        encoded_len = len(json.dumps(clamped, default=str).encode("utf-8"))
        if encoded_len <= max_bytes:
            return clamped

        # Payload exceeds budget; truncate data rows
        data = clamped.get("data")
        if isinstance(data, list) and data:
            lineage = clamped.get("lineage")
            if isinstance(lineage, dict) and isinstance(lineage.get("steps"), tuple | list):
                # Recorded before the loop so the extra bytes are inside the budget check.
                lineage["steps"] = [*lineage["steps"], TRUNCATION_STEP]
            truncated_data: list[Any] = list(data)
            while truncated_data and encoded_len > max_bytes:
                truncated_data.pop()
                clamped["data"] = truncated_data
                clamped["returned_count"] = len(truncated_data)
                clamped["truncated"] = True
                encoded_len = len(json.dumps(clamped, default=str).encode("utf-8"))

        # If metadata alone still exceeds max_bytes, clamp metadata strings deterministically
        if encoded_len > max_bytes:
            clamped["data"] = []
            clamped["returned_count"] = 0
            clamped["truncated"] = True
            for field in ["title", "citation", "summary"]:
                if field in clamped and isinstance(clamped[field], dict):
                    for subk, subv in clamped[field].items():
                        if isinstance(subv, str) and len(subv) > 80:
                            clamped[field][subk] = subv[:80] + "..."
            encoded_len = len(json.dumps(clamped, default=str).encode("utf-8"))

        return clamped
