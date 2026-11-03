"""Unit tests for the Open Government Canada CKAN client (CAN-34)."""

import json

import httpx
import pytest
import respx

from candata_mcp.connectors.ckan_open_canada import (
    CKAN_BASE_URL,
    OPEN_CANADA_LICENCE_URL,
    CKANClient,
    CKANHTTPError,
    CKANNotFoundError,
    CKANResponseError,
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
    assert 'organization:"ec"' in sent_json["fq"]
    assert 'datastore_active:"true"' in sent_json["fq"]


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
    # Verified: auto-discovered package_id replaces generic 'CKAN' fallback!
    assert envelope.core.table_id == "pkg-climate"
    assert envelope.core.vector_id == "res-999"
    # Verified: reference_period derived directly from observation records ('2020/2024')
    assert envelope.core.reference_period == "2020/2024"
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
