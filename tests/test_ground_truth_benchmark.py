"""Structural checks for the GTA ground-truth benchmark (CAN-14).

Runs offline against the committed JSON, so it is safe for PR checks.
Live-source drift is checked separately with `build_ground_truth.py --check`.
"""

import json
import re
from pathlib import Path

BENCHMARK = (
    Path(__file__).resolve().parents[1]
    / "collaboration"
    / "benchmarks"
    / "gta_ground_truth_v1.json"
)
EVAL_TYPES = {"numeric", "comparison", "refusal", "flag"}
CORE_FIELDS = {"table_id", "vector_id", "reference_period"}
ENRICHMENT_FIELDS = {
    "coordinate",
    "release_or_revision_date",
    "bilingual_title",
    "canonical_url",
}
# 2025 | 2025-10 | 2025-01-30, optionally as an interval start/end
_PERIOD = r"\d{4}(-\d{2}(-\d{2})?)?"
PERIOD_FORMAT = re.compile(rf"^{_PERIOD}(/{_PERIOD})?$")


def load() -> dict:
    return json.loads(BENCHMARK.read_text())


def citations():
    for q in load()["questions"]:
        for citation in q["citations"]:
            yield q["id"], citation


def test_has_fifteen_unique_questions() -> None:
    ids = [q["id"] for q in load()["questions"]]
    assert len(ids) == 15
    assert len(set(ids)) == 15


def test_every_question_is_complete() -> None:
    for q in load()["questions"]:
        for key in (
            "question",
            "category",
            "eval_type",
            "expected",
            "tolerance",
            "citations",
            "traps",
        ):
            assert q.get(key), f"{q['id']} is missing {key}"


def test_eval_type_is_known() -> None:
    for q in load()["questions"]:
        assert q["eval_type"] in EVAL_TYPES, q["id"]


def test_comparison_questions_have_a_categorical_answer() -> None:
    for q in load()["questions"]:
        if q["eval_type"] == "comparison":
            assert q["expected"].get("answer"), q["id"]


def test_refusal_and_flag_questions_define_expected_behaviour() -> None:
    for q in load()["questions"]:
        if q["eval_type"] in {"refusal", "flag"}:
            assert q["expected"].get("behaviour"), q["id"]


def test_citations_follow_the_two_tier_envelope() -> None:
    for qid, citation in citations():
        assert set(citation["core"]) == CORE_FIELDS, qid
        assert set(citation["enrichment"]) == ENRICHMENT_FIELDS, qid
        assert all(citation["core"].values()), f"{qid} has an empty core field"
        title = citation["enrichment"]["bilingual_title"]
        assert title["en"] and title["fr"], qid


def test_reference_periods_use_the_series_granularity() -> None:
    for qid, citation in citations():
        period = citation["core"]["reference_period"]
        assert PERIOD_FORMAT.match(period), f"{qid}: {period!r}"


def test_statcan_citations_use_ten_part_coordinates() -> None:
    for qid, citation in citations():
        if citation["publisher"] == "Statistics Canada":
            assert len(citation["enrichment"]["coordinate"].split(".")) == 10, qid
            assert citation["core"]["vector_id"].startswith("v"), qid
