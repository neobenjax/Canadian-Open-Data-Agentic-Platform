"""Unit tests for the Open Government Canada CKAN client (CAN-34)."""

import json

import httpx
import pytest
import respx

from candata_mcp.connectors.ckan_open_canada import (
    CKAN_BASE_URL,
    OPEN_CANADA_LICENCE_URL,
    CKANClient,
    CKANDatasetDetail,
    CKANDataStoreResult,
    CKANFieldSchema,
    CKANHTTPError,
    CKANNotFoundError,
    CKANResponseError,
    CKANResultTooLargeError,
    validate_identifier,
)

DATE_HEADER = "Mon, 19 Oct 2026 22:30:00 GMT"


@pytest.fixture
async def ckan():
    async with CKANClient(backoff=0.01) as client:
        yield client


def test_validate_identifier_accepts_clean_ids():
    assert validate_identifier("cmhc-housing-data") == "cmhc-housing-data"
    assert validate_identifier("123_abc-XYZ") == "123_abc-XYZ"
    assert (
        validate_identifier("550e8400-e29b-41d4-a716-446655440000")
        == "550e8400-e29b-41d4-a716-446655440000"
    )
    assert validate_identifier("cmhc.housing.2024") == "cmhc.housing.2024"


def test_validate_identifier_rejects_malformed_ids():
    with pytest.raises(ValueError, match="Invalid package_id"):
        validate_identifier("", "package_id")
    with pytest.raises(ValueError, match="Invalid resource_id"):
        validate_identifier("   ", "resource_id")
    with pytest.raises(ValueError, match="Invalid identifier"):
        validate_identifier("dataset/../traversal", "identifier")
    with pytest.raises(ValueError, match="Invalid identifier"):
        validate_identifier("dataset?query=1", "identifier")
    with pytest.raises(ValueError, match="Invalid identifier"):
        validate_identifier("dataset; DROP TABLE users;", "identifier")
    with pytest.raises(ValueError, match="path traversal"):
        validate_identifier("dataset/../traversal", "identifier")
    with pytest.raises(ValueError, match="path traversal"):
        validate_identifier("cmhc..starts", "identifier")


def test_https_enforced_in_production():
    with pytest.raises(ValueError, match="must use HTTPS in production"):
        CKANClient(base_url="http://open.canada.ca/data/api/3/action")


@respx.mock
async def test_search_datasets_parses_results(ckan: CKANClient):
    mock_payload = {
        "success": True,
        "result": {
            "count": 42,
            "results": [
                {
                    "id": "cmhc-housing-starts",
                    "name": "cmhc-housing-starts",
                    "title_translated": {
                        "en": "Housing Starts in Urban Areas",
                        "fr": "Mises en chantier dans les centres urbains",
                    },
                    "organization": {
                        "name": "cmhc-schl",
                        "title_translated": {
                            "en": "Canada Mortgage and Housing Corporation",
                            "fr": "Société canadienne d'hypothèques et de logement",
                        },
                    },
                    "metadata_modified": "2026-02-15T10:00:00",
                    "resources": [
                        {
                            "id": "res-001",
                            "datastore_active": True,
                            "format": "CSV",
                        },
                        {
                            "id": "res-002",
                            "datastore_active": False,
                            "format": "PDF",
                        },
                    ],
                }
            ],
        },
    }

    route = respx.post(f"{CKAN_BASE_URL}/package_search").mock(
        return_value=httpx.Response(
            200,
            json=mock_payload,
            headers={"Date": DATE_HEADER, "Content-Type": "application/json"},
        )
    )

    search_res = await ckan.search_datasets("housing starts", limit=5, offset=0)

    assert route.called
    sent_json = json.loads(route.calls.last.request.content)
    assert sent_json["q"] == "housing starts"
    assert sent_json["rows"] == 5
    assert sent_json["sort"] == "score desc, metadata_modified desc"
    assert search_res.total_results == 42
    assert len(search_res.datasets) == 1

    ds = search_res.datasets[0]
    assert ds.package_id == "cmhc-housing-starts"
    assert ds.title_en == "Housing Starts in Urban Areas"
    assert ds.title_fr == "Mises en chantier dans les centres urbains"
    assert ds.organization_en == "Canada Mortgage and Housing Corporation"
    assert ds.datastore_resource_ids == ("res-001",)


