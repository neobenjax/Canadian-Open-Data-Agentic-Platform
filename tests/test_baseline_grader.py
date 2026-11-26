"""Offline checks for the CAN-15 baseline grader.

Each case is a hand-written answer to a real benchmark question, so a change to the grading
rules that would flip a known-good or known-bad answer fails here before it skews a run.
"""

import json

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
    implicit = grade(
        "GT-09", "Census income reflects 2020 incomes while the rent is from 2025; it mixes years."
    )
    unflagged = grade("GT-09", "Rent takes about 27.4% of median household income.")
    assert implicit.outcome == "correct"
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


def test_wrong_headline_value_is_a_hallucination() -> None:
    # Start and end rates are right, but the count the question asks for is wrong.
    g = grade(
        "GT-13",
        "The Bank of Canada changed its rate three times in 2025:\n"
        "1. 29 January: 3.25% to 3.00%\n2. 12 March: 3.00% to 2.75%\n"
        "3. 29 October: 2.75% to 2.25%\nIt started at 3.25% and ended at 2.25%.",
    )
    assert g.outcome == "hallucinated"
    assert "number_of_changes" in g.reason


def test_list_numbering_is_not_a_value() -> None:
    assert rb.numbers_in("Steps:\n4. Check the table") == []


def test_counts_written_as_words_are_read() -> None:
    g = grade(
        "GT-13", "Four changes in 2025 (Valet V39079): from 3.25% at the start to 2.25% at the end."
    )
    assert g.outcome == "correct"


def test_declining_without_saying_the_data_is_absent_is_an_abstention() -> None:
    g = grade(
        "GT-14",
        "I can't give you a verified figure and won't estimate one. Check table 18-10-0004-01.",
    )
    assert g.outcome == "abstained"


def test_declining_with_years_only_is_not_a_hallucination() -> None:
    g = grade(
        "GT-10", "I can't tell you; compare the 2025 annual average with 2024 in 18-10-0005-01."
    )
    assert g.outcome == "abstained"


def test_number_words_outside_counts_are_ignored() -> None:
    assert rb.numbers_in("apartment structures of three units and over") == []


def test_every_headline_key_exists() -> None:
    for qid, keys in rb.HEADLINE.items():
        assert set(keys) <= set(rb.expected_values(QUESTIONS[qid])), qid


@pytest.mark.parametrize("qid", sorted(QUESTIONS))
def test_every_question_can_be_graded(qid: str) -> None:
    assert grade(qid, "").outcome in {"abstained", "partial"}


