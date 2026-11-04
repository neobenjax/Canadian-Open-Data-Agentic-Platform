"""Tests for the CAN-22 Supervisor: plan validation, the Claude planner loop and the full graph.

The graph tests run the real StateGraph with the real checkpointer, Data Analyst and Citation
Verifier. Only the data sources and the planner are fakes, and the data is the real WDS and
Valet series for GT-05 (Toronto housing starts), GT-12 (Toronto shelter vs all-items CPI) and
GT-13 (policy rate changes in 2025).
"""

import json
import tempfile
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any, cast

import pytest
import pytest_asyncio
from anthropic import AsyncAnthropic
from anthropic.types.beta import BetaMessage

from candata_agent.checkpoint import AsyncSqliteSaver
from candata_agent.state import AgentMessage, MessageRole, QueryPlan, StepStatus
from candata_agent.supervisor import (
    TOOLS,
    DraftStep,
    PlanDraft,
    PlanValidationError,
    build_agent_graph,
    period_bounds,
    validate_plan,
)
from candata_agent.supervisor.planner import ClaudePlanner, PlannerResult, PlanningError
from candata_mcp.connectors.boc_valet import Observation as ValetObservation
from candata_mcp.connectors.boc_valet import ObservationSet, SeriesDetail
from candata_mcp.connectors.statcan_wds import (
    CubeMetadata,
    CubeSearchResult,
    CubeSummary,
    Dimension,
    DimensionMember,
    Observation,
    StatCanSeriesResult,
)

GT05_QUESTION = (
    "How many housing units were started in the Toronto CMA in calendar year 2025, "
    "and how does that compare with 2024?"
)
GT13_QUESTION = "How many times did the Bank of Canada change its policy rate in 2025?"
GT12_QUESTION = (
    "In August 2026, how did shelter prices in Toronto change year over year, compared with "
    "overall consumer prices?"
)

# v42127475 (34-10-0154-01), Toronto CMA housing starts, total units, Jan 2024 to Dec 2025, as
# published by WDS on 2026-11-02. Sums: 37,718 (2024) and 26,087 (2025).
STARTS = (
    4005, 4649, 3494, 3054, 4480, 2847, 5523, 2163, 1733, 2489, 2301, 980,
    2368, 1479, 1225, 2290, 3512, 1701, 1720, 2156, 3678, 1445, 2051, 2462,
)  # fmt: skip

# V39079, target for the overnight rate in 2025: four cuts, 3.25 -> 2.25.
POLICY_RATE = (
    ("2025-01-02", 3.25),
    ("2025-01-30", 3.00),
    ("2025-03-13", 2.75),
    ("2025-09-18", 2.50),
    ("2025-10-30", 2.25),
    ("2025-12-31", 2.25),
)


# 18-10-0004-01, Toronto CPI (2002=100), Aug 2025 to Aug 2026, as published by WDS on 2026-11-03.
# Shelter v41692889: 191.4 -> 190.5 (-0.47%). All-items v41692888: 168.1 -> 171.7 (+2.14%).
SHELTER = (
    191.4, 191.3, 192.0, 191.7, 191.6, 190.8, 190.2, 190.7, 190.4, 190.0, 190.0, 189.3, 190.5,
)  # fmt: skip
ALL_ITEMS = (
    168.1, 168.1, 168.4, 168.6, 168.4, 167.7, 168.4, 169.7, 170.0, 171.7, 170.9, 171.4, 171.7,
)  # fmt: skip
CPI_RELEASES = (
    "2025-09-16", "2025-10-21", "2025-11-17", "2025-12-15", "2026-01-19", "2026-02-17",
    "2026-03-16", "2026-04-20", "2026-05-19", "2026-06-22", "2026-07-20", "2026-08-17",
    "2026-09-14",
)  # fmt: skip


def cpi_series(vector_id: int, coordinate: str, values: tuple[float, ...]) -> StatCanSeriesResult:
    months = [f"{2025 + (7 + i) // 12}-{(7 + i) % 12 + 1:02d}-01" for i in range(len(values))]
    observations = tuple(
        Observation(ref, v, 1, f"{released}T08:30", 0, 6, 0, 0)
        for ref, v, released in zip(months, values, CPI_RELEASES, strict=True)
    )
    return StatCanSeriesResult(
        product_id=18100004,
        coordinate=coordinate,
        vector_id=vector_id,
        title_en="Consumer Price Index, monthly, not seasonally adjusted",
        title_fr=None,
        frequency_code=6,
        unit="2002=100",
        observations=observations,
        fetched_at="2026-11-03T00:00:00+00:00",
    )