@respx.mock
async def test_search_datasets_organization_filter(ckan: CKANClient):
    route = respx.post(f"{CKAN_BASE_URL}/package_search").mock(
        return_value=httpx.Response(
            200,
            json={"success": True, "result": {"count": 0, "results": []}},
            headers={"Content-Type": "application/json"},
        )
    )

    await ckan.search_datasets("climate", organization="ec", datastore_only=True)

    sent_json = json.loads(route.calls.last.request.content)
    assert sent_json["fq"] == 'organization:"ec"'
    assert "datastore_active" not in sent_json["fq"]
    assert sent_json["sort"] == "score desc, metadata_modified desc"


@respx.mock
async def test_get_dataset_and_citation_envelope(ckan: CKANClient):
    mock_pkg = {
        "success": True,
        "result": {
            "id": "pkg-1234",
            "name": "canadian-climate-normals",
            "title_translated": {
                "en": "Canadian Climate Normals",
                "fr": "Normales climatiques canadiennes",
            },
            "notes_translated": {
                "en": "Historical climate observations across stations.",
                "fr": "Données climatiques historiques par station.",
            },
            "organization": {
                "name": "environment-climate-change-canada",
                "title_translated": {
                    "en": "Environment and Climate Change Canada",
                    "fr": "Environnement et Changement climatique Canada",
                },
            },
            "metadata_modified": "2025-11-01T14:30:00",
            "time_period_coverage_start": "1991-01-01",
            "time_period_coverage_end": "2020-12-31",
            "license_title": "Open Government Licence - Canada",
            "license_url": OPEN_CANADA_LICENCE_URL,
            "resources": [
                {
                    "id": "res-999",
                    "name_translated": {"en": "1991-2020 Normals Table", "fr": "Tableau 1991-2020"},
                    "format": "CSV",
                    "datastore_active": True,
                    "url": "https://open.canada.ca/data/dataset/pkg-1234/resource/res-999/download.csv",
                    "last_modified": "2025-11-01T14:30:00",
                    "size": 5242880,
                }
            ],
        },
    }

    respx.post(f"{CKAN_BASE_URL}/package_show").mock(
        return_value=httpx.Response(
            200, json=mock_pkg, headers={"Date": DATE_HEADER, "Content-Type": "application/json"}
        )
    )

    detail = await ckan.get_dataset("pkg-1234")

    assert detail.package_id == "pkg-1234"
    assert detail.title_en == "Canadian Climate Normals"
    assert detail.title_fr == "Normales climatiques canadiennes"
    assert len(detail.resources) == 1
    assert detail.resources[0].resource_id == "res-999"
    assert detail.resources[0].datastore_active is True

    # Check Citation Envelope
    envelope = detail.citation()
    assert envelope.publisher == "Open Government Canada / Environment and Climate Change Canada"
    assert envelope.core.table_id == "pkg-1234"
    assert envelope.core.vector_id == "pkg-1234"
    assert envelope.core.reference_period == "1991-01-01/2020-12-31"
    assert envelope.enrichment.reference_period_source == "time_period_coverage"
    assert envelope.enrichment.bilingual_title.en == "Canadian Climate Normals"
    assert envelope.enrichment.bilingual_title.fr == "Normales climatiques canadiennes"
    assert envelope.enrichment.canonical_url == "https://open.canada.ca/data/en/dataset/pkg-1234"
    assert envelope.enrichment.license_url == OPEN_CANADA_LICENCE_URL

    # Cached on second call without new network request
    cached_detail = await ckan.get_dataset("pkg-1234")
    assert cached_detail.package_id == "pkg-1234"


