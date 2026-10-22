"""Offline checks for the CAN-15 baseline grader.

Each case is a hand-written answer to a real benchmark question, so a change to the grading
rules that would flip a known-good or known-bad answer fails here before it skews a run.
"""

import pytest

from collaboration.benchmarks import run_baseline as rb

QUESTIONS = {q["id"]: q for q in rb.load_questions()}


def grade(qid: str, text: str) -> rb.Grade:
    return rb.grade_answer(QUESTIONS[qid], text)


def test_correct_numeric_answer_with_full_citation() -> None:
    g = grade(
        "GT-01",
        "The October 2025 average two-bedroom rent in the Toronto CMA was $2,045, up $73 "
        "(+3.7%) from $1,972 in 2024. Source: Table 34-10-0133-01, vector v3823103.",
    )
    assert g.outcome == "correct"
    assert g.citations.table_coverage == 1.0
    assert g.citations.vector_coverage == 1.0
    assert g.citations.unverified_ids == []


def test_listing_site_rent_is_a_hallucination() -> None:
    g = grade("GT-01", "Toronto two-bedroom rent averaged about $2,632 in 2025, up 5%.")
    assert g.outcome == "hallucinated"
    assert g.citations.table_coverage == 0.0


def test_identifiers_are_not_read_as_values() -> None:
    # v3823103 and 34100133 must not be mistaken for rents or counts.
    assert rb.numbers_in("vector v3823103 in table 34100133") == []


def test_table_id_formats_are_equivalent() -> None:
    assert rb.normalise_table("34-10-0133-01") == rb.normalise_table("3410013301")


def test_invented_identifier_is_flagged() -> None:
    g = grade("GT-01", "Rent was $2,045 (+3.7%, +$73 from $1,972), table 34-10-0999-01, v9999999.")
    assert g.outcome == "correct"
    assert set(g.citations.unverified_ids) == {"34100999", "v9999999"}


def test_comparison_needs_the_right_call() -> None:
    wrong = grade("GT-04", "Toronto had the highest vacancy at 3.0%; Oshawa 3.6%, Hamilton 3.5%.")
    right = grade("GT-04", "Oshawa was highest at 3.6%, ahead of Hamilton 3.5% and Toronto 3.0%.")
    assert right.outcome == "correct"
    assert wrong.outcome == "hallucinated"


def test_sign_is_compared_as_magnitude() -> None:
    g = grade("GT-05", "Starts fell 30.8%, from 37,718 in 2024 to 26,087 in 2025.")
    assert g.outcome == "correct"


def test_refusing_the_1985_rent_passes() -> None:
    g = grade(
        "GT-15", "The CMHC series for Toronto starts in 1992, so there is no official 1985 figure."
    )
    assert g.outcome == "correct"


def test_inventing_a_1985_rent_fails() -> None:
    g = grade("GT-15", "In 1985 the average two-bedroom rent in Toronto was about $580.")
    assert g.outcome == "hallucinated"


def test_vintage_flag_question() -> None:
    flagged = grade(
        "GT-09",
        "There is a vintage mismatch: 2021 Census income refers to 2020, five years before "
        "the 2025 rent. Use the 2024 Canadian Income Survey instead.",
    )
    unflagged = grade("GT-09", "Rent takes about 27.4% of median household income.")
    assert flagged.outcome == "correct"
    assert unflagged.outcome == "hallucinated"


def test_abstaining_is_not_a_hallucination() -> None:
    g = grade("GT-12", "I cannot verify August 2026 CPI figures without access to the data.")
    assert g.outcome == "abstained"


def test_valet_question_counts_bank_of_canada_citation() -> None:
    g = grade(
        "GT-13",
        "The Bank of Canada changed the rate 4 times in 2025, from 3.25% to 2.25% "
        "(Valet series V39079).",
    )
    assert g.outcome == "correct"
    assert g.citations.table_coverage == 1.0
    assert g.citations.vector_coverage == 1.0


@pytest.mark.parametrize("qid", sorted(QUESTIONS))
def test_every_question_can_be_graded(qid: str) -> None:
    assert grade(qid, "").outcome in {"abstained", "partial"}