def starts_series() -> StatCanSeriesResult:
    months = [f"{y}-{m:02d}-01" for y in (2024, 2025) for m in range(1, 13)]
    observations = tuple(
        Observation(ref, float(v), 0, "2026-01-21T08:30", 0, 6, 0, 0)
        for ref, v in zip(months, STARTS, strict=True)
    )
    return StatCanSeriesResult(
        product_id=34100154,
        coordinate="23.1.1.0.0.0.0.0.0.0",
        vector_id=42127475,
        title_en="CMHC housing starts, under construction and completions, monthly",
        title_fr=None,
        frequency_code=6,
        unit="Units",
        observations=observations,
        fetched_at="2026-11-02T00:00:00+00:00",
    )


class FakeStatCan:
    """Serves series by reference-period range, the way WDS does."""

    def __init__(self, *series: StatCanSeriesResult) -> None:
        self.by_vector = {s.vector_id: s for s in (series or (starts_series(),))}
        self.series = next(iter(self.by_vector.values()))
        self.calls: list[tuple[str, str, str | None]] = []

    async def get_data_by_reference_period(
        self, vector_id: int | str, start: str, end: str | None = None
    ) -> StatCanSeriesResult:
        self.calls.append((str(vector_id), start, end))
        series = self.by_vector.get(int(str(vector_id).lstrip("v")))
        if series is None:
            raise LookupError(f"vector {vector_id} not found")
        last = end or start
        kept = tuple(o for o in series.observations if start <= o.ref_per <= last)
        return StatCanSeriesResult(**{**_fields(series), "observations": kept})

    async def search_cubes(self, query: str, *, limit: int = 10) -> CubeSearchResult:
        cube = CubeSummary(
            34100154, "34-10-0154-01", None, "CMHC housing starts", None, None, None, None, 6,
            "Monthly",
        )  # fmt: skip
        return CubeSearchResult(total_results=1, cubes=(cube,))

    async def get_cube_metadata(self, product_id: int | str) -> CubeMetadata:
        geo = Dimension(
            1, "Geography", None, False, (DimensionMember(23, None, "Toronto", None, None),)
        )
        title = "CMHC housing starts"
        return CubeMetadata(34100154, None, title, None, None, None, None, 6, "Monthly", (geo,))

    async def get_data_from_cube(
        self, product_id: int | str, coordinate: str, latest_n: int = 1
    ) -> StatCanSeriesResult:
        return self.series


def _fields(series: StatCanSeriesResult) -> dict[str, Any]:
    return {name: getattr(series, name) for name in series.__slots__}  # type: ignore[attr-defined]


class FakeValet:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None, str | None]] = []

    async def get_observations(
        self, series_id: str, *, start_date: str | None = None, end_date: str | None = None
    ) -> ObservationSet:
        self.calls.append((series_id, start_date, end_date))
        detail = SeriesDetail(
            series_id, "Target for the overnight rate", "", "daily", "%", None, ""
        )
        kept = tuple(
            ValetObservation(d, v)
            for d, v in POLICY_RATE
            if (start_date or d) <= d <= (end_date or d)
        )
        return ObservationSet(detail, kept, "2026-11-02T00:00:00+00:00")


def draft(*steps: tuple[str, dict[str, Any]], objective: str = "answer") -> PlanDraft:
    return PlanDraft(
        objective=objective,
        steps=tuple(DraftStep(tool=t, args_json=json.dumps(a), description="") for t, a in steps),
    )


GT05_DRAFT = draft(
    ("fetch_statcan_vector", {"vector_id": "v42127475", "start": "2024", "end": "2025"}),
    ("calendar_year_aggregation", {"agg_func": "SUM"}),
    objective="Toronto CMA housing starts, 2025 vs 2024",
)
GT13_DRAFT = draft(
    ("fetch_valet_series", {"series_id": "V39079", "start": "2025", "end": "2025"}),
    ("discrete_regime_change_counter", {"year": 2025}),
    objective="Policy rate changes in 2025",
)