@respx.mock
async def test_query_datastore_records_and_citation(ckan: CKANClient):
    mock_ds = {
        "success": True,
        "result": {
            "resource_id": "res-999",
            "fields": [
                {"id": "_id", "type": "int"},
                {"id": "station_name", "type": "text"},
                {"id": "annual_mean_temp", "type": "numeric"},
                {"id": "year", "type": "text"},
            ],
            "records": [
                {
                    "_id": 1,
                    "station_name": "TORONTO INTL A",
                    "annual_mean_temp": 9.4,
                    "year": "2020",
                },
                {"_id": 2, "station_name": "OTTAWA CDA", "annual_mean_temp": 6.8, "year": "2024"},
            ],
            "total": 150,
        },
    }

    respx.post(f"{CKAN_BASE_URL}/resource_show").mock(
        return_value=httpx.Response(
            200,
            json={"success": True, "result": {"id": "res-999", "package_id": "pkg-climate"}},
            headers={"Content-Type": "application/json"},
        )
    )
    respx.post(f"{CKAN_BASE_URL}/package_show").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "result": {
                    "id": "pkg-climate",
                    "title_translated": {"en": "Climate Normals", "fr": "Normales"},
                    "organization": {"title_translated": {"en": "Environment Canada"}},
                },
            },
            headers={"Content-Type": "application/json"},
        )
    )
    respx.post(f"{CKAN_BASE_URL}/datastore_search").mock(
        return_value=httpx.Response(
            200, json=mock_ds, headers={"Date": DATE_HEADER, "Content-Type": "application/json"}
        )
    )

    ds_result = await ckan.query_datastore(
        "res-999",
        q="Toronto",
        limit=2,
    )

    assert ds_result.resource_id == "res-999"
    assert ds_result.package_id == "pkg-climate"
    assert ds_result.total_records == 150
    assert len(ds_result.records) == 2
    assert ds_result.records[0]["station_name"] == "TORONTO INTL A"

    envelope = ds_result.citation()
    assert envelope.core.table_id == "pkg-climate"
    assert envelope.core.vector_id == "res-999"
    # The year column is not a reference period; this package publishes no coverage.
    assert envelope.core.reference_period is None
    assert envelope.enrichment.reference_period_source == "unknown"
    assert envelope.core.reference_period != "2020/2024"
    assert "DataStore (2 rows)" in str(envelope.enrichment.coordinate)


@respx.mock
async def test_error_handling_not_found(ckan: CKANClient):
    respx.post(f"{CKAN_BASE_URL}/package_show").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": False,
                "error": {"__type": "Not Found Error", "message": "Not found"},
            },
            headers={"Content-Type": "application/json"},
        )
    )

    with pytest.raises(CKANNotFoundError, match="Not found"):
        await ckan.get_dataset("unknown-pkg")


@respx.mock
async def test_error_handling_html_outage(ckan: CKANClient):
    respx.post(f"{CKAN_BASE_URL}/package_search").mock(
        return_value=httpx.Response(
            200,
            text="<html><body>503 Service Temporarily Unavailable</body></html>",
            headers={"Content-Type": "text/html"},
        )
    )

    with pytest.raises(CKANResponseError, match="non-JSON content-type"):
        await ckan.search_datasets("housing")


@respx.mock
async def test_error_handling_http_server_error(ckan: CKANClient):
    respx.post(f"{CKAN_BASE_URL}/package_search").mock(
        return_value=httpx.Response(
            500,
            json={"success": False, "error": {"message": "Internal error"}},
            headers={"Content-Type": "application/json"},
        )
    )

    with pytest.raises(CKANHTTPError, match="500"):
        await ckan.search_datasets("test")


def _package(
    package_id: str,
    *,
    datastore: bool,
    resource_id: str = "res-1",
) -> dict[str, object]:
    return {
        "id": package_id,
        "name": package_id,
        "title": package_id,
        "metadata_modified": "2026-01-01T00:00:00",
        "resources": [
            {
                "id": resource_id,
                "datastore_active": datastore,
                "format": "CSV",
            }
        ],
    }


