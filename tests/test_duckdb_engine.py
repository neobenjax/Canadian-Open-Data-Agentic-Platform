"""Unit tests for the DuckDB Arrow in-memory slicing engine (CAN-13)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import duckdb
import pytest

from candata_mcp.citation import (
    BilingualTitle,
    CitationEnvelope,
    CoreVerificationTuple,
    MetadataEnrichment,
)
from candata_mcp.connectors.boc_valet import (
    Observation as ValetObservation,
)
from candata_mcp.connectors.boc_valet import (
    ObservationSet,
    SeriesDetail,
)
from candata_mcp.connectors.statcan_wds import (
    Observation as StatCanObservation,
)
from candata_mcp.connectors.statcan_wds import (
    StatCanSeriesResult,
)
from candata_mcp.engine import MAX_PAYLOAD_BYTES, DuckDBSlicingEngine


@pytest.fixture
def engine() -> DuckDBSlicingEngine:
    return DuckDBSlicingEngine()


@pytest.fixture
def sample_statcan_result() -> StatCanSeriesResult:
    obs = tuple(
        StatCanObservation(
            ref_per=f"2024-{m:02d}",
            value=100.0 + m,
            decimals=1,
            release_time=f"2024-{m:02d}-15T08:30",
            scalar_factor_code=0,
            frequency_code=6,
        )
        for m in range(1, 13)
    )
    mock_citation = CitationEnvelope(
        publisher="Statistics Canada",
        core=CoreVerificationTuple(
            table_id="18-10-0004",
            vector_id="v41690973",
            reference_period="2024-01/2024-12",
        ),
        enrichment=MetadataEnrichment(
            coordinate="2.1",
            release_or_revision_date="2024-12-15",
            bilingual_title=BilingualTitle(en="Consumer Price Index", fr="Indice des prix"),
            canonical_url="https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810000401",
        ),
    )
    result = MagicMock(spec=StatCanSeriesResult)
    result.product_id = 18100004
    result.vector_id = 41690973
    result.coordinate = "2.1"
    result.title_en = "Consumer Price Index"
    result.title_fr = "Indice des prix"
    result.unit = "2002=100"
    result.observations = obs
    result.citation.return_value = mock_citation
    result.fetched_at = "Thu, 22 Oct 2026 19:00:00 GMT"
    return result


@pytest.fixture
def sample_valet_result() -> ObservationSet:
    obs = tuple(
        ValetObservation(
            date=f"2024-{m:02d}-01",
            value=4.5 - (m * 0.1),
        )
        for m in range(1, 13)
    )
    mock_citation = CitationEnvelope(
        publisher="Bank of Canada",
        core=CoreVerificationTuple(
            table_id="10-10-0139",
            vector_id="V39079",
            reference_period="2024-01-01/2024-12-01",
        ),
        enrichment=MetadataEnrichment(
            coordinate=None,
            release_or_revision_date="2024-12-01",
            bilingual_title=BilingualTitle(en="Policy Interest Rate", fr="Taux directeur"),
            canonical_url="https://www.bankofcanada.ca/valet/observations/V39079/json",
        ),
    )
    series = SeriesDetail(
        name="V39079",
        label="Policy Interest Rate",
        description="Target rate",
        frequency="M",
        unit="%",
        date_format="YYYY-MM-DD",
        url="https://www.bankofcanada.ca/valet/series/V39079/json",
    )
    result = MagicMock(spec=ObservationSet)
    result.series = series
    result.observations = obs
    result.citation.return_value = mock_citation
    result.fetched_at = "Thu, 22 Oct 2026 19:00:00 GMT"
    return result


def test_statcan_table_conversion_and_slicing(
    engine: DuckDBSlicingEngine,
    sample_statcan_result: StatCanSeriesResult,
) -> None:
    table = engine.table_from_statcan(sample_statcan_result)
    assert table.num_rows == 12
    assert "date" in table.column_names
    assert "value" in table.column_names

    # Slicing with limit and date range
    records, summary = engine.slice_table(
        table,
        start_date="2024-03",
        end_date="2024-06",
        limit=5,
        descending=False,
    )
    assert len(records) == 4
    assert records[0]["date"] == "2024-03"
    assert records[-1]["date"] == "2024-06"
    assert summary["filtered_count"] == 4
    assert summary["min_date"] == "2024-03"
    assert summary["max_date"] == "2024-06"
    assert summary["min_value"] == 103.0
    assert summary["max_value"] == 106.0


def test_valet_slice_payload_formatting(
    engine: DuckDBSlicingEngine,
    sample_valet_result: ObservationSet,
) -> None:
    payload = engine.slice_valet(
        sample_valet_result,
        start_date="2024-01-01",
        limit=3,
        descending=True,
    )

    assert payload["source"] == "Bank of Canada"
    assert payload["series_name"] == "V39079"
    assert payload["returned_count"] == 3
    assert len(payload["data"]) == 3
    assert payload["citation"]["publisher"] == "Bank of Canada"
    assert payload["citation"]["core"]["vector_id"] == "V39079"

    # Verify payload size is well below 3KB
    encoded_len = len(json.dumps(payload).encode("utf-8"))
    assert encoded_len < MAX_PAYLOAD_BYTES


def test_payload_clamp_budget_enforcement(engine: DuckDBSlicingEngine) -> None:
    # Construct a synthetic result with 500 records
    large_data = [
        {"date": f"2020-01-{i:03d}", "value": 100.55 + i, "note": "extended description" * 5}
        for i in range(500)
    ]
    payload = {
        "source": "Statistics Canada",
        "vector_id": "v12345",
        "returned_count": 500,
        "summary": {"count": 500, "min_date": "2020-01-000", "max_date": "2020-01-499"},
        "data": large_data,
        "citation": {"publisher": "Statistics Canada", "core": {}, "enrichment": {}},
    }

    raw_len = len(json.dumps(payload).encode("utf-8"))
    assert raw_len > MAX_PAYLOAD_BYTES

    clamped = engine.clamp_payload(payload, max_bytes=MAX_PAYLOAD_BYTES)
    clamped_len = len(json.dumps(clamped).encode("utf-8"))

    assert clamped_len <= MAX_PAYLOAD_BYTES
    assert clamped.get("truncated") is True
    assert len(clamped["data"]) < 500
    assert "summary" in clamped
    assert "citation" in clamped


def test_payload_clamp_immutability(engine: DuckDBSlicingEngine) -> None:
    original_data = [{"date": "2024-01-01", "value": 1.0}, {"date": "2024-01-02", "value": 2.0}]
    payload = {
        "source": "Statistics Canada",
        "data": original_data,
        "returned_count": 2,
    }
    # Force truncation with small max_bytes
    clamped = engine.clamp_payload(payload, max_bytes=50)
    assert clamped is not payload
    assert len(payload["data"]) == 2  # Original remains unmutated


def test_invalid_date_format_rejection(
    engine: DuckDBSlicingEngine,
    sample_valet_result: ObservationSet,
) -> None:
    table = engine.table_from_valet(sample_valet_result)
    with pytest.raises(ValueError, match="Invalid date format"):
        engine.slice_table(table, start_date="bad-date-format")


def test_execute_analytics_query(
    engine: DuckDBSlicingEngine,
    sample_statcan_result: StatCanSeriesResult,
) -> None:
    table = engine.table_from_statcan(sample_statcan_result)
    sql = "SELECT max(value) - min(value) AS spread, avg(value) AS mean FROM series"
    results = engine.execute_analytics(table, sql)

    assert len(results) == 1
    assert round(results[0]["spread"], 1) == 11.0
    assert results[0]["mean"] > 100.0


def test_execute_analytics_security_guardrails(
    engine: DuckDBSlicingEngine,
    sample_statcan_result: StatCanSeriesResult,
) -> None:
    table = engine.table_from_statcan(sample_statcan_result)

    # Rejects non-SELECT queries
    with pytest.raises(ValueError, match="Only read-only SELECT or WITH"):
        engine.execute_analytics(table, "DROP TABLE series")

    # Rejects forbidden keywords
    with pytest.raises(ValueError, match="forbidden SQL"):
        engine.execute_analytics(table, "SELECT * FROM series; DELETE FROM series")


def test_duckdb_sandbox_blocks_filesystem_access(
    engine: DuckDBSlicingEngine,
    sample_statcan_result: StatCanSeriesResult,
) -> None:
    """Security probe test: verify in-memory sandbox completely forbids file and config access."""
    table = engine.table_from_statcan(sample_statcan_result)

    # Probing read_text should fail with PermissionException
    with pytest.raises(duckdb.PermissionException, match="file system operations are disabled"):
        engine.execute_analytics(table, "SELECT * FROM read_text('pyproject.toml')")

    # Probing read_csv should fail with PermissionException
    with pytest.raises(duckdb.PermissionException, match="file system operations are disabled"):
        engine.execute_analytics(table, "SELECT * FROM read_csv('pyproject.toml')")

    # Probing glob should fail with PermissionException
    with pytest.raises(duckdb.PermissionException, match="file system operations are disabled"):
        engine.execute_analytics(table, "SELECT file FROM glob('*')")

    # Non-SELECT statements are rejected by query parser
    with pytest.raises(ValueError, match="Only read-only SELECT or WITH"):
        engine.execute_analytics(table, "SET enable_external_access=true")

    # If executed directly on underlying connection, configuration is locked
    with pytest.raises(duckdb.InvalidInputException, match="the configuration has been locked"):
        engine.connection.execute("SET enable_external_access=true")


def test_date_boundary_normalization_includes_own_period(
    engine: DuckDBSlicingEngine,
    sample_statcan_result: StatCanSeriesResult,
) -> None:
    """Verify that end_date='2024' includes all 12 months of 2024 (avoiding period drop)."""
    table = engine.table_from_statcan(sample_statcan_result)

    # End date as year YYYY should include all 2024 records
    records, summary = engine.slice_table(table, end_date="2024", limit=100)
    assert len(records) == 12
    assert summary["filtered_count"] == 12

    # Matching start_date and end_date on same year
    records, summary = engine.slice_table(table, start_date="2024", end_date="2024", limit=100)
    assert len(records) == 12

    # Month boundary: end_date='2024-06' should include 2024-01 through 2024-06
    records, summary = engine.slice_table(table, end_date="2024-06", limit=100, descending=False)
    assert len(records) == 6
    assert records[-1]["date"] == "2024-06"


def test_date_range_diagnostic_note_when_preceding_window(
    engine: DuckDBSlicingEngine,
    sample_statcan_result: StatCanSeriesResult,
) -> None:
    """Verify diagnostic note is returned when requested range precedes earliest observation."""
    table = engine.table_from_statcan(sample_statcan_result)

    # Requesting start_date='2010' against 2024 data
    records, summary = engine.slice_table(table, start_date="2010", end_date="2012")
    assert len(records) == 0
    assert "data_window_note" in summary
    assert "precedes earliest fetched observation" in summary["data_window_note"]


def test_statcan_table_preserves_status_code_symbol_code_and_metadata(
    engine: DuckDBSlicingEngine,
) -> None:
    """Guardrail 6: Quality flags (statusCode/symbolCode) and provenance must not be dropped."""
    obs = (
        StatCanObservation(
            ref_per="2025-07-01",
            value=None,
            decimals=0,
            release_time="2025-08-15T08:30",
            scalar_factor_code=0,
            frequency_code=6,
            status_code=1,  # suppressed / missing
            symbol_code=0,
        ),
        StatCanObservation(
            ref_per="2025-08-01",
            value=2500.0,
            decimals=1,
            release_time="2025-09-15T08:30",
            scalar_factor_code=0,
            frequency_code=6,
            status_code=0,
            symbol_code=2,  # use with caution
        ),
    )
    res = MagicMock(spec=StatCanSeriesResult)
    res.product_id = 34100143
    res.coordinate = "125.1.0.0.0.0.0.0.0.0"
    res.vector_id = 729961
    res.title_en = "Housing starts"
    res.title_fr = None
    res.unit = "Units"
    res.series_title_en = "Toronto, Ontario; Total units"
    res.series_title_fr = None
    res.observations = obs

    table = engine.table_from_statcan(res)
    assert "status_code" in table.column_names
    assert "symbol_code" in table.column_names
    assert table.schema.metadata[b"vector_id"] == b"729961"
    assert table.schema.metadata[b"product_id"] == b"34100143"
    assert table.schema.metadata[b"unit"] == b"Units"
    assert table.schema.metadata[b"series_title_en"] == b"Toronto, Ontario; Total units"

    records, _ = engine.slice_table(table, limit=10)
    assert len(records) == 2
    row0 = next(r for r in records if r["date"] == "2025-07-01")
    assert row0["status_code"] == 1
    assert row0["value"] is None
    row1 = next(r for r in records if r["date"] == "2025-08-01")
    assert row1["symbol_code"] == 2
    assert row1["value"] == 2500.0


def test_statcan_slice_includes_series_title_and_unit(
    engine: DuckDBSlicingEngine,
) -> None:
    """Query response payloads must include series_title and unit for benchmark fidelity."""
    obs = (
        StatCanObservation(
            ref_per="2024-01-01",
            value=105000.0,
            decimals=0,
            release_time="2024-06-15T08:30",
            scalar_factor_code=0,
            frequency_code=12,
            status_code=0,
            symbol_code=0,
        ),
    )
    envelope = CitationEnvelope(
        publisher="Statistics Canada",
        core=CoreVerificationTuple(
            table_id="11-10-0190-01",
            vector_id="v123456",
            reference_period="2024",
        ),
        enrichment=MetadataEnrichment(
            coordinate="125.1",
            release_or_revision_date="2024-06-15T08:30",
            bilingual_title=BilingualTitle(
                en="Income — Toronto, Ontario; Median income",
                fr="Revenu",
            ),
            canonical_url="https://statcan.gc.ca",
        ),
    )
    res = MagicMock(spec=StatCanSeriesResult)
    res.product_id = 11100190
    res.coordinate = "125.1"
    res.vector_id = 123456
    res.title_en = "Income"
    res.title_fr = "Revenu"
    res.unit = "2024 constant dollars"
    res.unit_code = 455
    res.series_title_en = "Toronto, Ontario; Median income"
    res.series_title_fr = "Toronto, Ontario; Revenu median"
    res.observations = obs
    res.fetched_at = "2026-10-29T10:00:00Z"
    res.citation.return_value = envelope

    table = engine.table_from_statcan(res)
    assert table.schema.metadata[b"unit_code"] == b"455"

    payload = engine.slice_statcan(res)
    assert payload["unit"] == "2024 constant dollars"
    assert payload["unit_code"] == 455
    assert payload["series_title"]["en"] == "Toronto, Ontario; Median income"
    assert payload["data"][0]["status_code"] == 0
