"""Tests for the CAN-41 DeepEval harness: period matching, the two-tier scores and a full run.

The end-to-end tests run the real graph (checkpointer, Data Analyst, Citation Verifier) with
the fake sources and real WDS / Valet values from ``test_supervisor``, record the runs as JSONL
and grade them with DeepEval.
"""

import dataclasses
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio

from candata_agent.checkpoint import AsyncSqliteSaver
from candata_agent.evals import AgentRun, covers, load_benchmark, period_interval, score_core
from candata_agent.evals.__main__ import main as cli
from candata_agent.evals.ground_truth import GroundTruthQuestion
from candata_agent.evals.report import ENRICHMENT, FRESHNESS, TIER_1, grade, render_markdown
from candata_agent.evals.run import read_runs, run_benchmark, write_runs
from candata_agent.evals.scoring import score_enrichment, score_freshness
from candata_agent.supervisor import build_agent_graph
from candata_mcp.citation import CitationEnvelope, CoreVerificationTuple
from tests.test_supervisor import (
    ALL_ITEMS,
    GT05_DRAFT,
    GT12_DRAFT,
    GT13_DRAFT,
    SHELTER,
    FakeStatCan,
    FakeValet,
    ScriptedPlanner,
    cpi_series,
    planned,
    starts_series,
)

BENCHMARK = load_benchmark()
QUESTIONS = {q.id: q for q in BENCHMARK.questions}


def core(table: str, vector: str, period: str | None) -> CoreVerificationTuple:
    return CoreVerificationTuple(table, vector, period)


def run_citing(
    truth: GroundTruthQuestion, *citations: CitationEnvelope, **fields: object
) -> AgentRun:
    defaults: dict[str, object] = {"answer": "answer", "produced_figures": True}
    return AgentRun(truth.id, truth.question, citations=citations, **{**defaults, **fields})  # type: ignore[arg-type]


def with_core(citation: CitationEnvelope, **changes: str | None) -> CitationEnvelope:
    return dataclasses.replace(citation, core=dataclasses.replace(citation.core, **changes))


# ---------------------------------------------------------------------------------------------
# Ground truth and periods
# ---------------------------------------------------------------------------------------------


def test_the_benchmark_loads_with_a_known_eval_type_and_citations_for_every_question() -> None:
    assert len(BENCHMARK.questions) == 15
    assert {q.eval_type for q in BENCHMARK.questions} == {
        "numeric",
        "comparison",
        "refusal",
        "flag",
    }
    assert all(q.citations for q in BENCHMARK.questions)
    assert [q.id for q in BENCHMARK.select(["GT-12", "GT-05"])] == ["GT-05", "GT-12"]
    with pytest.raises(KeyError, match="GT-99"):
        BENCHMARK.select(["GT-99"])


def test_partial_dates_become_half_open_intervals() -> None:
    assert [str(d) for d in period_interval("2025")] == ["2025-01-01", "2026-01-01"]
    assert [str(d) for d in period_interval("2025-12")] == ["2025-12-01", "2026-01-01"]
    assert [str(d) for d in period_interval("2025-01-30")] == ["2025-01-30", "2025-01-31"]
    assert [str(d) for d in period_interval("2024-01/2025-12")] == ["2024-01-01", "2026-01-01"]
    with pytest.raises(ValueError, match="not a reference period"):
        period_interval("Q3 2025")


def test_a_cited_range_covers_the_points_inside_it_and_nothing_else() -> None:
    shelter = "v41692889"
    cited = core("18-10-0004-01", shelter, "2025-08/2026-08")
    assert covers(cited, core("18-10-0004-01", shelter, "2025-08"))
    assert covers(cited, core("1810000401", "V41692889", "2026-08"))  # ID formats normalised
    assert not covers(cited, core("18-10-0004-01", shelter, "2026-09"))
    assert not covers(cited, core("18-10-0004-01", "v41692888", "2026-08"))  # other vector
    assert not covers(core("18-10-0004-01", shelter, None), core("18-10-0004-01", shelter, "2025"))
    assert not covers(
        core("18-10-0004-01", shelter, "garbage"), core("18-10-0004-01", shelter, "2025")
    )