@respx.mock
async def test_search_ranks_by_relevance_then_recency(ckan: CKANClient):
    """'consumer price index' must ask CKAN for score, not recency alone."""
    route = respx.post(f"{CKAN_BASE_URL}/package_search").mock(
        return_value=httpx.Response(
            200,
            json={"success": True, "result": {"count": 0, "results": []}},
            headers={"Content-Type": "application/json"},
        )
    )

    await ckan.search_datasets("consumer price index")

    sent_json = json.loads(route.calls.last.request.content)
    assert sent_json["sort"] == "score desc, metadata_modified desc"
    assert sent_json["q"] == "consumer price index"


@respx.mock
async def test_datastore_only_filters_resources_client_side(ckan: CKANClient):
    """datastore_active lives on resources, so the package fq filter matches nothing."""

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["sort"] == "score desc, metadata_modified desc"
        assert "datastore_active" not in body.get("fq", "")
        start = int(body["start"])
        if start == 0:
            results = [
                _package("new-but-irrelevant", datastore=False),
                _package("also-no-datastore", datastore=False, resource_id="res-2"),
            ]
        else:
            results = [
                _package(
                    "population-estimates",
                    datastore=True,
                    resource_id="f9a392dc-0000-4000-8000-000000000001",
                )
            ]
        return httpx.Response(
            200,
            json={"success": True, "result": {"count": 3, "results": results}},
            headers={"Content-Type": "application/json"},
        )

    route = respx.post(f"{CKAN_BASE_URL}/package_search").mock(side_effect=handler)

    found = await ckan.search_datasets("population", datastore_only=True, limit=5)

    assert route.call_count == 2
    assert len(found.datasets) == 1
    assert found.datasets[0].package_id == "population-estimates"
    assert found.datasets[0].datastore_resource_ids == ("f9a392dc-0000-4000-8000-000000000001",)
    assert found.total_is_exact is True


@pytest.mark.live
async def test_live_datastore_only_population_returns_a_hit() -> None:
    async with CKANClient() as client:
        found = await client.search_datasets("population", datastore_only=True, limit=5)

    assert found.datasets
    assert all(item.datastore_resource_ids for item in found.datasets)


def test_dataset_citation_does_not_invent_a_period():
    detail = CKANDatasetDetail(
        package_id="pkg-1",
        name="pkg-1",
        title_en="Population estimates",
        title_fr=None,
        notes_en=None,
        notes_fr=None,
        organization_en=None,
        organization_fr=None,
        metadata_modified="2025-11-01T14:30:00",
        time_period_coverage_start=None,
        time_period_coverage_end=None,
        license_title=None,
        license_url=OPEN_CANADA_LICENCE_URL,
        resources=(),
    )

    envelope = detail.citation()

    assert envelope.core.reference_period is None
    assert envelope.enrichment.reference_period_source == "unknown"
    assert envelope.core.reference_period != "2025-11-01"
    assert envelope.core.reference_period != "current"


def test_datastore_citation_ignores_mixed_language_header_row():
    """A French header stored as a record must not become the reference period."""
    guessed = CKANDataStoreResult(
        resource_id="f9a392dc-0000-4000-8000-000000000001",
        package_id="pkg-population",
        title_en="Population estimates",
        title_fr="Estimations de la population",
        publisher_en="Open Government Canada",
        fields=(
            CKANFieldSchema("year", "text"),
            CKANFieldSchema("Année", "text"),
            CKANFieldSchema("value", "numeric"),
        ),
        records=(
            {"year": "1988", "Année": "Année", "value": "1"},
            {"year": "2020", "Année": "2020", "value": "2"},
        ),
        total_records=526,
        release_or_revision_date="2024-06-01T00:00:00",
        fetched_at="2026-10-29T10:00:00Z",
    )
    envelope = guessed.citation()
    assert envelope.core.reference_period is None
    assert envelope.enrichment.reference_period_source == "unknown"
    assert envelope.core.reference_period != "1988/Année"
    assert envelope.core.reference_period != "2024-06-01"
    assert envelope.core.table_id == "pkg-population"

    covered = CKANDataStoreResult(
        resource_id=guessed.resource_id,
        package_id=guessed.package_id,
        title_en=guessed.title_en,
        title_fr=guessed.title_fr,
        publisher_en=guessed.publisher_en,
        fields=guessed.fields,
        records=guessed.records,
        total_records=guessed.total_records,
        release_or_revision_date=guessed.release_or_revision_date,
        fetched_at=guessed.fetched_at,
        time_period_coverage_start="2001-01-01",
        time_period_coverage_end="2021-12-31",
    )
    covered_envelope = covered.citation()
    assert covered_envelope.core.reference_period == "2001-01-01/2021-12-31"
    assert covered_envelope.enrichment.reference_period_source == "time_period_coverage"