def test_false_claim_override_keeps_the_automatic_outcome(tmp_path, monkeypatch) -> None:
    run = tmp_path / "2026-10-22_no_tools_m.jsonl"
    row = {
        "question_id": "GT-14",
        "arm": "no_tools",
        "requested_model": "m",
        "model_ids": ["m"],
        "tools_available": [],
        "started_at": "2026-10-22T00:00:00+00:00",
        "duration_s": 1.0,
        "num_turns": 1,
        "tool_calls": [],
        "is_error": False,
        "response": "I can't give you a figure. Table 18-10-0004-01 has a Toronto series.",
    }
    run.write_text(json.dumps(row) + "\n", encoding="utf-8")
    overrides = tmp_path / "overrides.json"
    overrides.write_text(
        json.dumps(
            {"no_tools/m/2026-10-22/GT-14": {"false_claim": "Says a Toronto series exists."}}
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(rb, "OVERRIDES", overrides)
    report = rb.grade([run])
    assert report["answers"][0]["grade"]["outcome"] == "abstained"
    assert report["summary"][0]["false_claims"] == 1
    assert "Says a Toronto series exists." in rb.render_markdown(report)


def test_run_records_each_tool_calls_arguments_and_error_status() -> None:
    """#54: a failed call must be diagnosable from the run file, not inferred from the answer."""
    long_sql = "SELECT " + "x, " * 200 + "1"
    events = [
        {"type": "system", "subtype": "init", "tools": ["mcp__candata__query_statcan_vector"]},
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "text", "text": "Looking it up."},
                    {
                        "type": "tool_use",
                        "id": "tu_1",
                        "name": "mcp__candata__query_statcan_coordinate",
                        "input": {"product_id": 34100133, "coordinate": "1.2.3"},
                    },
                    {
                        "type": "tool_use",
                        "id": "tu_2",
                        "name": "mcp__candata__execute_sql_analytics",
                        "input": {"sql": long_sql, "tables": ["t"]},
                    },
                ]
            },
        },
        {
            "type": "user",
            "message": {
                "content": [
                    {"type": "tool_result", "tool_use_id": "tu_1", "is_error": True},
                    {"type": "tool_result", "tool_use_id": "tu_2", "content": "ok"},
                ]
            },
        },
        {"type": "assistant", "message": {"content": "plain text, not blocks"}},
    ]
    first, second = rb.tool_call_details(events)
    assert first == {
        "name": "mcp__candata__query_statcan_coordinate",
        "input": {"product_id": 34100133, "coordinate": "1.2.3"},
        "is_error": True,
    }
    assert second["is_error"] is False
    assert second["input"]["tables"] == ["t"]
    sql = second["input"]["sql"]
    assert len(sql) < len(long_sql) and sql.endswith(f"... [{len(long_sql)} chars]")
    assert sql.startswith(long_sql[: rb.MAX_ARG_CHARS])


def test_a_tool_call_without_a_result_is_recorded_as_unknown() -> None:
    events = [
        {
            "type": "assistant",
            "message": {"content": [{"type": "tool_use", "id": "a", "name": "t", "input": {}}]},
        }
    ]
    assert rb.tool_call_details(events) == [{"name": "t", "input": {}, "is_error": None}]


def _answer(qid: str, response: str, started: str) -> dict[str, object]:
    return {
        "question_id": qid,
        "arm": "candata_mcp",
        "requested_model": "m",
        "model_ids": ["m"],
        "tools_available": [],
        "started_at": started,
        "duration_s": 1.0,
        "num_turns": 1,
        "tool_calls": [],
        "is_error": False,
        "response": response,
    }


def test_a_rerun_is_its_own_row_and_keeps_its_own_hand_grades(tmp_path, monkeypatch) -> None:
    """#54: re-running CanData-MCP must not merge with, or inherit grades from, the old run."""
    old = tmp_path / "2026-10-22_candata_mcp_m.jsonl"
    new = tmp_path / "2026-11-25_candata_mcp_m.jsonl"
    old.write_text(
        json.dumps(_answer("GT-14", "I can't verify that.", "2026-10-22T20:00:00+00:00"))
    )
    new.write_text(
        json.dumps(_answer("GT-14", "I can't verify that.", "2026-11-25T19:00:00+00:00"))
    )
    overrides = tmp_path / "overrides.json"
    overrides.write_text(
        json.dumps({"candata_mcp/m/2026-11-25/GT-14": {"outcome": "correct", "reason": "ok"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(rb, "OVERRIDES", overrides)

    report = rb.grade([new, old])
    assert [(s["run_date"], s["questions"], s["correct"]) for s in report["summary"]] == [
        ("2026-10-22", 1, 0),
        ("2026-11-25", 1, 1),
    ]
    md = rb.render_markdown(report)
    assert "| Question | candata_mcp · m · 2026-10-22 | candata_mcp · m · 2026-11-25 |" in md
    assert "| GT-14 | abstained | correct* |" in md


def test_run_files_must_start_with_their_date(tmp_path) -> None:
    bad = tmp_path / "candata_mcp_m.jsonl"
    bad.write_text(json.dumps(_answer("GT-14", "x", "2026-11-25T19:00:00+00:00")))
    with pytest.raises(ValueError, match="does not start with its run date"):
        rb.load_runs([bad])
