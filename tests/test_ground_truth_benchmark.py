"""Structural checks for the GTA ground-truth benchmark (CAN-14). Runs offline."""

import json
from pathlib import Path

BENCHMARK = (
    Path(__file__).resolve().parents[1]
    / "collaboration"
    / "benchmarks"
    / "gta_ground_truth_v1.json"
)
REQUIRED_CITATION_FIELDS = {
    "table_id",
    "vector_id",
    "coordinate",
    "reference_periods",
    "release_time",
    "series_title_en",
    "series_title_fr",
    "deep_link_en",
}


def load() -> dict:
    return json.loads(BENCHMARK.read_text())


def test_has_fifteen_unique_questions() -> None:
    ids = [q["id"] for q in load()["questions"]]
    assert len(ids) == 15
    assert len(set(ids)) == 15


def test_every_question_is_complete() -> None:
    for q in load()["questions"]:
        for key in (
            "question",
            "category",
            "expected",
            "tolerance",
            "citations",
            "traps",
        ):
            assert q.get(key), f"{q['id']} is missing {key}"


def test_every_citation_has_the_full_tuple() -> None:
    for q in load()["questions"]:
        for citation in q["citations"]:
            missing = REQUIRED_CITATION_FIELDS - citation.keys()
            assert not missing, (
                f"{q['id']} citation {citation.get('vector_id')} is missing {missing}"
            )
            assert citation["reference_periods"], (
                f"{q['id']} has a citation with no reference period"
            )


def test_statcan_citations_use_ten_part_coordinates() -> None:
    for q in load()["questions"]:
        for citation in q["citations"]:
            if citation["publisher"] == "Statistics Canada":
                assert len(citation["coordinate"].split(".")) == 10, q["id"]
                assert citation["vector_id"].startswith("v"), q["id"]


def test_unanswerable_questions_define_expected_behaviour() -> None:
    for q in load()["questions"]:
        if q["category"] == "Unanswerable":
            assert "behaviour" in q["expected"], q["id"]
