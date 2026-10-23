"""Unit tests for the FastMCP 2.0 Server (CAN-13)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

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
    ValetClient,
)
from candata_mcp.connectors.statcan_wds import (
    Observation as StatCanObservation,
)
from candata_mcp.connectors.statcan_wds import (
    StatCanClient,
    StatCanSeriesResult,
)
from candata_mcp.engine import MAX_PAYLOAD_BYTES, DuckDBSlicingEngine
from candata_mcp.server import CanDataServer, create_server


@pytest.fixture
def mock_statcan_result() -> StatCanSeriesResult:
    obs = tuple(
        StatCanObservation(
            ref_per=f"2024-{m:02d}",
            value=150.0 + m,
            decimals=1,
            release_time=f"2024-{m:02d}-15T08:30",
            scalar_factor_code=0,
            frequency_code=6,
        )
        for m in range(1, 13)
    )
    citation = CitationEnvelope(
        publisher="Statistics Canada",
        core=CoreVerificationTuple(
            table_id="18-10-0004",
            vector_id="v41690973",
            reference_period="2024-01/2024-12",
        ),
        enrichment=MetadataEnrichment(
            coordinate="2.1",
            release_or_revision_date="2024-12-15",
            bilingual_title=BilingualTitle(
                en="Consumer Price Index, shelter",
                fr="Indice des prix à la consommation, logement",
            ),
            canonical_url="https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810000401",
        ),
    )
    result = MagicMock(spec=StatCanSeriesResult)
    result.product_id = 18100004
    result.vector_id = 41690973
    result.coordinate = "2.1"
    result.title_en = "Consumer Price Index, shelter"
    result.title_fr = "Indice des prix à la consommation, logement"
    result.unit = "2002=100"
    result.observations = obs
    result.citation.return_value = citation
    result.fetched_at = "Thu, 22 Oct 2026 19:00:00 GMT"
    return result


@pytest.fixture
def mock_valet_result() -> ObservationSet:
    obs = tuple(
        ValetObservation(
            date=f"2024-{m:02d}-01",
            value=5.0 - (m * 0.25),
        )
        for m in range(1, 13)
    )
    citation = CitationEnvelope(
        publisher="Bank of Canada",
        core=CoreVerificationTuple(
            table_id="10-10-0139",
            vector_id="V39079",
            reference_period="2024-01-01/2024-12-01",
        ),
        enrichment=MetadataEnrichment(
            coordinate=None,
            release_or_revision_date="2024-12-01",
            bilingual_title=BilingualTitle(
                en="Policy Interest Rate",
                fr="Taux cible du financement à un jour",
            ),
            canonical_url="https://www.bankofcanada.ca/valet/observations/V39079/json",
        ),
    )
    series = SeriesDetail(
        name="V39079",
        label="Policy Interest Rate",
        description="Target for the overnight rate",
        frequency="M",
        unit="%",
        date_format="YYYY-MM-DD",
        url="https://www.bankofcanada.ca/valet/series/V39079/json",
    )
    result = MagicMock(spec=ObservationSet)
    result.series = series
    result.observations = obs
    result.citation.return_value = citation
    result.fetched_at = "Thu, 22 Oct 2026 19:00:00 GMT"
    return result


@pytest.fixture
def mock_server(
    mock_statcan_result: StatCanSeriesResult,
    mock_valet_result: ObservationSet,
) -> CanDataServer:
    statcan = MagicMock(spec=StatCanClient)
    statcan.get_data_from_vectors = AsyncMock(return_value=(mock_statcan_result,))
    statcan.get_data_from_cube = AsyncMock(return_value=mock_statcan_result)
    statcan.aclose = AsyncMock()

    valet = MagicMock(spec=ValetClient)
    valet.get_observations = AsyncMock(return_value=mock_valet_result)
    valet.get_policy_rate = AsyncMock(return_value=mock_valet_result)
    valet.get_cpi = AsyncMock(return_value=mock_valet_result)
    valet.aclose = AsyncMock()

    engine = DuckDBSlicingEngine()
    return create_server(statcan_client=statcan, valet_client=valet, engine=engine)


async def test_tool_registration_and_annotations(mock_server: CanDataServer) -> None:
    tools = await mock_server.mcp.list_tools()
    tool_map = {t.name: t for t in tools}

    expected_tools = {
        "query_statcan_vector",
        "query_statcan_coordinate",
        "query_valet_series",
        "query_valet_policy_rate",
        "query_valet_cpi",
        "execute_sql_analytics",
    }
    assert set(tool_map.keys()) == expected_tools

    # Check 2026 Tool Annotations
    for name in [
        "query_statcan_vector",
        "query_statcan_coordinate",
        "query_valet_series",
        "query_valet_policy_rate",
        "query_valet_cpi",
    ]:
        annotations = tool_map[name].annotations
        assert annotations is not None
        assert annotations.read_only_hint is True
        assert annotations.idempotent_hint is True
        assert annotations.open_world_hint is True

    # Local analytic tool
    analytic_annotations = tool_map["execute_sql_analytics"].annotations
    assert analytic_annotations is not None
    assert analytic_annotations.read_only_hint is True
    assert analytic_annotations.idempotent_hint is True
    assert analytic_annotations.open_world_hint is False


async def test_call_query_statcan_vector(mock_server: CanDataServer) -> None:
    result = await mock_server.mcp.call_tool(
        "query_statcan_vector",
        {"vector_id": "v41690973", "limit": 6},
    )
    assert not result.is_error
    assert len(result.content) == 1

    payload = json.loads(result.content[0].text)  # type: ignore[union-attr]
    assert payload["source"] == "Statistics Canada"
    assert payload["vector_id"] == "v41690973"
    assert payload["returned_count"] == 6
    assert len(payload["data"]) == 6
    assert payload["citation"]["core"]["table_id"] == "18-10-0004"
    assert len(result.content[0].text.encode("utf-8")) < MAX_PAYLOAD_BYTES  # type: ignore[union-attr]


async def test_call_query_statcan_coordinate(mock_server: CanDataServer) -> None:
    result = await mock_server.mcp.call_tool(
        "query_statcan_coordinate",
        {"table_id": "18-10-0004-01", "coordinate": "2.1", "limit": 3},
    )
    assert not result.is_error
    payload = json.loads(result.content[0].text)  # type: ignore[union-attr]
    assert payload["coordinate"] == "2.1"
    assert payload["returned_count"] == 3


async def test_call_query_valet_series(mock_server: CanDataServer) -> None:
    result = await mock_server.mcp.call_tool(
        "query_valet_series",
        {"series_name": "V39079", "limit": 4},
    )
    assert not result.is_error
    payload = json.loads(result.content[0].text)  # type: ignore[union-attr]
    assert payload["source"] == "Bank of Canada"
    assert payload["series_name"] == "V39079"
    assert payload["returned_count"] == 4
    assert len(result.content[0].text.encode("utf-8")) < MAX_PAYLOAD_BYTES  # type: ignore[union-attr]


async def test_call_query_valet_policy_rate(mock_server: CanDataServer) -> None:
    result = await mock_server.mcp.call_tool(
        "query_valet_policy_rate",
        {"limit": 5},
    )
    assert not result.is_error
    payload = json.loads(result.content[0].text)  # type: ignore[union-attr]
    assert payload["series_name"] == "V39079"
    assert payload["returned_count"] == 5
    assert payload["citation"]["publisher"] == "Bank of Canada"


async def test_call_query_valet_cpi(mock_server: CanDataServer) -> None:
    result = await mock_server.mcp.call_tool(
        "query_valet_cpi",
        {"measure": "trim", "limit": 6},
    )
    assert not result.is_error
    payload = json.loads(result.content[0].text)  # type: ignore[union-attr]
    assert payload["source"] == "Bank of Canada"


async def test_call_execute_sql_analytics_statcan(mock_server: CanDataServer) -> None:
    result = await mock_server.mcp.call_tool(
        "execute_sql_analytics",
        {
            "source": "statcan",
            "series_id": "v41690973",
            "sql_query": (
                "SELECT count(*) AS total_rows, max(value) - min(value) AS diff FROM series"
            ),
        },
    )
    assert not result.is_error
    payload = json.loads(result.content[0].text)  # type: ignore[union-attr]
    assert payload["row_count"] == 1
    assert payload["data"][0]["total_rows"] == 12
    assert round(payload["data"][0]["diff"], 1) == 11.0
    assert "citation" in payload


async def test_call_execute_sql_analytics_valet(mock_server: CanDataServer) -> None:
    result = await mock_server.mcp.call_tool(
        "execute_sql_analytics",
        {
            "source": "valet",
            "series_id": "V39079",
            "sql_query": "SELECT avg(value) AS average_rate FROM series",
        },
    )
    assert not result.is_error
    payload = json.loads(result.content[0].text)  # type: ignore[union-attr]
    assert payload["row_count"] == 1
    assert payload["data"][0]["average_rate"] > 0


async def test_call_execute_sql_analytics_security_block(mock_server: CanDataServer) -> None:
    result = await mock_server.mcp.call_tool(
        "execute_sql_analytics",
        {
            "source": "statcan",
            "series_id": "v41690973",
            "sql_query": "DELETE FROM series",
        },
    )
    assert not result.is_error
    payload = json.loads(result.content[0].text)  # type: ignore[union-attr]
    assert "error" in payload
    assert "read-only" in payload["error"].lower() or "forbidden" in payload["error"].lower()


async def test_server_aclose(mock_server: CanDataServer) -> None:
    await mock_server.aclose()
    mock_server.statcan_client.aclose.assert_awaited_once()  # type: ignore[union-attr]
    mock_server.valet_client.aclose.assert_awaited_once()  # type: ignore[union-attr]


async def test_statcan_vector_supports_french_and_reports_its_lineage(
    mock_server: CanDataServer,
) -> None:
    result = await mock_server.mcp.call_tool(
        "query_statcan_vector", {"vector_id": "v41690973", "limit": 6, "lang": "fr"}
    )
    payload = json.loads(result.content[0].text)  # type: ignore[union-attr]
    assert payload["display"]["title"] == "Indice des prix à la consommation, logement"
    assert payload["display"]["language"] == "fr"
    assert payload["lineage"]["source_call"] == {
        "endpoint": "https://www150.statcan.gc.ca/t1/wds/rest/getDataFromVectorsAndLatestNPeriods",
        "request": {"vectorId": 41690973, "latestN": 12},
    }
    assert payload["lineage"]["fetched_at"] == "Thu, 22 Oct 2026 19:00:00 GMT"


async def test_statcan_coordinate_lineage_uses_the_normalised_ids(
    mock_server: CanDataServer,
) -> None:
    result = await mock_server.mcp.call_tool(
        "query_statcan_coordinate",
        {"table_id": "18-10-0004-01", "coordinate": "2.1", "limit": 3},
    )
    payload = json.loads(result.content[0].text)  # type: ignore[union-attr]
    assert payload["lineage"]["source_call"]["request"] == {
        "productId": 18100004,
        "coordinate": "2.1",
        "latestN": 12,
    }
    assert payload["display"]["language"] == "en"


@pytest.mark.parametrize(
    ("tool", "args", "recent"),
    [
        ("query_valet_series", {"series_name": "V39079", "limit": 4}, 24),
        ("query_valet_policy_rate", {}, 20),
        ("query_valet_cpi", {"measure": "trim"}, 24),
    ],
)
async def test_valet_tools_report_the_request_they_sent(
    mock_server: CanDataServer, tool: str, args: dict[str, object], recent: int
) -> None:
    result = await mock_server.mcp.call_tool(tool, {**args, "lang": "fr"})
    payload = json.loads(result.content[0].text)  # type: ignore[union-attr]
    assert payload["display"]["title"] == "Taux cible du financement à un jour"
    assert payload["lineage"]["source_call"] == {
        "endpoint": "https://www.bankofcanada.ca/valet/observations/V39079/json",
        "request": {"recent": recent},
    }


async def test_valet_date_range_request_omits_recent(mock_server: CanDataServer) -> None:
    result = await mock_server.mcp.call_tool(
        "query_valet_series", {"series_name": "V39079", "start_date": "2024-01-01"}
    )
    payload = json.loads(result.content[0].text)  # type: ignore[union-attr]
    assert payload["lineage"]["source_call"]["request"] == {"start_date": "2024-01-01"}


@pytest.mark.parametrize(
    ("tool", "args"),
    [
        ("query_statcan_vector", {"vector_id": "v41690973"}),
        ("query_statcan_coordinate", {"table_id": "18-10-0004-01", "coordinate": "2.1"}),
        ("query_valet_series", {"series_name": "V39079"}),
        ("query_valet_policy_rate", {}),
        ("query_valet_cpi", {}),
    ],
)
async def test_unsupported_language_fails_before_any_upstream_call(
    mock_server: CanDataServer, tool: str, args: dict[str, object]
) -> None:
    result = await mock_server.mcp.call_tool(tool, {**args, "lang": "de"})
    payload = json.loads(result.content[0].text)  # type: ignore[union-attr]
    assert "Unsupported language 'de'" in payload["error"]
    mock_server.statcan_client.get_data_from_vectors.assert_not_called()  # type: ignore[attr-defined]
    mock_server.statcan_client.get_data_from_cube.assert_not_called()  # type: ignore[attr-defined]
    mock_server.valet_client.get_observations.assert_not_called()  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("source", "series_id", "request_params", "publisher"),
    [
        ("statcan", "v41690973", {"vectorId": 41690973, "latestN": 100}, "Statistics Canada"),
        ("valet", "V39079", {"recent": 100}, "Bank of Canada"),
    ],
)
async def test_sql_analytics_records_how_the_numbers_were_derived(
    mock_server: CanDataServer,
    source: str,
    series_id: str,
    request_params: dict[str, int],
    publisher: str,
) -> None:
    result = await mock_server.mcp.call_tool(
        "execute_sql_analytics",
        {
            "source": source,
            "series_id": series_id,
            "sql_query": "SELECT avg(value) AS m FROM series",
        },
    )
    payload = json.loads(result.content[0].text)  # type: ignore[union-attr]
    lineage = payload["lineage"]
    assert lineage["publisher"] == publisher
    assert lineage["source_call"]["request"] == request_params
    assert lineage["steps"][0] == "fetched 12 observations"
    assert lineage["steps"][1].startswith("computed in DuckDB with the read-only SQL shown")
    assert len(result.content[0].text.encode("utf-8")) < MAX_PAYLOAD_BYTES  # type: ignore[union-attr]