class ScriptedPlanner:
    """Returns prepared plans in order, as the planner would after discovery."""

    def __init__(self, *outcomes: PlannerResult | Exception) -> None:
        self.outcomes = list(outcomes)
        self.questions: list[str] = []

    async def plan(self, question: str) -> PlannerResult:
        self.questions.append(question)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def planned(plan_draft: PlanDraft) -> PlannerResult:
    return PlannerResult(validate_plan(plan_draft), None, input_tokens=1200, output_tokens=300)


def user(text: str) -> AgentMessage:
    return AgentMessage(role=MessageRole.USER, content=text)


@pytest_asyncio.fixture
async def saver() -> AsyncGenerator[AsyncSqliteSaver, None]:
    with tempfile.TemporaryDirectory() as tmpdir:
        async with AsyncSqliteSaver(Path(tmpdir) / "can22.db") as checkpointer:
            yield checkpointer


# ---------------------------------------------------------------------------------------------
# Plan validation
# ---------------------------------------------------------------------------------------------


def test_valid_plan_becomes_executable_steps() -> None:
    plan = validate_plan(GT05_DRAFT)
    fetch, aggregate = plan.steps
    assert (fetch.assigned_agent, fetch.tool_name) == ("data_fetcher", "fetch_statcan_vector")
    assert fetch.tool_args == {
        "vector_id": "v42127475",
        "start": "2024",
        "end": "2025",
        "into": "series_table",
    }
    assert aggregate.assigned_agent == "data_analyst"
    # The analyst cites the series the fetcher loaded, not an ID the model typed.
    assert aggregate.tool_args == {
        "agg_func": "SUM",
        "expected_periods": 12,
        "slot": "series_table",
        "series_id": "v42127475",
    }
    assert plan.active_step_id == 1
    assert not plan.completed


def test_every_problem_is_reported_at_once() -> None:
    bad = PlanDraft(
        objective="x",
        steps=(
            DraftStep(
                tool="fetch_statcan_vector",
                args_json='{"vector_id": "v0", "start": "2024", "end": "2025"}',
                description="",
            ),  # fmt: skip
            DraftStep(
                tool="fetch_valet_series",
                args_json=json.dumps(
                    {"series_id": "V39079", "start": "2025", "end": "2024", "into": "table_a"}
                ),
                description="",
            ),  # fmt: skip
            DraftStep(tool="read_csv", args_json="{}", description=""),
            DraftStep(tool="yoy_point_to_point", args_json="{not json", description=""),
            DraftStep(tool="affordability_burden_ratio", args_json="{}", description=""),
        ),
    )
    with pytest.raises(PlanValidationError) as raised:
        validate_plan(bad)
    problems = "\n".join(raised.value.problems)
    assert "step 1 (fetch_statcan_vector): vector_id" in problems
    assert "start 2025 is after end 2024" in problems
    assert "step 3 (read_csv): unknown tool" in problems
    assert "step 4 (yoy_point_to_point): args_json is not valid JSON" in problems
    assert "no earlier fetch step fills rent_table, income_table" in problems


def test_model_cannot_supply_identifiers_or_extra_arguments() -> None:
    with pytest.raises(PlanValidationError, match="series_id: Extra inputs"):
        validate_plan(
            draft(
                (
                    "fetch_statcan_vector",
                    {"vector_id": "v42127475", "start": "2024", "end": "2025"},
                ),  # fmt: skip
                ("calendar_year_aggregation", {"series_id": "v1"}),
            )
        )


def test_a_slot_holds_one_series() -> None:
    with pytest.raises(PlanValidationError, match="slot 'series_table' is already filled"):
        validate_plan(
            draft(
                ("fetch_statcan_vector", {"vector_id": "v1", "start": "2024", "end": "2025"}),
                ("fetch_statcan_vector", {"vector_id": "v2", "start": "2024", "end": "2025"}),
            )
        )