def test_business_daily_ranges_may_start_after_a_holiday() -> None:
    expected = core("Valet", "V39079", "2025-01-01/2025-12-31")
    assert covers(core("Valet", "V39079", "2025-01-02/2025-12-31"), expected)  # no 1 Jan value
    assert not covers(core("Valet", "V39079", "2025-03-13/2025-12-31"), expected)


# ---------------------------------------------------------------------------------------------
# Tier 1
# ---------------------------------------------------------------------------------------------


def test_tier1_passes_only_with_every_core_tuple_and_nothing_extra() -> None:
    gt12 = QUESTIONS["GT-12"]
    exact = run_citing(gt12, *gt12.citations)
    assert score_core(gt12, exact).score == 1.0

    shelter, all_items = gt12.citations[1], gt12.citations[3]  # the 2026-08 tuples
    ranges = run_citing(
        gt12,
        with_core(shelter, reference_period="2025-08/2026-08"),
        with_core(all_items, reference_period="2025-08/2026-08"),
    )
    assert score_core(gt12, ranges).score == 1.0  # one range citation per series is enough

    one_series = run_citing(gt12, with_core(shelter, reference_period="2025-08/2026-08"))
    result = score_core(gt12, one_series)
    assert result.score == 0.0 and "missing 18-10-0004-01 v41692888 2025-08" in result.reason

    invented = with_core(shelter, vector_id="v0")
    result = score_core(gt12, run_citing(gt12, *gt12.citations, invented))
    assert (
        result.score == 0.0
        and "outside the ground truth" in result.reason
        and "v0" in result.reason
    )

    crashed = run_citing(gt12, error="TimeoutError: WDS")
    assert score_core(gt12, crashed).score == 0.0


def test_tier1_on_refusals_fails_any_figure() -> None:
    gt15 = QUESTIONS["GT-15"]
    declined = run_citing(gt15, produced_figures=False, declined="Declined: no 1992 data")
    result = score_core(gt15, declined)
    assert result.score == 1.0 and "1992" in result.reason
    assert score_core(gt15, run_citing(gt15, *gt15.citations)).score == 0.0  # gave figures
    assert score_enrichment(gt15, declined).applicable is False
    assert score_freshness(gt15, declined).applicable is False


# ---------------------------------------------------------------------------------------------
# Tier 2
# ---------------------------------------------------------------------------------------------


def test_enrichment_counts_each_field_that_matches() -> None:
    gt05 = QUESTIONS["GT-05"]
    (truth,) = gt05.citations
    assert score_enrichment(gt05, run_citing(gt05, truth)).score == 1.0

    no_french = dataclasses.replace(
        truth,
        enrichment=dataclasses.replace(
            truth.enrichment,
            bilingual_title=dataclasses.replace(truth.enrichment.bilingual_title, fr=None),
        ),
    )
    result = score_enrichment(gt05, run_citing(gt05, no_french))
    assert result.score == pytest.approx(4 / 5) and "French title (1)" in result.reason
    assert score_enrichment(gt05, run_citing(gt05)).score == 0.0  # nothing cited


def test_freshness_flags_a_release_older_than_the_ground_truth() -> None:
    gt05 = QUESTIONS["GT-05"]
    (truth,) = gt05.citations
    assert score_freshness(gt05, run_citing(gt05, truth)).score == 1.0
    old = dataclasses.replace(
        truth,
        enrichment=dataclasses.replace(
            truth.enrichment, release_or_revision_date="2025-12-17T08:30"
        ),
    )
    result = score_freshness(gt05, run_citing(gt05, old))
    assert result.score == 0.0 and "released 2025-12-17, expected 2026-01-21" in result.reason

    gt13 = QUESTIONS["GT-13"]  # Valet publishes no release dates
    assert score_freshness(gt13, run_citing(gt13, *gt13.citations)).applicable is False


# ---------------------------------------------------------------------------------------------
# End to end: the real graph, recorded, then graded by DeepEval
# ---------------------------------------------------------------------------------------------


@pytest_asyncio.fixture
async def saver(tmp_path: Path) -> AsyncGenerator[AsyncSqliteSaver, None]:
    async with AsyncSqliteSaver(tmp_path / "evals.db") as checkpointer:
        yield checkpointer


