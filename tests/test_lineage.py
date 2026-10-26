"""Tests for data lineage on sliced payloads (CAN-26)."""

from __future__ import annotations

import json

from candata_mcp.connectors.boc_valet import VALET_BASE_URL, ObservationSet
from candata_mcp.connectors.statcan_wds import STATCAN_WDS_BASE_URL, StatCanSeriesResult
from candata_mcp.engine import MAX_PAYLOAD_BYTES, TRUNCATION_STEP, DuckDBSlicingEngine
from candata_mcp.lineage import build_lineage, statcan_call, valet_call

FETCHED_AT = "Thu, 22 Oct 2026 19:00:00 GMT"


def test_statcan_call_builds_the_wds_endpoint() -> None:
    call = statcan_call("getCubeMetadata", {"productId": 34100133})
    assert call.endpoint == f"{STATCAN_WDS_BASE_URL}/getCubeMetadata"
    assert call.request == {"productId": 34100133}


def test_valet_call_keeps_only_the_parameters_that_were_sent() -> None:
    call = valet_call(
        "observations/V39079/json", {"recent": None, "start_date": "2025-01-01", "end_date": None}
    )
    assert call.endpoint == f"{VALET_BASE_URL}/observations/V39079/json"
    assert call.request == {"start_date": "2025-01-01"}


def test_build_lineage_keeps_unknowns_as_null_instead_of_guessing() -> None:
    lineage = build_lineage(
        publisher="Bank of Canada", fetched_at=None, upstream_release=None, steps=("a",)
    )
    assert lineage == {
        "publisher": "Bank of Canada",
        "source_call": None,
        "fetched_at": None,
        "upstream_release": None,
        "title_source": None,
        "steps": ("a",),
    }


def test_statcan_lineage_records_the_call_release_and_every_step(
    engine: DuckDBSlicingEngine, statcan_result: StatCanSeriesResult
) -> None:
    payload = engine.slice_statcan(
        statcan_result,
        start_date="2024-03",
        end_date="2024-06",
        limit=5,
        source_call=statcan_call(
            "getDataFromVectorsAndLatestNPeriods", {"vectorId": 41690973, "latestN": 100}
        ),
    )
    lineage = payload["lineage"]
    assert lineage["publisher"] == "Statistics Canada"
    assert lineage["fetched_at"] == FETCHED_AT
    assert lineage["upstream_release"] == "2024-12-15T08:30"
    assert lineage["title_source"] == "getCubeMetadata productId 18100004"
    assert lineage["source_call"] == {
        "endpoint": f"{STATCAN_WDS_BASE_URL}/getDataFromVectorsAndLatestNPeriods",
        "request": {"vectorId": 41690973, "latestN": 100},
    }
    assert lineage["steps"][0] == "fetched 12 observations via getDataFromVectorsAndLatestNPeriods"
    assert lineage["steps"][1] == (
        "sliced in DuckDB: 2024-03 to 2024-06, newest first, limit 5; 4 rows matched, 4 returned"
    )


def test_lineage_does_not_invent_the_source_call(
    engine: DuckDBSlicingEngine, statcan_result: StatCanSeriesResult
) -> None:
    lineage = engine.slice_statcan(statcan_result)["lineage"]
    assert lineage["source_call"] is None
    assert lineage["steps"][0] == "fetched 12 observations"


def test_valet_lineage_says_the_release_timestamp_is_not_published(
    engine: DuckDBSlicingEngine, valet_result: ObservationSet
) -> None:
    payload = engine.slice_valet(
        valet_result,
        limit=3,
        source_call=valet_call("observations/V39079/json", {"recent": 24}),
    )
    lineage = payload["lineage"]
    assert lineage["publisher"] == "Bank of Canada"
    assert lineage["fetched_at"] == FETCHED_AT
    assert lineage["upstream_release"] is None
    assert lineage["title_source"] is None
    assert lineage["source_call"]["request"] == {"recent": 24}
    assert lineage["steps"][0] == "fetched 12 observations via observations/V39079/json"
    assert lineage["steps"][1] == "release timestamp: not published by Valet"
    assert "3 returned" in lineage["steps"][2]


def test_sliced_payload_with_lineage_stays_inside_the_budget(
    engine: DuckDBSlicingEngine, statcan_result: StatCanSeriesResult
) -> None:
    payload = engine.slice_statcan(
        statcan_result,
        limit=12,
        source_call=statcan_call(
            "getDataFromVectorsAndLatestNPeriods", {"vectorId": 41690973, "latestN": 100}
        ),
    )
    assert len(json.dumps(payload, default=str).encode("utf-8")) <= MAX_PAYLOAD_BYTES


def test_clamp_records_the_truncation_in_the_lineage(engine: DuckDBSlicingEngine) -> None:
    payload = {
        "data": [{"date": f"2020-{i:04d}", "value": 100.5 + i} for i in range(500)],
        "returned_count": 500,
        "lineage": build_lineage(
            publisher="Statistics Canada",
            fetched_at=FETCHED_AT,
            upstream_release=None,
            steps=("fetched 500 observations",),
        ),
    }
    clamped = engine.clamp_payload(payload)

    assert clamped["lineage"]["steps"][-1] == TRUNCATION_STEP
    assert clamped["truncated"] is True
    assert len(json.dumps(clamped, default=str).encode("utf-8")) <= MAX_PAYLOAD_BYTES
    # The caller's payload is untouched.
    assert payload["lineage"]["steps"] == ("fetched 500 observations",)


def test_clamp_leaves_lineage_alone_when_nothing_was_dropped(engine: DuckDBSlicingEngine) -> None:
    payload = {
        "data": [{"date": "2024-01", "value": 1.0}],
        "lineage": build_lineage(
            publisher="Statistics Canada", fetched_at=None, upstream_release=None, steps=("a",)
        ),
    }
    assert engine.clamp_payload(payload)["lineage"]["steps"] == ("a",)