GT12_DRAFT = draft(
    ("fetch_statcan_vector", {"vector_id": "v41692889", "start": "2025-08", "end": "2026-08",
                              "into": "table_a"}),
    ("fetch_statcan_vector", {"vector_id": "v41692888", "start": "2025-08", "end": "2026-08",
                              "into": "table_b"}),
    ("yoy_point_to_point", {"slot": "table_a"}),
    ("yoy_point_to_point", {"slot": "table_b"}),
    objective="Toronto shelter vs all-items CPI, Aug 2026 year over year",
)  # fmt: skip


def test_single_series_recipes_can_read_any_filled_slot() -> None:
    """GT-10/11/12: one recipe per series, each citing the series in the slot it reads."""
    plan = validate_plan(GT12_DRAFT)
    shelter, all_items = plan.steps[2], plan.steps[3]
    assert (shelter.tool_args["slot"], shelter.tool_args["series_id"]) == ("table_a", "v41692889")
    assert (all_items.tool_args["slot"], all_items.tool_args["series_id"]) == (
        "table_b",
        "v41692888",
    )
    with pytest.raises(PlanValidationError, match="no earlier fetch step fills table_b"):
        validate_plan(
            draft(
                ("fetch_statcan_vector", {"vector_id": "v1", "start": "2024", "end": "2025"}),
                ("yoy_point_to_point", {"slot": "table_b"}),
            )
        )


def test_impossible_dates_are_rejected_before_anything_runs() -> None:
    def fetch(start: str, end: str) -> PlanDraft:
        return draft(("fetch_statcan_vector", {"vector_id": "v1", "start": start, "end": end}))

    for bad in ("2025-02-29", "2025-02-30", "2025-04-31"):
        with pytest.raises(PlanValidationError, match=f"{bad} is not a calendar date"):
            validate_plan(fetch("2025-01-01", bad))
    assert (
        validate_plan(fetch("2024-02-29", "2024-02-29")).steps[0].tool_args["end"] == "2024-02-29"
    )


def test_vectors_must_come_from_discovery_when_the_planner_says_so() -> None:
    confirmed = {"v41692889"}
    with pytest.raises(PlanValidationError) as raised:
        validate_plan(GT12_DRAFT, confirmed_vectors=confirmed)
    problems = "\n".join(raised.value.problems)
    assert "step 2 (fetch_statcan_vector): vector v41692888 was not returned by lookup_series" in (
        problems
    )
    assert "v41692889" not in problems
    # Valet series names are not looked up, so the check does not apply to them.
    assert validate_plan(GT13_DRAFT, confirmed_vectors=set()).steps[0].tool_args["series_id"] == (
        "V39079"
    )


def test_recipes_that_need_typed_numbers_or_sql_are_not_offered() -> None:
    assert {"multi_year_cagr", "custom_sql", "cross_geography_ranking"}.isdisjoint(TOOLS)


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        ("2025", "2025", ("2025-01-01", "2025-12-31")),
        ("2024-02", "2024-02", ("2024-02-01", "2024-02-29")),
        ("2025-08-15", "2025-09", ("2025-08-15", "2025-09-30")),
    ],
)
def test_period_bounds_cover_whole_periods(start: str, end: str, expected: tuple[str, str]) -> None:
    assert period_bounds(start, end) == expected


# ---------------------------------------------------------------------------------------------
# Claude planner loop (fake Messages API)
# ---------------------------------------------------------------------------------------------


def message(*content: dict[str, Any], stop: str = "tool_use") -> BetaMessage:
    return BetaMessage.model_validate(
        {
            "id": "msg_1",
            "type": "message",
            "role": "assistant",
            "model": "claude-opus-5-5",
            "content": list(content),
            "stop_reason": stop,
            "stop_sequence": None,
            "usage": {"input_tokens": 1000, "output_tokens": 100},
        }
    )


def tool_use(call_id: str, name: str, args: dict[str, Any]) -> dict[str, Any]:
    return {"type": "tool_use", "id": call_id, "name": name, "input": args}


def submit(plan_draft: PlanDraft) -> dict[str, Any]:
    return {
        "objective": plan_draft.objective,
        "steps": [s.model_dump() for s in plan_draft.steps],
    }


class FakeMessages:
    def __init__(self, *responses: BetaMessage) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []

    async def create(self, **request: Any) -> BetaMessage:
        self.requests.append({**request, "messages": list(request["messages"])})
        return self.responses.pop(0)