async def recorded_runs(saver: AsyncSqliteSaver) -> list[AgentRun]:
    statcan = FakeStatCan(
        starts_series(),
        cpi_series(41692889, "16.79.0.0.0.0.0.0.0.0", SHELTER),
        cpi_series(41692888, "16.2.0.0.0.0.0.0.0.0", ALL_ITEMS),
    )
    planner = ScriptedPlanner(planned(GT05_DRAFT), planned(GT12_DRAFT), planned(GT13_DRAFT))
    app = build_agent_graph(planner=planner, statcan=statcan, valet=FakeValet(), checkpointer=saver)
    questions = BENCHMARK.select(["GT-05", "GT-12", "GT-13"])
    return await run_benchmark(app, questions, planner="scripted", run_label="test")


async def test_a_full_run_is_recorded_and_graded_in_two_tiers(
    saver: AsyncSqliteSaver, tmp_path: Path
) -> None:
    runs = await recorded_runs(saver)
    assert [r.question_id for r in runs] == ["GT-05", "GT-12", "GT-13"]
    assert all(r.verified and r.produced_figures and r.error is None for r in runs)
    gt12 = runs[1]
    assert sorted(c.core.reference_period or "" for c in gt12.citations) == [
        "2025-08/2026-08",
        "2025-08/2026-08",
    ]  # each question on its own thread: no citations carried over from GT-05

    path = write_runs(runs, tmp_path / "runs.jsonl")
    assert read_runs(path) == runs  # JSONL round trip keeps every field

    report = grade(read_runs(path), BENCHMARK)
    assert report.graded == 3 and report.tier1_passed == 3
    assert report.tier1_by_type() == {"numeric": (2, 2), "comparison": (1, 1)}
    by_id = {r.question_id: r for r in report.results}
    # The CPI fakes carry no French title, so one enrichment field in five is missing.
    assert by_id["GT-12"].metrics[ENRICHMENT].score == pytest.approx(4 / 5)
    assert "French title" in by_id["GT-12"].metrics[ENRICHMENT].reason
    assert by_id["GT-12"].metrics[FRESHNESS].score == 1.0
    assert by_id["GT-13"].metrics[FRESHNESS].applicable is False
    assert report.mean(FRESHNESS) == 1.0

    markdown = render_markdown(report, runs)
    assert "**3/3 passed**" in markdown and "| GT-12 | comparison | pass |" in markdown


async def test_the_cli_grades_a_run_file_and_can_gate_on_tier1(
    saver: AsyncSqliteSaver, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    runs = await recorded_runs(saver)
    good = write_runs(runs, tmp_path / "good.jsonl")
    assert cli(["grade", str(good), "--out-dir", str(tmp_path), "--require-tier1"]) == 0
    assert (tmp_path / "good_report.json").exists() and (tmp_path / "good_report.md").exists()

    broken = [dataclasses.replace(runs[0], citations=())] + runs[1:]
    bad = write_runs(broken, tmp_path / "bad.jsonl")
    assert cli(["grade", str(bad), "--out-dir", str(tmp_path)]) == 0  # report only
    assert cli(["grade", str(bad), "--out-dir", str(tmp_path), "--require-tier1"]) == 1
    assert "Tier 1 failed on 1 question(s)." in capsys.readouterr().out

    report = grade(read_runs(bad), BENCHMARK)
    assert {r.question_id: r.metrics[TIER_1].passed for r in report.results} == {
        "GT-05": False,
        "GT-12": True,
        "GT-13": True,
    }


def test_the_recorded_live_run_still_passes_both_tiers() -> None:
    """GT-05, GT-12 and GT-13 as answered from live WDS and Valet on 2026-11-04 (fixed plans)."""
    recorded = Path(__file__).parents[1] / "collaboration/benchmarks/agent_evals/runs"
    runs = read_runs(recorded / "agent_demo_live_20261104.jsonl")
    assert all(r.verified for r in runs)
    report = grade(runs, BENCHMARK)
    assert report.tier1_passed == report.graded == 3
    assert report.mean(ENRICHMENT) == 1.0 and report.mean(FRESHNESS) == 1.0
