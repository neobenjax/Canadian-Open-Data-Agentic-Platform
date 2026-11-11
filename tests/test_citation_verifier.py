"""Tests for the CAN-24 Citation Verifier.

Offline tests use small fake sources built from real WDS and Valet values (the CAN-14 GT-01,
GT-05 and GT-13 figures), so each rule is pinned to a case we have seen. The live test checks
every citation in the ground-truth benchmark against the official APIs.
"""

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from candata_agent.verifier import (
    CitationVerifier,
    Claim,
    VerdictCode,
    make_citation_verifier_node,
)
from candata_mcp.citation import (
    BilingualTitle,
    CitationEnvelope,
    CoreVerificationTuple,
    MetadataEnrichment,
)
from candata_mcp.connectors.boc_valet import Observation as ValetObservation
from candata_mcp.connectors.boc_valet import (
    ObservationSet,
    SeriesDetail,
    ValetClient,
    ValetRequestError,
)
from candata_mcp.connectors.statcan_wds import (
    STATCAN_WDS_BASE_URL,
    Observation,
    StatCanClient,
    StatCanFailedStatusError,
    StatCanResponseError,
    StatCanSeriesResult,
)

GROUND_TRUTH = (
    Path(__file__).resolve().parents[1]
    / "collaboration"
    / "benchmarks"
    / "gta_ground_truth_v1.json"
)

RENT_2025 = Observation("2025-01-01", 2045.0, 0, "2025-12-17T08:30", 0, 12, 0, 0)
RENT_2024 = Observation("2024-01-01", 1972.0, 0, "2025-02-04T08:30", 0, 12, 0, 0)


def rent_series(*observations: Observation, product_id: int = 34100133) -> StatCanSeriesResult:
    return StatCanSeriesResult(
        product_id=product_id,
        coordinate="125.3.3.0.0.0.0.0.0.0",
        vector_id=3823103,
        title_en="CMHC average rents",
        title_fr=None,
        frequency_code=12,
        unit=None,
        observations=observations,
        fetched_at="2026-10-28T00:00:00+00:00",
    )


def statcan_citation(
    period: str = "2025",
    *,
    table_id: str = "34-10-0133-01",
    vector_id: str = "v3823103",
    release: str | None = "2025-12-17T08:30",
    coordinate: str | None = "125.3.3.0.0.0.0.0.0.0",
) -> CitationEnvelope:
    return CitationEnvelope(
        publisher="Statistics Canada",
        core=CoreVerificationTuple(table_id, vector_id, period),
        enrichment=MetadataEnrichment(
            coordinate=coordinate,
            release_or_revision_date=release,
            bilingual_title=BilingualTitle(en="CMHC average rents", fr=None),
            canonical_url="https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3410013301",
        ),
    )


def valet_citation(period: str = "2025-12-31") -> CitationEnvelope:
    return CitationEnvelope(
        publisher="Bank of Canada",
        core=CoreVerificationTuple("Valet", "V39079", period),
        enrichment=MetadataEnrichment(
            coordinate=None,
            release_or_revision_date=None,
            bilingual_title=BilingualTitle(en="Target for the overnight rate", fr=None),
            canonical_url="https://www.bankofcanada.ca/valet/observations/V39079",
        ),
    )


class FakeStatCan:
    def __init__(self, result: StatCanSeriesResult | Exception) -> None:
        self.result = result
        self.calls: list[tuple[str, str, str | None]] = []

    async def get_data_by_reference_period(
        self, vector_id: int | str, start: str, end: str | None = None
    ) -> StatCanSeriesResult:
        self.calls.append((str(vector_id), start, end))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakeValet:
    def __init__(self, result: ObservationSet | Exception) -> None:
        self.result = result

    async def get_observations(
        self, series_id: str, *, start_date: str | None = None, end_date: str | None = None
    ) -> ObservationSet:
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def policy_rate(*values: tuple[str, float | None]) -> ObservationSet:
    detail = SeriesDetail("V39079", "Target for the overnight rate", "", "daily", None, None, "")
    return ObservationSet(
        detail, tuple(ValetObservation(d, v) for d, v in values), "2026-10-28T00:00:00+00:00"
    )


RENT_2025_SERIES = rent_series(RENT_2025)
RATE_END_2025 = policy_rate(("2025-12-31", 2.25))


def verifier(
    statcan: StatCanSeriesResult | Exception = RENT_2025_SERIES,
    valet: ObservationSet | Exception = RATE_END_2025,
) -> CitationVerifier:
    return CitationVerifier(FakeStatCan(statcan), FakeValet(valet))