class FakeClient:
    def __init__(self, *responses: BetaMessage) -> None:
        self.messages = FakeMessages(*responses)
        self.beta = self


def planner_with(*responses: BetaMessage, max_turns: int = 6) -> tuple[ClaudePlanner, FakeClient]:
    client = FakeClient(*responses)
    planner = ClaudePlanner(cast(AsyncAnthropic, client), FakeStatCan(), max_turns=max_turns)
    return planner, client


async def test_planner_discovers_then_fixes_an_invalid_plan() -> None:
    bad = draft(("fetch_statcan_vector", {"vector_id": "v0", "start": "2024", "end": "2025"}))
    planner, client = planner_with(
        message(
            tool_use("t1", "lookup_series", {"table_id": "34-10-0154-01", "coordinate": "23.1.1"})
        ),  # fmt: skip
        message(tool_use("t2", "submit_plan", submit(bad))),
        message(tool_use("t3", "submit_plan", submit(GT05_DRAFT))),
    )
    result = await planner.plan(GT05_QUESTION)

    assert result.plan is not None
    assert [s.tool_name for s in result.plan.steps] == [
        "fetch_statcan_vector",
        "calendar_year_aggregation",
    ]
    assert (result.input_tokens, result.output_tokens) == (3000, 300)

    discovery = client.messages.requests[1]["messages"][-1]["content"][0]
    assert discovery["tool_use_id"] == "t1" and not discovery["is_error"]
    assert json.loads(discovery["content"])["vector_id"] == "v42127475"
    feedback = client.messages.requests[2]["messages"][-1]["content"][0]
    assert feedback["is_error"] and "vector_id" in feedback["content"]

    first = client.messages.requests[0]
    assert first["model"] == "claude-opus-5-5"
    assert first["fallbacks"] == "default"
    assert "tool_choice" not in first  # forced tool use is rejected on current models
    assert all(tool["strict"] for tool in first["tools"])


async def test_planner_rejects_a_vector_it_did_not_look_up() -> None:
    planner, client = planner_with(
        message(tool_use("t1", "submit_plan", submit(GT05_DRAFT))),
        message(
            tool_use("t2", "lookup_series", {"table_id": "34-10-0154-01", "coordinate": "23.1.1"})
        ),  # fmt: skip
        message(tool_use("t3", "submit_plan", submit(GT05_DRAFT))),
    )
    result = await planner.plan(GT05_QUESTION)
    assert result.plan is not None
    feedback = client.messages.requests[1]["messages"][-1]["content"][0]
    assert feedback["is_error"]
    assert "vector v42127475 was not returned by lookup_series" in feedback["content"]


async def test_planner_declines_when_official_data_does_not_exist() -> None:
    planner, _ = planner_with(
        message(tool_use("t1", "decline", {"reason": "No Toronto mortgage interest cost index"})),
    )
    result = await planner.plan("Toronto mortgage interest cost inflation in 2025?")
    assert result.plan is None
    assert result.declined_reason == "No Toronto mortgage interest cost index"


async def test_planner_stops_on_refusal_and_on_turn_budget() -> None:
    planner, _ = planner_with(message(stop="refusal"))
    with pytest.raises(PlanningError, match="declined"):
        await planner.plan(GT05_QUESTION)

    chatter = message({"type": "text", "text": "Let me think."}, stop="end_turn")
    planner, client = planner_with(chatter, chatter, max_turns=2)
    with pytest.raises(PlanningError, match="no valid plan within 2 turns"):
        await planner.plan(GT05_QUESTION)
    assert client.messages.requests[1]["messages"][-1]["content"].startswith("Finish by calling")


# ---------------------------------------------------------------------------------------------
# Full graph
# ---------------------------------------------------------------------------------------------


