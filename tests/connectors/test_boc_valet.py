"""Unit tests for the Bank of Canada Valet client (CAN-12).

Responses are real Valet payloads saved in tests/fixtures/valet, so the suite runs offline.
The single live test is skipped unless run with ``pytest -m live``.
"""

import json
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from candata_mcp.connectors.boc_valet import (
    CPI_SERIES,
    POLICY_RATE_SERIES,
    VALET_BASE_URL,
    ValetClient,
    ValetHTTPError,
    ValetNotFoundError,
    ValetRequestError,
    ValetResponseError,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "valet"
DATE_HEADER = "Mon, 19 Oct 2026 22:30:00 GMT"


def fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def ok(name: str) -> httpx.Response:
    return httpx.Response(200, json=fixture(name), headers={"Date": DATE_HEADER})


@pytest.fixture
async def valet():
    async with ValetClient(backoff=0) as client:
        yield client


@respx.mock
async def test_get_series_parses_detail(valet: ValetClient) -> None:
    respx.get(f"{VALET_BASE_URL}/series/V39079/json").mock(return_value=ok("series_V39079"))

    series = await valet.get_series("V39079")

    assert series.name == "V39079"
    assert series.label == "Target for the overnight rate (business daily)"
    assert series.frequency == "Business daily"
    assert series.unit == "Percent"
    assert series.date_format == "daily"
    assert series.url == f"{VALET_BASE_URL}/series/V39079"


@respx.mock
async def test_get_observations_returns_floats_oldest_first(valet: ValetClient) -> None:
    route = respx.get(f"{VALET_BASE_URL}/observations/V39079/json").mock(
        return_value=ok("observations_V39079_jan2025")
    )

    result = await valet.get_observations(
        "V39079", start_date=date(2025, 1, 27), end_date="2025-02-04"
    )

    assert route.calls.last.request.url.params["start_date"] == "2025-01-27"
    assert route.calls.last.request.url.params["end_date"] == "2025-02-04"
    dates = [o.date for o in result.observations]
    assert dates == sorted(dates)
    by_date = {o.date: o.value for o in result.observations}
    assert by_date["2025-01-29"] == 3.25
    assert by_date["2025-01-30"] == 3.0


@respx.mock
async def test_recent_results_are_sorted_oldest_first(valet: ValetClient) -> None:
    route = respx.get(f"{VALET_BASE_URL}/observations/CPI_TRIM/json").mock(
        return_value=ok("observations_CPI_TRIM_recent3")
    )

    result = await valet.get_observations("CPI_TRIM", recent=3)

    assert route.calls.last.request.url.params["recent"] == "3"
    assert [o.date for o in result.observations] == ["2026-07-01", "2026-08-01", "2026-09-01"]


@respx.mock
async def test_fetched_at_comes_from_the_http_date_header(valet: ValetClient) -> None:
    respx.get(f"{VALET_BASE_URL}/observations/V39079/json").mock(
        return_value=ok("observations_V39079_jan2025")
    )

    result = await valet.get_observations("V39079", recent=1)

    assert result.fetched_at == "2026-10-19T22:30:00+00:00"


@respx.mock
async def test_get_policy_rate_requests_v39079(valet: ValetClient) -> None:
    route = respx.get(f"{VALET_BASE_URL}/observations/{POLICY_RATE_SERIES}/json").mock(
        return_value=ok("observations_V39079_jan2025")
    )

    result = await valet.get_policy_rate(start_date="2025-01-27", end_date="2025-02-04")

    assert route.called
    assert result.series.name == "V39079"


@respx.mock
async def test_get_cpi_maps_measure_to_series(valet: ValetClient) -> None:
    route = respx.get(f"{VALET_BASE_URL}/observations/CPI_TRIM/json").mock(
        return_value=ok("observations_CPI_TRIM_recent3")
    )

    await valet.get_cpi("trim", recent=3)

    assert route.called
    assert CPI_SERIES["trim"] == "CPI_TRIM"


async def test_get_cpi_rejects_unknown_measure(valet: ValetClient) -> None:
    with pytest.raises(ValueError, match="unknown CPI measure"):
        await valet.get_cpi("bogus")


@respx.mock
async def test_get_group_lists_member_series(valet: ValetClient) -> None:
    respx.get(f"{VALET_BASE_URL}/groups/CPI_MONTHLY/json").mock(
        return_value=ok("group_CPI_MONTHLY")
    )

    group = await valet.get_group("CPI_MONTHLY")

    assert group.name == "CPI_MONTHLY"
    assert group.frequency == "Monthly"
    assert {s.name for s in group.series} == set(CPI_SERIES.values())
    assert all(s.url.startswith(f"{VALET_BASE_URL}/series/") for s in group.series)


@respx.mock
async def test_unknown_series_raises_not_found(valet: ValetClient) -> None:
    respx.get(f"{VALET_BASE_URL}/observations/NOT_A_SERIES/json").mock(
        return_value=httpx.Response(404, json=fixture("error_404_series"))
    )

    with pytest.raises(ValetNotFoundError, match="Series NOT_A_SERIES not found") as info:
        await valet.get_observations("NOT_A_SERIES")

    assert info.value.status_code == 404


@respx.mock
async def test_bad_request_raises_http_error_with_valet_message(valet: ValetClient) -> None:
    respx.get(f"{VALET_BASE_URL}/observations/V39079/json").mock(
        return_value=httpx.Response(400, json=fixture("error_400_param"))
    )

    with pytest.raises(ValetHTTPError, match="must be numeric") as info:
        await valet.get_observations("V39079", recent=1)

    assert info.value.status_code == 400
    assert not isinstance(info.value, ValetNotFoundError)


@respx.mock
async def test_retries_transient_failures_then_succeeds(valet: ValetClient) -> None:
    route = respx.get(f"{VALET_BASE_URL}/observations/V39079/json").mock(
        side_effect=[
            httpx.Response(503),
            httpx.ConnectTimeout("slow"),
            ok("observations_V39079_jan2025"),
        ]
    )

    result = await valet.get_observations("V39079", recent=1)

    assert route.call_count == 3
    assert result.observations


@respx.mock
async def test_gives_up_after_retries_on_timeout(valet: ValetClient) -> None:
    route = respx.get(f"{VALET_BASE_URL}/observations/V39079/json").mock(
        side_effect=httpx.ConnectTimeout("slow")
    )

    with pytest.raises(ValetRequestError):
        await valet.get_observations("V39079", recent=1)

    assert route.call_count == 3


@respx.mock
async def test_persistent_server_error_is_reported_not_retried_forever(valet: ValetClient) -> None:
    route = respx.get(f"{VALET_BASE_URL}/observations/V39079/json").mock(
        return_value=httpx.Response(503)
    )

    with pytest.raises(ValetHTTPError) as info:
        await valet.get_observations("V39079", recent=1)

    assert info.value.status_code == 503
    assert route.call_count == 3


@respx.mock
async def test_non_json_body_raises_response_error(valet: ValetClient) -> None:
    respx.get(f"{VALET_BASE_URL}/series/V39079/json").mock(
        return_value=httpx.Response(200, text="<html>maintenance</html>")
    )

    with pytest.raises(ValetResponseError, match="not valid JSON"):
        await valet.get_series("V39079")


@respx.mock
async def test_empty_observation_value_becomes_none(valet: ValetClient) -> None:
    payload = fixture("observations_V39079_jan2025")
    payload["observations"] = [{"d": "2025-01-27", "V39079": {"v": ""}}]
    respx.get(f"{VALET_BASE_URL}/observations/V39079/json").mock(
        return_value=httpx.Response(200, json=payload)
    )

    result = await valet.get_observations("V39079", recent=1)

    assert result.observations[0].value is None


@respx.mock
async def test_non_numeric_observation_value_raises(valet: ValetClient) -> None:
    payload = fixture("observations_V39079_jan2025")
    payload["observations"] = [{"d": "2025-01-27", "V39079": {"v": "n/a"}}]
    respx.get(f"{VALET_BASE_URL}/observations/V39079/json").mock(
        return_value=httpx.Response(200, json=payload)
    )

    with pytest.raises(ValetResponseError, match="non-numeric"):
        await valet.get_observations("V39079", recent=1)


@pytest.mark.parametrize("bad", ["", "V39079/../x", "V 39079", "a?b=c"])
async def test_rejects_unsafe_series_names_without_a_request(valet: ValetClient, bad: str) -> None:
    with pytest.raises(ValueError, match="invalid Valet name"):
        await valet.get_series(bad)


async def test_recent_cannot_be_combined_with_dates(valet: ValetClient) -> None:
    with pytest.raises(ValueError, match="cannot be combined"):
        await valet.get_observations("V39079", recent=1, start_date="2025-01-01")


async def test_rejects_malformed_dates(valet: ValetClient) -> None:
    with pytest.raises(ValueError, match="ISO date"):
        await valet.get_observations("V39079", start_date="01/02/2025")


async def test_rejects_non_positive_recent(valet: ValetClient) -> None:
    with pytest.raises(ValueError, match="positive"):
        await valet.get_observations("V39079", recent=0)


@respx.mock
async def test_daily_range_citation(valet: ValetClient) -> None:
    respx.get(f"{VALET_BASE_URL}/observations/V39079/json").mock(
        return_value=ok("observations_V39079_jan2025")
    )
    result = await valet.get_policy_rate(start_date="2025-01-27", end_date="2025-02-04")

    envelope = result.citation()

    assert envelope.publisher == "Bank of Canada"
    assert envelope.core.table_id == "Valet"
    assert envelope.core.vector_id == "V39079"
    assert envelope.core.reference_period == "2025-01-27/2025-02-04"
    assert envelope.enrichment.canonical_url == f"{VALET_BASE_URL}/observations/V39079"
    assert (
        envelope.enrichment.bilingual_title.en == "Target for the overnight rate (business daily)"
    )


@respx.mock
async def test_monthly_citation_uses_month_granularity(valet: ValetClient) -> None:
    respx.get(f"{VALET_BASE_URL}/observations/CPI_TRIM/json").mock(
        return_value=ok("observations_CPI_TRIM_recent3")
    )
    result = await valet.get_cpi("trim", recent=3)

    assert result.citation().core.reference_period == "2026-07/2026-09"


@respx.mock
async def test_single_observation_citation_has_no_interval(valet: ValetClient) -> None:
    payload = fixture("observations_CPI_TRIM_recent3")
    payload["observations"] = payload["observations"][:1]
    respx.get(f"{VALET_BASE_URL}/observations/CPI_TRIM/json").mock(
        return_value=httpx.Response(200, json=payload)
    )
    result = await valet.get_cpi("trim", recent=1)

    assert result.citation().core.reference_period == "2026-09"


@respx.mock
async def test_citation_leaves_unpublished_fields_empty(valet: ValetClient) -> None:
    respx.get(f"{VALET_BASE_URL}/observations/V39079/json").mock(
        return_value=ok("observations_V39079_jan2025")
    )
    result = await valet.get_policy_rate(recent=None, start_date="2025-01-27")

    enrichment = result.citation().enrichment

    assert enrichment.coordinate is None
    assert enrichment.release_or_revision_date is None
    assert enrichment.bilingual_title.fr is None


@respx.mock
async def test_citation_requires_observations(valet: ValetClient) -> None:
    payload = fixture("observations_V39079_jan2025")
    payload["observations"] = []
    respx.get(f"{VALET_BASE_URL}/observations/V39079/json").mock(
        return_value=httpx.Response(200, json=payload)
    )
    result = await valet.get_policy_rate(recent=None, start_date="2030-01-01")

    with pytest.raises(ValueError, match="no observations"):
        result.citation()


async def test_caller_owned_http_client_is_not_closed() -> None:
    async with httpx.AsyncClient() as http:
        async with ValetClient(client=http):
            pass
        assert not http.is_closed


@pytest.mark.live
async def test_live_policy_rate_matches_published_shape() -> None:
    async with ValetClient() as valet:
        result = await valet.get_policy_rate(recent=1)

    assert result.series.name == "V39079"
    assert result.observations[0].value is not None
    assert result.citation().core.table_id == "Valet"