def _json_response(payload: dict[str, object]) -> httpx.Response:
    return httpx.Response(
        200,
        json=payload,
        headers={"Content-Type": "application/json", "Date": DATE_HEADER},
    )


@respx.mock
async def test_query_datastore_raises_when_package_lookup_fails(ckan: CKANClient):
    respx.post(f"{CKAN_BASE_URL}/datastore_search").mock(
        return_value=_json_response(
            {
                "success": True,
                "result": {
                    "fields": [{"id": "value", "type": "numeric"}],
                    "records": [{"value": 1}],
                    "total": 1,
                },
            }
        )
    )
    respx.post(f"{CKAN_BASE_URL}/resource_show").mock(
        return_value=_json_response(
            {
                "success": True,
                "result": {"id": "res-999", "package_id": "pkg-missing"},
            }
        )
    )
    respx.post(f"{CKAN_BASE_URL}/package_show").mock(
        return_value=_json_response(
            {
                "success": False,
                "error": {"__type": "Not Found Error", "message": "Not found"},
            }
        )
    )

    with pytest.raises(CKANNotFoundError, match="Not found"):
        await ckan.query_datastore("res-999")


@respx.mock
async def test_query_datastore_complete_pages_past_the_first_hundred(ckan: CKANClient):
    total = 250

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        offset = int(body["offset"])
        limit = int(body["limit"])
        assert limit == 100
        end = min(offset + limit, total)
        records = [{"_id": i, "value": i} for i in range(offset, end)]
        return _json_response(
            {
                "success": True,
                "result": {
                    "fields": [
                        {"id": "_id", "type": "int"},
                        {"id": "value", "type": "int"},
                    ],
                    "records": records,
                    "total": total,
                },
            }
        )

    route = respx.post(f"{CKAN_BASE_URL}/datastore_search").mock(side_effect=handler)
    respx.post(f"{CKAN_BASE_URL}/resource_show").mock(
        return_value=_json_response(
            {"success": True, "result": {"id": "res-999", "package_id": "pkg-1"}}
        )
    )
    respx.post(f"{CKAN_BASE_URL}/package_show").mock(
        return_value=_json_response(
            {
                "success": True,
                "result": {
                    "id": "pkg-1",
                    "name": "pkg-1",
                    "title": "Population estimates",
                    "metadata_modified": "2024-06-01T00:00:00",
                },
            }
        )
    )

    result = await ckan.query_datastore_complete("res-999")

    assert route.call_count == 3
    assert result.total_records == 250
    assert len(result.records) == 250
    assert result.records[0]["_id"] == 0
    assert result.records[-1]["_id"] == 249
    assert result.citation().core.reference_period is None
    assert result.citation().enrichment.reference_period_source == "unknown"


@respx.mock
async def test_query_datastore_complete_rejects_tables_past_the_cap(ckan: CKANClient):
    route = respx.post(f"{CKAN_BASE_URL}/datastore_search").mock(
        return_value=_json_response(
            {
                "success": True,
                "result": {
                    "fields": [{"id": "_id", "type": "int"}],
                    "records": [{"_id": i} for i in range(100)],
                    "total": 5001,
                },
            }
        )
    )

    with pytest.raises(CKANResultTooLargeError, match="5001") as raised:
        await ckan.query_datastore_complete("res-999")

    assert raised.value.total == 5001
    assert raised.value.cap == 5000
    assert route.call_count == 1