async def test_graph_answers_two_questions_on_one_thread(saver: AsyncSqliteSaver) -> None:
    statcan, valet = FakeStatCan(), FakeValet()
    planner = ScriptedPlanner(planned(GT05_DRAFT), planned(GT13_DRAFT))
    app = build_agent_graph(planner=planner, statcan=statcan, valet=valet, checkpointer=saver)
    config = {"configurable": {"thread_id": "t1"}}

    first = await app.ainvoke(
        {"session_id": "s1", "thread_id": "t1", "messages": (user(GT05_QUESTION),)}, config
    )
    totals = {r["cal_year"]: r["aggregated_total"] for r in first["sql_artifacts"][-1].rows}
    assert totals == {"2025": 26087.0, "2024": 37718.0}
    assert first["plan"].completed
    assert first["verification"]["passed"] is True
    assert [v["code"] for v in first["verification"]["verdicts"]] == ["verified"]
    assert first["token_budget"].total_tokens_used == 1500
    assert statcan.calls[0] == ("v42127475", "2024-01-01", "2025-12-31")
    speakers = [m.name for m in first["messages"] if m.role is MessageRole.ASSISTANT]
    assert speakers == ["supervisor", "data_fetcher", "data_analyst", "citation_verifier"]

    second = await app.ainvoke({"messages": (user(GT13_QUESTION),)}, config)
    counter = second["sql_artifacts"][-1].rows[0]
    assert (counter["rate_change_count"], counter["year_start_rate"], counter["year_end_rate"]) == (
        4,
        3.25,
        2.25,
    )
    assert planner.questions == [GT05_QUESTION, GT13_QUESTION]
    # Only this question's citation is verified again.
    verdicts = second["verification"]["verdicts"]
    verified = [v["claim"]["citation"]["core"]["vector_id"] for v in verdicts]
    assert verified == ["V39079"]
    assert second["token_budget"].total_tokens_used == 3000


async def test_failed_fetch_ends_the_run_without_verification(saver: AsyncSqliteSaver) -> None:
    unknown = draft(("fetch_statcan_vector", {"vector_id": "v999", "start": "2024", "end": "2025"}))
    app = build_agent_graph(
        planner=ScriptedPlanner(planned(GT05_DRAFT), planned(unknown)),
        statcan=FakeStatCan(),
        valet=FakeValet(),
        checkpointer=saver,
    )
    config = {"configurable": {"thread_id": "t2"}}
    first = await app.ainvoke(
        {"session_id": "s1", "thread_id": "t2", "messages": (user(GT05_QUESTION),)}, config
    )
    assert first["verification"]["passed"] is True

    out = await app.ainvoke({"messages": (user("?"),)}, config)
    plan = cast(QueryPlan, out["plan"])
    assert plan.steps[0].status is StepStatus.FAILED
    assert "vector v999 not found" in (plan.steps[0].result_summary or "")
    assert out.get("verification") is None  # the first question's report is not carried over


async def test_graph_compares_two_series_and_verifies_both(saver: AsyncSqliteSaver) -> None:
    statcan = FakeStatCan(
        cpi_series(41692889, "16.79.0.0.0.0.0.0.0.0", SHELTER),
        cpi_series(41692888, "16.2.0.0.0.0.0.0.0.0", ALL_ITEMS),
    )
    planner = ScriptedPlanner(planned(GT12_DRAFT), planned(GT12_DRAFT))
    app = build_agent_graph(planner=planner, statcan=statcan, valet=FakeValet(), checkpointer=saver)
    config = {"configurable": {"thread_id": "gt12"}}

    for turn in (1, 2):  # the second turn re-asks the same question on the same thread
        out = await app.ainvoke(
            {"session_id": "s", "thread_id": "gt12", "messages": (user(GT12_QUESTION),)}, config
        )
        shelter, all_items = out["sql_artifacts"][-2:]
        assert _august_2026_change(shelter.rows) == pytest.approx(-0.47, abs=0.01)
        assert _august_2026_change(all_items.rows) == pytest.approx(2.14, abs=0.01)
        assert (shelter.source_series_id, all_items.source_series_id) == ("v41692889", "v41692888")
        verified = [
            v["claim"]["citation"]["core"]["vector_id"] for v in out["verification"]["verdicts"]
        ]
        assert sorted(verified) == ["v41692888", "v41692889"]
        assert out["verification"]["passed"] is True
        assert len(planner.questions) == turn


def _august_2026_change(rows: tuple[dict[str, Any], ...]) -> float:
    (row,) = [r for r in rows if str(r["obs_date"]).startswith("2026-08")]
    return float(row["change_pct"])


