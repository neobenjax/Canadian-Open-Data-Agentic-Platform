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
from candata_mcp.engine import (
    MAX_PAYLOAD_BYTES,
    DuckDBSecurityError,
    DuckDBSlicingEngine,
    validate_and_lock_connection,
)


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


def test_table_from_ckan_and_slice_ckan(engine: DuckDBSlicingEngine) -> None:
    from candata_mcp.connectors.ckan_open_canada import (
        CKANDataStoreResult,
        CKANFieldSchema,
    )

    fields = (
        CKANFieldSchema(field_id="id", field_type="int"),
        CKANFieldSchema(field_id="city", field_type="text"),
        CKANFieldSchema(field_id="starts", field_type="numeric"),
    )
    records = tuple({"id": i, "city": f"City {i}", "starts": 100.0 * i} for i in range(1, 15))
    res = CKANDataStoreResult(
        resource_id="res-12345",
        package_id="pkg-cmhc-starts",
        title_en="Urban Housing Starts",
        title_fr="Mises en chantier urbaines",
        publisher_en="Open Government Canada / CMHC",
        fields=fields,
        records=records,
        total_records=14,
        release_or_revision_date="2026-01-15T12:00:00",
        fetched_at="2026-10-29T10:00:00Z",
    )

    table = engine.table_from_ckan(res)
    assert table.num_rows == 14
    assert table.schema.metadata[b"resource_id"] == b"res-12345"
    assert table.schema.metadata[b"package_id"] == b"pkg-cmhc-starts"

    # Test slice_ckan
    payload = engine.slice_ckan(res, limit=5)
    assert payload["returned_count"] == 5
    assert len(payload["data"]) == 5
    assert payload["total_available"] == 14
    assert payload["citation"]["core"]["table_id"] == "pkg-cmhc-starts"
    assert payload["citation"]["core"]["vector_id"] == "res-12345"
    assert len(json.dumps(payload, default=str).encode("utf-8")) <= MAX_PAYLOAD_BYTES

    # Test execute_analytics on CKAN table
    sql = "SELECT avg(starts) as mean_starts FROM series"
    analytics = engine.execute_analytics(table, sql)
    assert len(analytics) == 1
    assert analytics[0]["mean_starts"] > 0


# ==============================================================================
# Issue #20 (CAN-TECH-DEBT): Driver-Level Sandbox Lockdown on Caller Connections
# ==============================================================================


def test_caller_supplied_unlocked_connection_is_automatically_locked_down(
    sample_statcan_result: StatCanSeriesResult,
) -> None:
    """An unlocked in-memory DuckDB connection is automatically locked down (Rule 7)."""
    raw_con = duckdb.connect(":memory:")

    # Verify connection starts unlocked
    before_settings = dict(
        raw_con.execute(
            "SELECT name, value FROM duckdb_settings() "
            "WHERE name IN ('enable_external_access', 'lock_configuration')"
        ).fetchall()
    )
    assert before_settings.get("enable_external_access") == "true"
    assert before_settings.get("lock_configuration") == "false"

    # Pass into DuckDBSlicingEngine
    engine = DuckDBSlicingEngine(connection=raw_con)

    # Verify connection is now fully locked down
    after_settings = dict(
        engine.connection.execute(
            "SELECT name, value FROM duckdb_settings() "
            "WHERE name IN ('enable_external_access', 'lock_configuration')"
        ).fetchall()
    )
    assert after_settings.get("enable_external_access") == "false"
    assert after_settings.get("lock_configuration") == "true"

    table = engine.table_from_statcan(sample_statcan_result)

    # Verify table functions that access filesystem are blocked
    with pytest.raises(duckdb.PermissionException, match="file system operations are disabled"):
        engine.execute_analytics(table, "SELECT * FROM read_text('pyproject.toml')")

    with pytest.raises(duckdb.PermissionException, match="file system operations are disabled"):
        engine.execute_analytics(table, "SELECT * FROM read_csv('pyproject.toml')")

    with pytest.raises(duckdb.PermissionException, match="file system operations are disabled"):
        engine.execute_analytics(table, "SELECT file FROM glob('*')")

    # Verify driver-level lock blocks runtime tampering
    with pytest.raises(duckdb.InvalidInputException, match="the configuration has been locked"):
        raw_con.execute("SET enable_external_access = true")

    # Verify engine can still perform normal analytical slicing
    records, summary = engine.slice_table(table, limit=3)
    assert len(records) == 3
    assert summary["filtered_count"] == 12


