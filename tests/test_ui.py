"""Tests for the CAN-32 UI support: graph event streaming, the demo planner and the charts.

The streaming tests run the real graph (checkpointer, Data Analyst, Citation Verifier) through
``astream_events`` v2 with the fake sources and real WDS values from ``test_supervisor``.
"""

from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import pytest_asyncio

from candata_agent.checkpoint import AsyncSqliteSaver
from candata_agent.state import SQLArtifact
from candata_agent.supervisor import build_agent_graph
from candata_agent.ui import (
    AnalysisResult,
    FetchedSeries,
    NodeFinished,
    NodeStarted,
    RunEvent,
    RunFinished,
    RunResult,
    stream_question,
)
from candata_agent.ui.charts import CUT_NOTE, flag_text, result_figure, series_figure
from candata_agent.ui.session import DEMO_QUESTIONS, DemoPlanner
from tests.test_supervisor import (
    ALL_ITEMS,
    GT05_QUESTION,
    GT12_DRAFT,
    GT12_QUESTION,
    GT13_QUESTION,
    SHELTER,
    FakeStatCan,
    FakeValet,
    ScriptedPlanner,
    cpi_series,
    draft,
    planned,
)


@pytest_asyncio.fixture
async def saver(tmp_path: Path) -> AsyncGenerator[AsyncSqliteSaver, None]:
    async with AsyncSqliteSaver(tmp_path / "ui.db") as checkpointer:
        yield checkpointer


def gt12_statcan() -> FakeStatCan:
    return FakeStatCan(
        cpi_series(41692889, "16.79.0.0.0.0.0.0.0.0", SHELTER),
        cpi_series(41692888, "16.2.0.0.0.0.0.0.0.0", ALL_ITEMS),
    )


async def collect(app: Any, question: str, thread: str) -> list[RunEvent]:
    return [e async for e in stream_question(app, question, thread_id=thread, session_id="s")]


# ---------------------------------------------------------------------------------------------
# Streaming
# ---------------------------------------------------------------------------------------------


async def test_stream_reports_each_node_and_gathers_only_this_runs_results(
    saver: AsyncSqliteSaver,
) -> None:
    planner = ScriptedPlanner(planned(GT12_DRAFT), planned(GT12_DRAFT))
    app = build_agent_graph(
        planner=planner, statcan=gt12_statcan(), valet=FakeValet(), checkpointer=saver
    )

    for turn in (1, 2):  # same thread: the second run must not repeat the first run's series
        events = await collect(app, GT12_QUESTION, "gt12")
        started = [e.node for e in events if isinstance(e, NodeStarted)]
        assert started[0] == "supervisor" and started[-1] == "citation_verifier"
        assert started.count("data_fetcher") == 2 and started.count("data_analyst") == 2
        assert isinstance(events[-1], RunFinished)

        result = events[-1].result
        assert [(s.slot, s.source, s.unit) for s in result.series] == [
            ("table_a", "v41692889", "2002=100"),
            ("table_b", "v41692888", "2002=100"),
        ]
        assert [len(s.rows) for s in result.series] == [13, 13]
        assert [(a.recipe, a.artifact.source_series_id) for a in result.analyses] == [
            ("yoy_point_to_point", "v41692889"),
            ("yoy_point_to_point", "v41692888"),
        ]
        assert sorted(c.core.vector_id for c in result.citations) == ["v41692888", "v41692889"]
        assert result.verified and result.failed_step is None
        assert len(planner.questions) == turn

        shown = [m.id for e in events if isinstance(e, NodeFinished) for m in e.messages]
        assert len(shown) == len(set(shown)) == len(result.messages)  # each message once
        assert all(m.role != "user" for m in result.messages)


async def test_stream_surfaces_a_failed_fetch(saver: AsyncSqliteSaver) -> None:
    unknown = draft(("fetch_statcan_vector", {"vector_id": "v999", "start": "2024", "end": "2025"}))
    app = build_agent_graph(
        planner=ScriptedPlanner(planned(unknown)),
        statcan=FakeStatCan(),
        valet=FakeValet(),
        checkpointer=saver,
    )
    events = await collect(app, GT05_QUESTION, "fail")
    result = events[-1].result if isinstance(events[-1], RunFinished) else None
    assert result is not None
    assert result.failed_step is not None and "v999" in result.failed_step
    assert result.series == [] and result.analyses == [] and result.verification is None