async def test_retrying_a_failed_question_plans_it_again(saver: AsyncSqliteSaver) -> None:
    unknown = draft(("fetch_statcan_vector", {"vector_id": "v999", "start": "2024", "end": "2025"}))
    planner = ScriptedPlanner(planned(unknown), planned(GT05_DRAFT))
    app = build_agent_graph(
        planner=planner, statcan=FakeStatCan(), valet=FakeValet(), checkpointer=saver
    )
    config = {"configurable": {"thread_id": "retry"}}
    first = await app.ainvoke(
        {"session_id": "s", "thread_id": "retry", "messages": (user(GT05_QUESTION),)}, config
    )
    assert first["plan"].steps[0].status is StepStatus.FAILED

    second = await app.ainvoke({"messages": (user(GT05_QUESTION),)}, config)
    assert planner.questions == [GT05_QUESTION, GT05_QUESTION]
    totals = {r["cal_year"]: r["aggregated_total"] for r in second["sql_artifacts"][-1].rows}
    assert totals == {"2025": 26087.0, "2024": 37718.0}
    assert second["verification"]["passed"] is True


async def test_decline_and_planner_errors_end_the_run_with_a_message(
    saver: AsyncSqliteSaver,
) -> None:
    planner = ScriptedPlanner(
        PlannerResult(None, "StatCan does not publish this for Toronto"),
        PlanningError("no valid plan within 12 turns"),
    )
    app = build_agent_graph(
        planner=planner, statcan=FakeStatCan(), valet=FakeValet(), checkpointer=saver
    )
    config = {"configurable": {"thread_id": "t3"}}
    out = await app.ainvoke(
        {"session_id": "s", "thread_id": "t3", "messages": (user("a"),)}, config
    )
    assert out["plan"] is None
    assert out["messages"][-1].content == "Declined: StatCan does not publish this for Toronto"

    out = await app.ainvoke({"messages": (user("b"),)}, config)
    assert out["messages"][-1].content.startswith("Planning failed: PlanningError")


async def test_forked_thread_continues_with_the_graph(saver: AsyncSqliteSaver) -> None:
    """The CAN-21 follow-up: a fork from arollback_to must be resumable by the graph."""
    planner = ScriptedPlanner(planned(GT05_DRAFT), planned(GT13_DRAFT), planned(GT13_DRAFT))
    app = build_agent_graph(
        planner=planner, statcan=FakeStatCan(), valet=FakeValet(), checkpointer=saver
    )
    t1 = {"configurable": {"thread_id": "t1"}}
    first_input = {"session_id": "sess-A", "thread_id": "t1", "messages": (user(GT05_QUESTION),)}
    await app.ainvoke(first_input, t1)
    after_first = (await app.aget_state(t1)).config["configurable"]["checkpoint_id"]
    await app.ainvoke({"messages": (user(GT13_QUESTION),)}, t1)

    forked = await saver.arollback_to("t1", after_first, new_thread_id="fork1")
    assert (forked.session_id, forked.thread_id) == ("sess-A", "fork1")

    out = await app.ainvoke(
        {"messages": (user(GT13_QUESTION),)}, {"configurable": {"thread_id": "fork1"}}
    )
    assert out["session_id"] == "sess-A"
    assert out["thread_id"] == "fork1"
    assert out["sql_artifacts"][-1].rows[0]["rate_change_count"] == 4
    asked = [m.content for m in out["messages"] if m.role is MessageRole.USER]
    assert asked == [GT05_QUESTION, GT13_QUESTION]  # the fork starts after question 1

    original = (await app.aget_state(t1)).values
    assert len([m for m in original["messages"] if m.role is MessageRole.USER]) == 2


# ---------------------------------------------------------------------------------------------
# Live: real Claude planner with real StatCan discovery (costs API tokens; `pytest -m live`)
# ---------------------------------------------------------------------------------------------


@pytest.mark.live
async def test_live_claude_plans_gt05_from_discovery() -> None:
    from candata_mcp.connectors.statcan_wds import StatCanClient

    async with StatCanClient() as statcan:
        planner = ClaudePlanner(AsyncAnthropic(), statcan)
        result = await planner.plan(GT05_QUESTION)
    assert result.plan is not None, result.declined_reason
    fetched = {s.tool_args.get("vector_id") for s in result.plan.steps}
    assert fetched & {"v42127475", "v42127955"}  # monthly table or the annual one