def test_caller_supplied_prelocked_safe_connection_accepted(
    sample_statcan_result: StatCanSeriesResult,
) -> None:
    """Pre-configured safe connection is accepted without re-executing locked SET statements."""
    safe_con = duckdb.connect(
        ":memory:",
        config={
            "enable_external_access": False,
            "lock_configuration": True,
        },
    )
    # Direct validate_and_lock_connection call
    validated = validate_and_lock_connection(safe_con)
    assert validated is safe_con

    engine = DuckDBSlicingEngine(connection=safe_con)
    assert engine.connection is safe_con

    table = engine.table_from_statcan(sample_statcan_result)
    records, _ = engine.slice_table(table, limit=2)
    assert len(records) == 2


def test_caller_supplied_locked_unsafe_connection_fails_loud() -> None:
    """A connection pre-locked with enable_external_access=True cannot be secured."""
    unsafe_locked_con = duckdb.connect(
        ":memory:",
        config={
            "enable_external_access": True,
            "lock_configuration": True,
        },
    )
    with pytest.raises(
        DuckDBSecurityError,
        match="locked with enable_external_access=True",
    ):
        DuckDBSlicingEngine(connection=unsafe_locked_con)


def test_caller_supplied_file_backed_database_fails_loud(
    tmp_path: pytest.TempPathFactory,
) -> None:
    """A caller-supplied connection to an on-disk database violates Rule 7 and must fail loud."""
    db_path = str(tmp_path) + "/test_disk.duckdb"
    disk_con = duckdb.connect(db_path)
    try:
        with pytest.raises(
            DuckDBSecurityError,
            match="file-backed database.*Rule 7 requires in-memory only",
        ):
            DuckDBSlicingEngine(connection=disk_con)
    finally:
        disk_con.close()


def test_caller_supplied_attached_file_database_fails_loud(
    tmp_path: pytest.TempPathFactory,
) -> None:
    """A connection with an attached file-backed database violates Rule 7 and must fail loud."""
    attached_path = str(tmp_path) + "/attached.duckdb"
    con = duckdb.connect(":memory:")
    con.execute(f"ATTACH '{attached_path}' AS external_store")
    try:
        with pytest.raises(
            DuckDBSecurityError,
            match="file-backed database.*Rule 7 requires in-memory only",
        ):
            DuckDBSlicingEngine(connection=con)
    finally:
        con.close()


def test_caller_supplied_invalid_connection_type_rejected() -> None:
    """Supplying non-duckdb connection objects raises TypeError."""
    with pytest.raises(TypeError, match="expected duckdb.DuckDBPyConnection, got str"):
        DuckDBSlicingEngine(connection="not_a_connection")  # pyright: ignore[reportArgumentType]

    with pytest.raises(TypeError, match="expected duckdb.DuckDBPyConnection, got dict"):
        DuckDBSlicingEngine(connection={"connection": True})  # pyright: ignore[reportArgumentType]


def test_caller_supplied_closed_connection_fails_loud() -> None:
    """Supplying a closed connection raises DuckDBSecurityError."""
    closed_con = duckdb.connect(":memory:")
    closed_con.close()
    with pytest.raises(DuckDBSecurityError, match="unusable or closed"):
        DuckDBSlicingEngine(connection=closed_con)


def test_require_prelocked_mode() -> None:
    """When require_prelocked=True, unlocked connections are rejected even if in-memory."""
    unlocked_con = duckdb.connect(":memory:")
    with pytest.raises(DuckDBSecurityError, match="not pre-locked"):
        DuckDBSlicingEngine(connection=unlocked_con, require_prelocked=True)

    prelocked_con = duckdb.connect(
        ":memory:",
        config={
            "enable_external_access": False,
            "lock_configuration": True,
        },
    )
    engine = DuckDBSlicingEngine(connection=prelocked_con, require_prelocked=True)
    assert engine.connection is prelocked_con