async def test_matching_value_and_release_is_verified() -> None:
    v = await verifier().verify_claim(Claim(statcan_citation(), 2045.0, "Toronto 2BR rent 2025"))
    assert v.code is VerdictCode.VERIFIED
    assert v.passed
    assert v.official_value == 2045.0
    assert (v.status_code, v.symbol_code) == (0, 0)


async def test_annual_period_is_queried_as_january_first() -> None:
    fake = FakeStatCan(rent_series(RENT_2025))
    await CitationVerifier(fake, FakeValet(policy_rate())).verify_claim(Claim(statcan_citation()))
    assert fake.calls == [("v3823103", "2025-01-01", "2025-01-01")]


async def test_listing_site_rent_is_a_value_mismatch() -> None:
    v = await verifier().verify_claim(Claim(statcan_citation(), 2632.0))
    assert v.code is VerdictCode.VALUE_MISMATCH
    assert "official 2045" in v.message


async def test_value_rounded_to_published_precision_passes() -> None:
    v = await verifier().verify_claim(Claim(statcan_citation(), 2045.4))
    assert v.code is VerdictCode.VERIFIED


async def test_vector_from_another_table_is_rejected() -> None:
    citation = statcan_citation(table_id="34-10-0127-01")
    v = await verifier().verify_claim(Claim(citation, 2045.0))
    assert v.code is VerdictCode.TABLE_MISMATCH
    assert "34-10-0133-01" in v.message


async def test_short_coordinate_matches_and_wrong_coordinate_fails() -> None:
    ok = await verifier().verify_claim(Claim(statcan_citation(coordinate="125.3.3"), 2045.0))
    bad = await verifier().verify_claim(Claim(statcan_citation(coordinate="132.3.3"), 2045.0))
    assert ok.code is VerdictCode.VERIFIED
    assert bad.code is VerdictCode.TABLE_MISMATCH


async def test_older_release_date_is_stale() -> None:
    revised = replace(RENT_2025, release_time="2026-01-15T08:30")
    v = await verifier(rent_series(revised)).verify_claim(Claim(statcan_citation(), 2045.0))
    assert v.code is VerdictCode.STALE_RELEASE
    assert v.official_release == "2026-01-15T08:30"


async def test_release_date_that_does_not_exist_is_flagged() -> None:
    citation = statcan_citation(release="2026-03-01T08:30")
    v = await verifier().verify_claim(Claim(citation, 2045.0))
    assert v.code is VerdictCode.RELEASE_MISMATCH


async def test_missing_official_value_is_suppressed() -> None:
    # v729961 (34-10-0143-01) has no published value for July 2025 (statusCode 1).
    gap = Observation("2025-07-01", None, 0, "2025-08-15T08:30", 0, 6, 1, 0)
    series = replace(rent_series(gap, product_id=34100143), vector_id=729961, coordinate="")
    citation = statcan_citation(
        "2025-07", table_id="34-10-0143-01", vector_id="v729961", release="2025-08-15T08:30"
    )
    v = await verifier(series).verify_claim(Claim(citation, 1500.0))
    assert v.code is VerdictCode.SUPPRESSED
    assert v.status_code == 1


async def test_range_citation_checks_the_latest_release() -> None:
    citation = statcan_citation("2024/2025", release="2025-12-17T08:30")
    v = await verifier(rent_series(RENT_2024, RENT_2025)).verify_claim(Claim(citation))
    assert v.code is VerdictCode.VERIFIED


async def test_value_claim_on_a_range_is_malformed() -> None:
    citation = statcan_citation("2024/2025")
    v = await verifier(rent_series(RENT_2024, RENT_2025)).verify_claim(Claim(citation, 2045.0))
    assert v.code is VerdictCode.MALFORMED_CITATION


@pytest.mark.parametrize(
    ("citation", "fragment"),
    [
        (statcan_citation(vector_id="3823103"), "vNNN"),
        (statcan_citation(table_id="34100133"), "NN-NN-NNNN-NN"),
        (statcan_citation("Oct 2025"), "reference_period"),
        (statcan_citation(release=None), "release_or_revision_date"),
        (statcan_citation(vector_id="v0x"), "vNNN"),
    ],
)
async def test_malformed_citations_never_reach_the_source(
    citation: CitationEnvelope, fragment: str
) -> None:
    fake = FakeStatCan(rent_series(RENT_2025))
    v = await CitationVerifier(fake, FakeValet(policy_rate())).verify_claim(Claim(citation, 1.0))
    assert v.code is VerdictCode.MALFORMED_CITATION
    assert fragment in v.message
    assert fake.calls == []


