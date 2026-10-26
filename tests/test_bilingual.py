"""Tests for English/French title selection (CAN-26)."""

from __future__ import annotations

import pytest

from candata_mcp.bilingual import Language, localize_title, parse_language
from candata_mcp.citation import BilingualTitle
from candata_mcp.connectors.boc_valet import ObservationSet
from candata_mcp.connectors.statcan_wds import StatCanSeriesResult
from candata_mcp.engine import DuckDBSlicingEngine


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "en"),
        ("en", "en"),
        ("EN", "en"),
        ("fr", "fr"),
        (" FR ", "fr"),
        ("fr-CA", "fr"),
        ("fr_CA", "fr"),
        ("en-US", "en"),
    ],
)
def test_parse_language_accepts_case_and_region_variants(value: str | None, expected: str) -> None:
    assert parse_language(value) == expected


@pytest.mark.parametrize("value", ["de", "", "french", "frfr"])
def test_parse_language_rejects_unsupported_codes(value: str) -> None:
    with pytest.raises(ValueError, match="Unsupported language"):
        parse_language(value)


def test_french_title_is_returned_when_published() -> None:
    title = localize_title(BilingualTitle(en="Rent", fr="Loyer"), "fr")
    assert (title.text, title.language, title.requested, title.fallback) == (
        "Loyer",
        "fr",
        "fr",
        False,
    )
    assert "note" not in title.to_payload()


@pytest.mark.parametrize("missing", [None, "", "   "])
def test_missing_french_falls_back_to_english_and_says_so(missing: str | None) -> None:
    title = localize_title(BilingualTitle(en="Rent", fr=missing), "fr")
    assert title.text == "Rent"
    assert title.language == "en"
    assert title.requested == "fr"
    assert title.fallback is True
    assert "English" in title.to_payload()["note"]


def test_english_request_never_reports_a_fallback() -> None:
    title = localize_title(BilingualTitle(en="Rent", fr="Loyer"), "en")
    assert (title.text, title.language, title.fallback) == ("Rent", "en", False)


def test_statcan_payload_localizes_to_french(
    engine: DuckDBSlicingEngine, statcan_result: StatCanSeriesResult
) -> None:
    payload = engine.slice_statcan(statcan_result, lang="fr")
    assert payload["display"] == {
        "title": "Indice des prix à la consommation",
        "language": "fr",
        "requested": "fr",
        "fallback": False,
    }
    # Both languages stay available for callers that compare field by field.
    assert payload["title"]["en"] == "Consumer Price Index"
    assert payload["title"]["fr"] == "Indice des prix à la consommation"


def test_statcan_payload_defaults_to_english(
    engine: DuckDBSlicingEngine, statcan_result: StatCanSeriesResult
) -> None:
    payload = engine.slice_statcan(statcan_result)
    assert payload["display"]["title"] == "Consumer Price Index"
    assert payload["display"]["language"] == "en"


def test_statcan_without_french_falls_back(
    engine: DuckDBSlicingEngine, statcan_result_no_french: StatCanSeriesResult
) -> None:
    payload = engine.slice_statcan(statcan_result_no_french, lang="fr")
    assert payload["display"]["title"] == "Consumer Price Index"
    assert payload["display"]["fallback"] is True


def test_valet_policy_rate_has_a_sourced_french_title(
    engine: DuckDBSlicingEngine, valet_result: ObservationSet
) -> None:
    payload = engine.slice_valet(valet_result, lang="fr")
    assert payload["display"]["title"] == "Taux cible du financement à un jour"
    assert payload["display"]["fallback"] is False


def test_valet_series_without_a_published_french_title_is_not_translated(
    engine: DuckDBSlicingEngine, valet_result_no_french: ObservationSet
) -> None:
    payload = engine.slice_valet(valet_result_no_french, lang="fr")
    assert payload["title"]["fr"] is None
    assert payload["display"]["title"] == "Policy Interest Rate"
    assert payload["display"]["fallback"] is True


@pytest.mark.parametrize("lang", ["en", "fr"])
def test_engine_accepts_every_supported_language(
    engine: DuckDBSlicingEngine, statcan_result: StatCanSeriesResult, lang: Language
) -> None:
    assert engine.slice_statcan(statcan_result, lang=lang)["display"]["requested"] == lang
