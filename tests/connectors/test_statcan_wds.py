"""Unit and offline integration tests for Statistics Canada WDS client (CAN-11).

Responses are realistic StatCan WDS payloads saved in tests/fixtures/statcan/,
allowing the entire suite to run offline and fast.
Live tests are marked with `@pytest.mark.live` and only run with `pytest -m live`.
"""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from candata_mcp.connectors.statcan_wds import (
    DEFAULT_USER_AGENT,
    STATCAN_LICENCE_URL,
    STATCAN_WDS_BASE_URL,
    CubeSummary,
    StatCanAmbiguousMemberError,
    StatCanClient,
    StatCanHTTPError,
    StatCanMemberNotFoundError,
    StatCanNotFoundError,
    StatCanRequestError,
    StatCanResponseError,
    format_table_id,
    normalize_product_id,
    normalize_vector_id,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "statcan"
DATE_HEADER = "Mon, 19 Oct 2026 22:30:00 GMT"


def fixture(name: str) -> list[dict[str, Any]]:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def ok(name: str) -> httpx.Response:
    return httpx.Response(200, json=fixture(name), headers={"Date": DATE_HEADER})


@pytest.fixture
async def statcan():
    async with StatCanClient(backoff=0) as client:
        yield client


def test_format_table_id_and_normalize_helpers() -> None:
    assert format_table_id(18100004) == "18-10-0004-01"
    assert format_table_id("18100004") == "18-10-0004-01"
    assert format_table_id("3410013001") == "34-10-0130-01"

    assert normalize_vector_id(41690973) == 41690973
    assert normalize_vector_id("v41690973") == 41690973
    assert normalize_vector_id("V41690973") == 41690973

    with pytest.raises(ValueError, match="invalid vector ID"):
        normalize_vector_id("abc")

    with pytest.raises(ValueError, match="invalid vector ID"):
        normalize_vector_id(0)

    assert normalize_product_id(18100004) == 18100004
    assert normalize_product_id("1810000401") == 18100004
    assert normalize_product_id("18-10-0004-01") == 18100004


def test_default_user_agent_format(statcan: StatCanClient) -> None:
    assert "CanDataMCP" in DEFAULT_USER_AGENT
    assert "CAN-11" in DEFAULT_USER_AGENT


@respx.mock
async def test_get_cube_metadata_parses_details_and_dimensions(statcan: StatCanClient) -> None:
    respx.post(f"{STATCAN_WDS_BASE_URL}/getCubeMetadata").mock(
        return_value=ok("cube_metadata_18100004")
    )

    meta = await statcan.get_cube_metadata(18100004)

    assert meta.product_id == 18100004
    assert meta.cansim_id == "326-0020"
    assert meta.title_en == "Consumer Price Index, monthly, not seasonally adjusted"
    assert "prix à la consommation" in (meta.title_fr or "")
    assert meta.frequency_code == 6
    assert meta.frequency_name == "monthly"
    assert meta.release_time == "2026-10-19T08:30"
    assert len(meta.dimensions) >= 2

    geo_dim = meta.dimensions[0]
    assert geo_dim.position_id == 1
    assert geo_dim.name_en == "Geography"
    canada_member = next(m for m in geo_dim.members if m.name_en == "Canada")
    assert canada_member.member_id == 2


@respx.mock
async def test_cube_metadata_caching_and_bypass(statcan: StatCanClient) -> None:
    route = respx.post(f"{STATCAN_WDS_BASE_URL}/getCubeMetadata").mock(
        return_value=ok("cube_metadata_18100004")
    )

    # First call hits network
    meta1 = await statcan.get_cube_metadata(18100004)
    assert route.call_count == 1

    # Second call uses in-memory cache
    meta2 = await statcan.get_cube_metadata(18100004)
    assert route.call_count == 1
    assert meta1.product_id == meta2.product_id

    # Call with bypass_cache hits network again
    await statcan.get_cube_metadata(18100004, bypass_cache=True)
    assert route.call_count == 2

    # Clear cache and verify network call
    statcan.clear_cache()
    await statcan.get_cube_metadata(18100004)
    assert route.call_count == 3


@respx.mock
async def test_resolve_coordinate_success(statcan: StatCanClient) -> None:
    respx.post(f"{STATCAN_WDS_BASE_URL}/getCubeMetadata").mock(
        return_value=ok("cube_metadata_18100004")
    )

    # In 18100004: Dim 1 = Geography (Canada -> memberId 2)
    # Dim 2 = Products (All-items -> memberId 2)
    coord = await statcan.resolve_coordinate(18100004, ["Canada", "All-items"])

    assert coord == "2.2.0.0.0.0.0.0.0.0"
    assert len(coord.split(".")) == 10


@respx.mock
async def test_resolve_coordinate_french_member(statcan: StatCanClient) -> None:
    respx.post(f"{STATCAN_WDS_BASE_URL}/getCubeMetadata").mock(
        return_value=ok("cube_metadata_18100004")
    )

    coord = await statcan.resolve_coordinate(18100004, ["Canada", "Ensemble"])
    assert coord == "2.2.0.0.0.0.0.0.0.0"


@respx.mock
async def test_resolve_coordinate_member_not_found(statcan: StatCanClient) -> None:
    respx.post(f"{STATCAN_WDS_BASE_URL}/getCubeMetadata").mock(
        return_value=ok("cube_metadata_18100004")
    )

    with pytest.raises(StatCanMemberNotFoundError, match="not found in dimension"):
        await statcan.resolve_coordinate(18100004, ["Atlantis", "All-items"])


@respx.mock
async def test_resolve_coordinate_ambiguous_member_raises_error(statcan: StatCanClient) -> None:
    ambiguous_meta = [
        {
            "status": "SUCCESS",
            "object": {
                "productId": 34100133,
                "cubeTitleEn": "Rental Market Survey",
                "frequencyCode": 12,
                "dimension": [
                    {
                        "dimensionPositionId": 1,
                        "dimensionNameEn": "Geography",
                        "member": [
                            {"memberId": 10, "memberNameEn": "Kentville", "parentMemberId": 1},
                            {"memberId": 20, "memberNameEn": "Kentville", "parentMemberId": 2},
                        ],
                    }
                ],
            },
        }
    ]
    respx.post(f"{STATCAN_WDS_BASE_URL}/getCubeMetadata").mock(
        return_value=httpx.Response(200, json=ambiguous_meta, headers={"Date": DATE_HEADER})
    )

    with pytest.raises(StatCanAmbiguousMemberError, match="ambiguous member name 'Kentville'"):
        await statcan.resolve_coordinate(34100133, ["Kentville"])


@respx.mock
async def test_resolve_coordinate_position_out_of_bounds(statcan: StatCanClient) -> None:
    respx.post(f"{STATCAN_WDS_BASE_URL}/getCubeMetadata").mock(
        return_value=ok("cube_metadata_18100004")
    )

    with pytest.raises(StatCanMemberNotFoundError, match="does not exist in table"):
        await statcan.resolve_coordinate(
            18100004, ["Canada", "All-items", "ExtraDim3", "ExtraDim4", "ExtraDim5"]
        )


@respx.mock
async def test_get_data_from_cube_slicing_and_chronological_sort(statcan: StatCanClient) -> None:
    respx.post(f"{STATCAN_WDS_BASE_URL}/getDataFromCubePidCoordAndLatestNPeriods").mock(
        return_value=ok("data_coord_18100004_cpi")
    )
    respx.post(f"{STATCAN_WDS_BASE_URL}/getCubeMetadata").mock(
        return_value=ok("cube_metadata_18100004")
    )

    result = await statcan.get_data_from_cube(18100004, "2.2.0.0.0.0.0.0.0.0", latest_n=2)

    assert result.product_id == 18100004
    assert result.coordinate == "2.2.0.0.0.0.0.0.0.0"
    assert result.vector_id == 41690973
    assert len(result.observations) == 2
    # Verify sorted oldest first
    assert result.observations[0].ref_per == "2026-08-01"
    assert result.observations[0].value == 169.8
    assert result.observations[0].status_code == 0
    assert result.observations[0].symbol_code == 0
    assert result.observations[1].ref_per == "2026-09-01"
    assert result.observations[1].value == 170.0


@respx.mock
async def test_get_data_from_cube_citation_envelope(statcan: StatCanClient) -> None:
    respx.post(f"{STATCAN_WDS_BASE_URL}/getDataFromCubePidCoordAndLatestNPeriods").mock(
        return_value=ok("data_coord_18100004_cpi")
    )
    respx.post(f"{STATCAN_WDS_BASE_URL}/getCubeMetadata").mock(
        return_value=ok("cube_metadata_18100004")
    )

    result = await statcan.get_data_from_cube(18100004, "2.2.0.0.0.0.0.0.0.0", latest_n=2)
    citation = result.citation()

    # Top-level publisher
    assert citation.publisher == "Statistics Canada"

    # Tier 1: Core Verification Tuple
    assert citation.core.table_id == "18-10-0004-01"
    assert citation.core.vector_id == "v41690973"
    assert citation.core.reference_period == "2026-08/2026-09"

    # Tier 2: Metadata Enrichment
    assert citation.enrichment.coordinate == "2.2.0.0.0.0.0.0.0.0"
    assert len(citation.enrichment.coordinate.split(".")) == 10
    assert citation.enrichment.release_or_revision_date == "2026-10-19T08:30"
    assert citation.enrichment.bilingual_title.en == (
        "Consumer Price Index, monthly, not seasonally adjusted"
    )
    assert citation.enrichment.bilingual_title.fr is not None
    assert citation.enrichment.canonical_url == (
        "https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810000401"
    )


@respx.mock
async def test_get_data_from_vectors(statcan: StatCanClient) -> None:
    respx.post(f"{STATCAN_WDS_BASE_URL}/getDataFromVectorsAndLatestNPeriods").mock(
        return_value=ok("data_vector_v41690973")
    )
    respx.post(f"{STATCAN_WDS_BASE_URL}/getCubeMetadata").mock(
        return_value=ok("cube_metadata_18100004")
    )

    results = await statcan.get_data_from_vectors(["v41690973"], latest_n=2)

    assert len(results) == 1
    res = results[0]
    assert res.vector_id == 41690973
    assert res.product_id == 18100004
    assert len(res.observations) == 2
    assert res.observations[-1].value == 170.0


@respx.mock
async def test_get_data_from_cube_rejects_missing_or_zero_vector_id(
    statcan: StatCanClient,
) -> None:
    invalid_data = [
        {
            "status": "SUCCESS",
            "object": {
                "productId": 18100004,
                "coordinate": "2.2.0.0.0.0.0.0.0.0",
                "vectorId": 0,
                "vectorDataPoint": [],
            },
        }
    ]
    respx.post(f"{STATCAN_WDS_BASE_URL}/getDataFromCubePidCoordAndLatestNPeriods").mock(
        return_value=httpx.Response(200, json=invalid_data, headers={"Date": DATE_HEADER})
    )
    respx.post(f"{STATCAN_WDS_BASE_URL}/getCubeMetadata").mock(
        return_value=ok("cube_metadata_18100004")
    )

    with pytest.raises(StatCanResponseError, match="expected positive integer for 'vectorId'"):
        await statcan.get_data_from_cube(18100004, "2.2.0.0.0.0.0.0.0.0", latest_n=1)


@respx.mock
async def test_get_series_info(statcan: StatCanClient) -> None:
    respx.post(f"{STATCAN_WDS_BASE_URL}/getSeriesInfoFromVector").mock(
        return_value=ok("series_info_v41690973")
    )

    info = await statcan.get_series_info("v41690973")

    assert info.vector_id == 41690973
    assert info.product_id == 18100004
    assert info.coordinate == "2.2.0.0.0.0.0.0.0.0"
    assert info.frequency_code == 6
    assert info.title_en == "Canada;All-items"
    assert info.title_fr == "Canada;Ensemble"
    assert info.member_uom_code == 17


@respx.mock
async def test_statcan_response_error_on_failed_status(statcan: StatCanClient) -> None:
    respx.post(f"{STATCAN_WDS_BASE_URL}/getCubeMetadata").mock(return_value=ok("error_failed"))

    with pytest.raises(StatCanResponseError, match="No data found for coordinate"):
        await statcan.get_cube_metadata(99999999)


@respx.mock
async def test_statcan_not_found_error_on_http_404(statcan: StatCanClient) -> None:
    respx.post(f"{STATCAN_WDS_BASE_URL}/getCubeMetadata").mock(
        return_value=httpx.Response(404, text="Not Found")
    )

    with pytest.raises(StatCanNotFoundError, match="HTTP 404"):
        await statcan.get_cube_metadata(12345678)


@respx.mock
async def test_statcan_maintenance_window_error_on_http_409(statcan: StatCanClient) -> None:
    respx.post(f"{STATCAN_WDS_BASE_URL}/getCubeMetadata").mock(
        return_value=httpx.Response(409, text="Maintenance")
    )

    with pytest.raises(StatCanHTTPError, match="maintenance window"):
        await statcan.get_cube_metadata(18100004)


@respx.mock
async def test_statcan_retries_and_raises_http_error(statcan: StatCanClient) -> None:
    route = respx.post(f"{STATCAN_WDS_BASE_URL}/getCubeMetadata").mock(
        return_value=httpx.Response(500, text="Internal Server Error")
    )

    with pytest.raises(StatCanHTTPError, match="HTTP 500"):
        await statcan.get_cube_metadata(18100004)

    # 1 initial + 2 retries = 3 calls
    assert route.call_count == 3


@respx.mock
async def test_statcan_request_error_on_network_timeout(statcan: StatCanClient) -> None:
    respx.post(f"{STATCAN_WDS_BASE_URL}/getCubeMetadata").mock(
        side_effect=httpx.ReadTimeout("timed out")
    )

    with pytest.raises(StatCanRequestError, match="failed"):
        await statcan.get_cube_metadata(18100004)


@pytest.mark.live
async def test_live_statcan_wds_cpi_smoke() -> None:
    """Smoke test against the live Statistics Canada WDS API."""
    async with StatCanClient() as client:
        meta = await client.get_cube_metadata(18100004)
        assert meta.product_id == 18100004
        assert meta.title_en != ""

        data = await client.get_data_from_cube(18100004, "2.2.0.0.0.0.0.0.0.0", latest_n=1)
        assert len(data.observations) == 1
        citation = data.citation()
        assert citation.publisher == "Statistics Canada"
        assert citation.core.table_id == "18-10-0004-01"
        assert citation.enrichment.release_or_revision_date is not None


@respx.mock
async def test_ambiguous_member_error_carries_structured_attributes(statcan: StatCanClient) -> None:
    ambiguous_meta = [
        {
            "status": "SUCCESS",
            "object": {
                "productId": 34100133,
                "cubeTitleEn": "Rental Market Survey",
                "frequencyCode": 12,
                "dimension": [
                    {
                        "dimensionPositionId": 1,
                        "dimensionNameEn": "Geography",
                        "hasUom": False,
                        "member": [
                            {"memberId": 100, "memberNameEn": "Kentville", "memberNameFr": None},
                            {"memberId": 200, "memberNameEn": "Kentville", "memberNameFr": None},
                        ],
                    }
                ],
            },
        }
    ]
    respx.post(f"{STATCAN_WDS_BASE_URL}/getCubeMetadata").mock(
        return_value=httpx.Response(200, json=ambiguous_meta, headers={"Date": DATE_HEADER})
    )

    with pytest.raises(StatCanAmbiguousMemberError) as exc_info:
        await statcan.resolve_coordinate(34100133, ["Kentville"])

    err = exc_info.value
    assert err.member_name == "Kentville"
    assert err.dimension_position == 1
    assert err.dimension_name == "Geography"
    assert err.product_id == 34100133
    assert err.candidate_ids == (100, 200)
    assert len(err.candidates) == 2


@respx.mock
async def test_search_cubes_returns_compact_summaries(statcan: StatCanClient) -> None:
    results = await statcan.search_cubes("consumer price index", limit=5)
    assert len(results) >= 1
    first = results[0]
    assert isinstance(first, CubeSummary)
    assert first.product_id == 18100004
    assert first.table_id == "18-10-0004-01"
    assert "Consumer Price Index" in first.title_en
    assert first.frequency_code == 6


@respx.mock
async def test_statcan_citation_carries_licence_url(statcan: StatCanClient) -> None:
    respx.post(f"{STATCAN_WDS_BASE_URL}/getDataFromCubePidCoordAndLatestNPeriods").mock(
        return_value=ok("data_coord_18100004_cpi")
    )
    respx.post(f"{STATCAN_WDS_BASE_URL}/getCubeMetadata").mock(
        return_value=ok("cube_metadata_18100004")
    )

    result = await statcan.get_data_from_cube("18-10-0004-01", "2.1", latest_n=1)
    citation = result.citation()
    assert citation.enrichment.license_url == STATCAN_LICENCE_URL
    assert citation.enrichment.license_url == "https://www.statcan.gc.ca/en/reference/licence"