async def test_unknown_vector_is_not_found_but_an_outage_is_unavailable() -> None:
    missing = StatCanFailedStatusError("WDS call failed for vector v1: Vector does not exist")
    outage = StatCanResponseError("response from https://… is not valid JSON")
    v_missing = await verifier(missing).verify_claim(Claim(statcan_citation(), 2045.0))
    v_outage = await verifier(outage).verify_claim(Claim(statcan_citation(), 2045.0))
    assert v_missing.code is VerdictCode.NOT_FOUND
    assert v_outage.code is VerdictCode.SOURCE_UNAVAILABLE
    assert not v_outage.passed


async def test_not_found_comes_from_the_exception_type_not_its_message() -> None:
    # BEN-47: a broken payload whose text happens to say "WDS call failed" is an outage.
    lookalike = StatCanResponseError("WDS call failed: upstream returned garbage")
    v = await verifier(lookalike).verify_claim(Claim(statcan_citation(), 2045.0))
    assert v.code is VerdictCode.SOURCE_UNAVAILABLE


@respx.mock
async def test_client_raises_typed_error_for_failed_status_and_verifier_says_not_found() -> None:
    # BEN-47: WDS answers an unknown vector with 200 and status FAILED.
    body = [{"status": "FAILED", "object": "Vector does not exist"}]
    respx.get(f"{STATCAN_WDS_BASE_URL}/getDataFromVectorByReferencePeriodRange").mock(
        return_value=httpx.Response(200, json=body)
    )
    async with StatCanClient(backoff=0) as client:
        with pytest.raises(StatCanFailedStatusError):
            await client.get_data_by_reference_period(1, "2025-01-01", "2025-01-01")
        v = await CitationVerifier(client, FakeValet(policy_rate())).verify_claim(
            Claim(statcan_citation(vector_id="v1"), 2045.0)
        )
    assert v.code is VerdictCode.NOT_FOUND


@pytest.mark.parametrize(
    "cited",
    [
        "2025-12-17T08:30:00",  # seconds added
        "2025-12-17",  # date only, same day
        "2025-12-17T13:30:00+00:00",  # UTC; 08:30 Eastern in December
    ],
)
async def test_equivalent_release_forms_are_verified(cited: str) -> None:
    # BEN-46: as raw strings each of these differs from "2025-12-17T08:30", and
    # "2025-12-17" sorts before it, which made a same-day citation look stale.
    v = await verifier().verify_claim(Claim(statcan_citation(release=cited), 2045.0))
    assert v.code is VerdictCode.VERIFIED, v.message


async def test_date_only_release_from_an_earlier_day_is_stale() -> None:
    v = await verifier().verify_claim(Claim(statcan_citation(release="2025-02-04"), 2045.0))
    assert v.code is VerdictCode.STALE_RELEASE


async def test_later_release_with_different_format_is_a_mismatch_not_stale() -> None:
    v = await verifier().verify_claim(
        Claim(statcan_citation(release="2026-03-01T08:30:00"), 2045.0)
    )
    assert v.code is VerdictCode.RELEASE_MISMATCH


async def test_unparseable_release_date_is_malformed_before_any_request() -> None:
    fake = FakeStatCan(RENT_2025_SERIES)
    citation = statcan_citation(release="17 Dec 2025")
    v = await CitationVerifier(fake, FakeValet(policy_rate())).verify_claim(Claim(citation, 1.0))
    assert v.code is VerdictCode.MALFORMED_CITATION
    assert "release_or_revision_date" in v.message
    assert fake.calls == []


async def test_latest_release_is_chosen_by_time_not_by_string() -> None:
    # "2025-12-17T08:30" sorts after "2025-12-17T08:30:00+00:00" as text, but the UTC
    # release (03:30 Eastern) is earlier; the citation must match the true latest one.
    earlier = replace(RENT_2024, release_time="2025-12-17T08:30:00+00:00")
    series = rent_series(earlier, RENT_2025)
    v = await verifier(series).verify_claim(Claim(statcan_citation("2024/2025")))
    assert v.code is VerdictCode.VERIFIED, v.message


async def test_valet_policy_rate_is_verified_without_a_release_date() -> None:
    v = await verifier().verify_claim(Claim(valet_citation(), 2.25, "BoC rate, end of 2025"))
    assert v.code is VerdictCode.VERIFIED