# ---------------------------------------------------------------------------------------------
# Demo planner
# ---------------------------------------------------------------------------------------------


def test_demo_questions_are_the_benchmark_questions() -> None:
    assert [q.question for q in DEMO_QUESTIONS] == [GT12_QUESTION, GT05_QUESTION, GT13_QUESTION]


async def test_demo_planner_plans_the_examples_and_declines_the_rest() -> None:
    planner = DemoPlanner()
    for item in DEMO_QUESTIONS:
        result = await planner.plan(f"  {item.question.upper()} ")  # case and spacing ignored
        assert result.plan is not None and result.declined_reason is None
    gt12 = await planner.plan(GT12_QUESTION)
    assert gt12.plan is not None
    vectors = [s.tool_args.get("vector_id") for s in gt12.plan.steps[:2]]
    assert vectors == ["v41692889", "v41692888"]
    shelter, all_items = "Toronto shelter CPI", "Toronto all-items CPI"
    assert [s.description for s in gt12.plan.steps] == [shelter, all_items, shelter, all_items]

    other = await planner.plan("What was Ottawa's unemployment rate in 2024?")
    assert other.plan is None
    assert other.declined_reason is not None and "ANTHROPIC_API_KEY" in other.declined_reason


# ---------------------------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------------------------


def series(source: str, unit: str | None, *rows: dict[str, Any]) -> FetchedSeries:
    return FetchedSeries(slot=source, source=source, unit=unit, rows=rows)


def row(date: str, value: float | None, status: int = 0, symbol: int = 0) -> dict[str, Any]:
    return {"date": date, "value": value, "status_code": status, "symbol_code": symbol}


def test_series_sharing_a_unit_share_one_axis() -> None:
    fig = series_figure(
        [
            series("v1", "2002=100", row("2026-07", 170.9), row("2026-08", 171.7)),
            series("v2", "2002=100", row("2026-07", 189.3), row("2026-08", 190.5)),
        ]
    )
    assert fig is not None
    assert [t.name for t in fig.data] == ["v1", "v2"]
    assert fig.layout.yaxis.title.text == "2002=100"
    assert "yaxis2" not in fig.to_plotly_json()["layout"]  # one axis, no second scale
    assert fig.data[0].line.color != fig.data[1].line.color


def test_series_with_different_units_become_small_multiples_not_a_second_axis() -> None:
    fig = series_figure(
        [
            series("v42127475", "Units", row("2025-01", 2368.0)),
            series("V39079", "%", row("2025-01-30", 3.0)),
        ]
    )
    assert fig is not None
    assert [a.text for a in fig.layout.annotations] == ["Units", "%"]  # one panel per unit
    assert fig.data[1].yaxis == "y2" and fig.layout.yaxis2.overlaying is None
    assert fig.layout.xaxis.matches == "x2" or fig.layout.xaxis2.matches == "x"


def test_flagged_and_missing_observations_are_marked() -> None:
    fig = series_figure(
        [
            series(
                "v1", "%", row("2025-01", 1.0), row("2025-02", 2.0, symbol=5), row("2025-03", None)
            )
        ]
    )
    assert fig is not None
    line, flagged = fig.data
    assert flagged.name == "v1: flagged"
    assert list(flagged.x) == ["2025-02"]
    assert flagged.text == ("StatCan symbol code 5",)
    assert flag_text(row("2025-03", None)) == "value not available"
    assert flag_text(row("2025-01", 1.0)) is None
    assert series_figure([]) is None and series_figure([series("v1", "%")]) is None


def artifact(source: str, *rows: dict[str, Any]) -> SQLArtifact:
    return SQLArtifact(
        source_series_id=source, sql_query="SELECT 1", row_count=len(rows), rows=rows
    )


def test_a_two_series_comparison_becomes_grouped_bars() -> None:
    analyses = [
        AnalysisResult("yoy_point_to_point", artifact("v41692889", {"obs_date": "2026-08-01",
                                                                    "change_pct": -0.47})),
        AnalysisResult("yoy_point_to_point", artifact("v41692888", {"obs_date": "2026-08-01",
                                                                    "change_pct": 2.14})),
    ]  # fmt: skip
    fig = result_figure(analyses)
    assert fig is not None
    assert [(t.type, t.name, tuple(t.y)) for t in fig.data] == [
        ("bar", "v41692889", (-0.47,)),
        ("bar", "v41692888", (2.14,)),
    ]
    assert fig.layout.barmode == "group"
    assert fig.data[0].x == ("2026-08",) and fig.layout.xaxis.type == "category"
    assert fig.layout.yaxis.title.text == "Year-over-year change (%)"


