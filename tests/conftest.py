"""Shared fixtures for the CAN-26 bilingual and lineage tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from candata_mcp.citation import (
    BilingualTitle,
    CitationEnvelope,
    CoreVerificationTuple,
    MetadataEnrichment,
)
from candata_mcp.connectors.boc_valet import Observation as ValetObservation
from candata_mcp.connectors.boc_valet import ObservationSet, SeriesDetail
from candata_mcp.connectors.statcan_wds import Observation as StatCanObservation
from candata_mcp.connectors.statcan_wds import StatCanSeriesResult
from candata_mcp.engine import DuckDBSlicingEngine

FETCHED_AT = "Thu, 22 Oct 2026 19:00:00 GMT"


@pytest.fixture
def engine() -> DuckDBSlicingEngine:
    return DuckDBSlicingEngine()


def _statcan_result(title_fr: str | None) -> StatCanSeriesResult:
    observations = tuple(
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
    envelope = CitationEnvelope(
        publisher="Statistics Canada",
        core=CoreVerificationTuple(
            table_id="18-10-0004-01", vector_id="v41690973", reference_period="2024-01/2024-12"
        ),
        enrichment=MetadataEnrichment(
            coordinate="2.1",
            release_or_revision_date="2024-12-15T08:30",
            bilingual_title=BilingualTitle(en="Consumer Price Index", fr=title_fr),
            canonical_url="https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810000401",
        ),
    )
    result = MagicMock(spec=StatCanSeriesResult)
    result.product_id = 18100004
    result.vector_id = 41690973
    result.coordinate = "2.1"
    result.title_en = "Consumer Price Index"
    result.title_fr = title_fr
    result.unit = None
    result.observations = observations
    result.fetched_at = FETCHED_AT
    result.citation.return_value = envelope
    return result


def _valet_result(name: str, fr: str | None) -> ObservationSet:
    observations = tuple(
        ValetObservation(date=f"2024-{m:02d}-01", value=5.0 - m * 0.25) for m in range(1, 13)
    )
    envelope = CitationEnvelope(
        publisher="Bank of Canada",
        core=CoreVerificationTuple(
            table_id="Valet", vector_id=name, reference_period="2024-01-01/2024-12-01"
        ),
        enrichment=MetadataEnrichment(
            coordinate=None,
            release_or_revision_date=None,
            bilingual_title=BilingualTitle(en="Policy Interest Rate", fr=fr),
            canonical_url=f"https://www.bankofcanada.ca/valet/observations/{name}",
        ),
    )
    result = MagicMock(spec=ObservationSet)
    result.series = SeriesDetail(
        name=name,
        label="Policy Interest Rate",
        description="Target for the overnight rate",
        frequency="M",
        unit="%",
        date_format="YYYY-MM-DD",
        url=f"https://www.bankofcanada.ca/valet/series/{name}/json",
    )
    result.observations = observations
    result.fetched_at = FETCHED_AT
    result.citation.return_value = envelope
    return result


@pytest.fixture
def statcan_result() -> StatCanSeriesResult:
    return _statcan_result("Indice des prix à la consommation")


@pytest.fixture
def statcan_result_no_french() -> StatCanSeriesResult:
    return _statcan_result(None)


@pytest.fixture
def valet_result() -> ObservationSet:
    return _valet_result("V39079", "Taux cible du financement à un jour")


@pytest.fixture
def valet_result_no_french() -> ObservationSet:
    return _valet_result("CPI_TRIM", None)