def test_adversarial_queries_blocked_on_caller_supplied_connection(
    sample_statcan_result: StatCanSeriesResult,
) -> None:
    """Adversarial queries (SET, PRAGMA, ATTACH, COPY, table functions) are strictly blocked."""
    raw_con = duckdb.connect(":memory:")
    engine = DuckDBSlicingEngine(connection=raw_con)
    table = engine.table_from_statcan(sample_statcan_result)

    # 1. Blocked via query syntax check / regex defense
    with pytest.raises(ValueError, match="forbidden SQL statements or keywords"):
        engine.execute_analytics(table, "SELECT * FROM series; SET enable_external_access = true")

    with pytest.raises(ValueError, match="forbidden SQL statements or keywords"):
        engine.execute_analytics(
            table, "SELECT * FROM series; PRAGMA enable_external_access = true"
        )

    with pytest.raises(ValueError, match="forbidden SQL statements or keywords"):
        engine.execute_analytics(table, "SELECT * FROM series; ATTACH 'malicious.db'")

    with pytest.raises(ValueError, match="forbidden SQL statements or keywords"):
        engine.execute_analytics(table, "SELECT * FROM series; EXPORT DATABASE 'out'")

    with pytest.raises(ValueError, match="forbidden SQL statements or keywords"):
        engine.execute_analytics(table, "SELECT * FROM series; CHECKPOINT")

    with pytest.raises(ValueError, match="forbidden SQL statements or keywords"):
        engine.execute_analytics(table, "SELECT * FROM series; VACUUM")

    # 2. Blocked via driver-level lockdown on table functions
    with pytest.raises(duckdb.PermissionException, match="file system operations are disabled"):
        engine.execute_analytics(table, "SELECT * FROM read_parquet('test.parquet')")

    with pytest.raises(duckdb.PermissionException, match="file system operations are disabled"):
        engine.execute_analytics(table, "SELECT * FROM read_json('test.json')")

    with pytest.raises(duckdb.PermissionException, match="file system operations are disabled"):
        engine.execute_analytics(table, "SELECT * FROM read_blob('test.bin')")

    # Remote URL / httpfs access is also blocked by driver-level disabled file system operations
    with pytest.raises(duckdb.PermissionException, match="file system operations are disabled"):
        engine.execute_analytics(table, "SELECT * FROM read_csv('http://evil.com/payload.csv')")

    # 3. Direct execution on underlying connection is blocked by configuration lock
    with pytest.raises(duckdb.InvalidInputException, match="the configuration has been locked"):
        engine.connection.execute("SET enable_external_access = true")

    with pytest.raises(duckdb.InvalidInputException, match="the configuration has been locked"):
        engine.connection.execute("PRAGMA enable_external_access = true")

    with pytest.raises(duckdb.PermissionException, match="file system operations are disabled"):
        engine.connection.execute("ATTACH 'steal.db'")


def test_slice_statcan_annual_series_multi_year_range(engine: DuckDBSlicingEngine) -> None:
    """GT-05: Annual series (e.g. v42127955) sliced with 2024 to 2025 returns both years.

    Verifies Rule 8 temporal boundary normalization for annual series (YYYY).
    """
    obs = (
        StatCanObservation(
            ref_per="2023",
            value=25000.0,
            decimals=0,
            release_time="2024-01-15T08:30",
            scalar_factor_code=0,
            frequency_code=1,  # Annual
        ),
        StatCanObservation(
            ref_per="2024",
            value=27800.0,
            decimals=0,
            release_time="2025-01-15T08:30",
            scalar_factor_code=0,
            frequency_code=1,
        ),
        StatCanObservation(
            ref_per="2025",
            value=26087.0,
            decimals=0,
            release_time="2026-01-15T08:30",
            scalar_factor_code=0,
            frequency_code=1,
        ),
    )
    envelope = CitationEnvelope(
        publisher="Statistics Canada",
        core=CoreVerificationTuple(
            table_id="34-10-0134-01",
            vector_id="v42127955",
            reference_period="2025",
        ),
        enrichment=MetadataEnrichment(
            coordinate="1.1",
            release_or_revision_date="2026-01-15T08:30",
            bilingual_title=BilingualTitle(
                en="Housing starts in selected census metropolitan areas",
                fr="Mises en chantier dans certaines régions métropolitaines",
            ),
            canonical_url="https://statcan.gc.ca",
        ),
    )
    res = MagicMock(spec=StatCanSeriesResult)
    res.table_id = "34-10-0134-01"
    res.coordinate = "1.1"
    res.vector_id = 42127955
    res.title_en = "Housing starts"
    res.title_fr = "Mises en chantier"
    res.unit = "Units"
    res.unit_code = 1
    res.series_title_en = "Toronto, Ontario; Housing starts; Total units"
    res.series_title_fr = "Toronto, Ontario; Mises en chantier; Total"
    res.observations = obs
    res.fetched_at = "2026-02-01T10:00:00Z"
    res.citation.return_value = envelope

    # Slicing for both 2024 and 2025
    payload_both = engine.slice_statcan(res, start_date="2024", end_date="2025")
    assert payload_both["returned_count"] == 2
    dates = [row["date"] for row in payload_both["data"]]
    # Data is ordered DESC
    assert dates == ["2025", "2024"]
    values = [row["value"] for row in payload_both["data"]]
    assert values == [26087.0, 27800.0]

    # Slicing only 2025 (e.g. single-period fetch bug) returns only 1
    payload_single = engine.slice_statcan(res, start_date="2025", end_date="2025")
    assert payload_single["returned_count"] == 1
    assert payload_single["data"][0]["date"] == "2025"
    assert payload_single["data"][0]["value"] == 26087.0