def test_result_periods_run_oldest_first() -> None:
    totals = artifact(
        "v42127475",
        {"cal_year": "2025", "aggregated_total": 26087.0},
        {"cal_year": "2024", "aggregated_total": 37718.0},
    )
    fig = result_figure([AnalysisResult("calendar_year_aggregation", totals)])
    assert fig is not None
    assert (fig.data[0].x, fig.data[0].y) == (("2024", "2025"), (37718.0, 26087.0))


def test_results_without_a_time_series_metric_are_left_to_the_table() -> None:
    yoy = AnalysisResult("yoy_point_to_point", artifact("v1", {"obs_date": "x", "change_pct": 1}))
    count = AnalysisResult("discrete_regime_change_counter", artifact("V39079", {"changes": 4}))
    assert result_figure([yoy, count]) is None  # mixed recipes
    assert result_figure([count]) is None  # not a time series
    assert result_figure([]) is None


def test_series_and_results_are_named_by_their_plan_step() -> None:
    labelled = FetchedSeries("table_a", "v41692889", "2002=100", (), label="Toronto shelter CPI")
    assert labelled.name == "Toronto shelter CPI (v41692889)"
    assert series("v1", None).name == "v1"
    result = AnalysisResult("yoy_point_to_point", artifact("v41692888"), "Toronto all-items CPI")
    assert result.name == "Toronto all-items CPI (v41692888)"


def test_run_result_defaults_are_independent() -> None:
    first, second = RunResult("a"), RunResult("b")
    first.series.append(series("v1", None))
    assert second.series == [] and not second.verified


def test_planner_written_names_are_shown_as_text_not_evaluated_or_rendered() -> None:
    hostile = 'Shelter %{y:$.2f} <a href="https://evil.example">click</a> & co'
    named = FetchedSeries("table_a", "v1", "<b>%</b>", (row("2025-01", 1.0, symbol=5),), hostile)
    fig = series_figure([named])
    assert fig is not None
    line, flagged = fig.data
    escaped = 'Shelter %{y:$.2f} &lt;a href="https://evil.example"&gt;click&lt;/a&gt; &amp; co (v1)'
    assert line.name == escaped and flagged.name == f"{escaped}: flagged"
    assert line.meta is None  # with meta set, Plotly would evaluate templates in the name
    assert set(line.customdata) == {"&lt;b&gt;%&lt;/b&gt;"}
    assert fig.layout.yaxis.title.text == "&lt;b&gt;%&lt;/b&gt;"
    for trace in fig.data:  # names reach the hover box as data, never inside the template
        assert "evil" not in trace.hovertemplate and "Shelter" not in trace.hovertemplate
    assert "%{fullData.name}" in line.hovertemplate and "%{customdata}" in line.hovertemplate

    yoy = artifact("v1", {"obs_date": "x", "change_pct": 1})
    result = AnalysisResult("yoy_point_to_point", yoy, hostile)
    bars = result_figure([result])
    assert bars is not None
    assert bars.data[0].name.startswith("Shelter %{y:$.2f} &lt;a")
    assert "evil" not in bars.data[0].hovertemplate


def test_charts_say_when_they_leave_series_out() -> None:
    many = [series(f"v{i}", "%", row("2025-01", float(i))) for i in range(9)]
    fig = series_figure(many)
    assert fig is not None and len(fig.data) == 7
    assert [a.text for a in fig.layout.annotations if a.name == CUT_NOTE] == [
        "Showing the first 7 of 9 series; the tables list all of them."
    ]

    analyses = [
        AnalysisResult("yoy_point_to_point", artifact(f"v{i}", {"obs_date": "x", "change_pct": i}))
        for i in range(8)
    ]
    bars = result_figure(analyses)
    assert bars is not None and len(bars.data) == 7
    assert "first 7 of 8 results" in bars.layout.annotations[0].text

    few = series_figure(many[:7])
    assert few is not None and not few.layout.annotations  # nothing left out, no note