async def test_valet_tolerance_uses_published_decimals() -> None:
    # BEN-48: Valet published "3.00". repr(3.0) reads one decimal and would accept 3.04.
    detail = SeriesDetail("V39079", "Target for the overnight rate", "", "daily", None, None, "")
    published = ObservationSet(
        detail, (ValetObservation("2025-12-31", 3.0, 2),), "2026-10-28T00:00:00+00:00"
    )
    near = await verifier(valet=published).verify_claim(Claim(valet_citation(), 3.004))
    off = await verifier(valet=published).verify_claim(Claim(valet_citation(), 3.04))
    assert near.code is VerdictCode.VERIFIED
    assert off.code is VerdictCode.VALUE_MISMATCH


async def test_valet_wrong_rate_and_outage() -> None:
    wrong = await verifier().verify_claim(Claim(valet_citation(), 2.5))
    down = await verifier(valet=ValetRequestError("timeout")).verify_claim(
        Claim(valet_citation(), 2.25)
    )
    assert wrong.code is VerdictCode.VALUE_MISMATCH
    assert down.code is VerdictCode.SOURCE_UNAVAILABLE


async def test_report_passes_only_when_every_claim_passes() -> None:
    report = await verifier().verify(
        [Claim(statcan_citation(), 2045.0), Claim(statcan_citation(), 2632.0)]
    )
    assert not report.passed
    assert [f.code for f in report.failures] == [VerdictCode.VALUE_MISMATCH]
    payload = json.loads(json.dumps(report.to_dict()))
    assert payload["passed"] is False
    assert payload["verdicts"][1]["code"] == "value_mismatch"


async def test_node_reads_claims_from_dict_or_attribute_state() -> None:
    node = make_citation_verifier_node(verifier())
    claim = Claim(statcan_citation(), 2045.0)

    class State:
        claims = (claim, "not a claim")

    from_dict = await node({"claims": [claim]})
    from_attr = await node(State())
    assert from_dict["verification"].passed
    assert len(from_attr["verification"].verdicts) == 1


@respx.mock
async def test_client_fetches_a_vector_by_reference_period() -> None:
    point = {
        "refPer": "2025-01-01",
        "value": 2045.0,
        "decimals": 0,
        "scalarFactorCode": 0,
        "symbolCode": 0,
        "statusCode": 0,
        "releaseTime": "2025-12-17T08:30",
        "frequencyCode": 12,
    }
    body: list[dict[str, Any]] = [
        {
            "status": "SUCCESS",
            "object": {
                "productId": 34100133,
                "coordinate": "125.3.3.0.0.0.0.0.0.0",
                "vectorId": 3823103,
                "vectorDataPoint": [point],
            },
        }
    ]
    route = respx.get(f"{STATCAN_WDS_BASE_URL}/getDataFromVectorByReferencePeriodRange").mock(
        return_value=httpx.Response(200, json=body)
    )
    meta = {
        "status": "SUCCESS",
        "object": {
            "productId": "34100133",
            "cubeTitleEn": "CMHC average rents",
            "frequencyCode": 12,
            "dimension": [],
        },
    }
    respx.post(f"{STATCAN_WDS_BASE_URL}/getCubeMetadata").mock(
        return_value=httpx.Response(200, json=[meta])
    )
    async with StatCanClient() as client:
        result = await client.get_data_by_reference_period("v3823103", "2025-01-01")
    params = route.calls.last.request.url.params
    assert params["vectorIds"] == '"3823103"'
    assert params["startRefPeriod"] == params["endReferencePeriod"] == "2025-01-01"
    assert result.product_id == 34100133
    assert result.observations[0].value == 2045.0


@pytest.mark.live
async def test_every_ground_truth_citation_verifies_against_official_sources() -> None:
    questions = json.loads(GROUND_TRUTH.read_text(encoding="utf-8"))["questions"]
    claims = [
        Claim(
            CitationEnvelope(
                publisher=c["publisher"],
                core=CoreVerificationTuple(**c["core"]),
                enrichment=MetadataEnrichment(
                    coordinate=c["enrichment"]["coordinate"],
                    release_or_revision_date=c["enrichment"]["release_or_revision_date"],
                    bilingual_title=BilingualTitle(**c["enrichment"]["bilingual_title"]),
                    canonical_url=c["enrichment"]["canonical_url"],
                ),
            ),
            label=q["id"],
        )
        for q in questions
        for c in q["citations"]
    ]
    # GT-01 cites the 2024 then the 2025 rent; check the values too, not only the citations.
    gt01 = [c for c in claims if c.label == "GT-01"]
    claims += [replace(gt01[0], value=1972.0), replace(gt01[1], value=2045.0)]
    async with StatCanClient() as statcan, ValetClient() as valet:
        report = await CitationVerifier(statcan, valet).verify(claims)
    failures = [(f.claim.label, f.code.value, f.message) for f in report.failures]
    assert report.passed, failures
