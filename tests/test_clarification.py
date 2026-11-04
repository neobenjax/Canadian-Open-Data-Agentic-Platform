"""Tests for CAN-33: pausing the agent with ``interrupt()`` when a term is ambiguous.

The planner tests drive ``ClaudePlanner`` through a fake Messages API and a StatCan table with
two members named "Smiths Falls, Ontario" (the guardrail 6 example). The graph tests run the
real graph with a SQLite checkpointer. They pause, resume, replay and fork on one thread
(guardrail 26).
"""

import json
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from langgraph.types import Command

from candata_agent.checkpoint import AsyncSqliteSaver
from candata_agent.state import AgentMessage, MessageRole
from candata_agent.supervisor import build_agent_graph
from candata_agent.supervisor.clarification import (
    MAX_CLARIFICATIONS,
    Candidate,
    Clarification,
    Resolution,
)
from candata_agent.supervisor.node import CLARIFICATIONS, HUMAN_CLARIFICATION, PLANNER_AUDIT
from candata_agent.supervisor.planner import PlannerResult
from candata_agent.ui import ClarificationNeeded, RunFinished, stream_question
from candata_mcp.connectors.statcan_wds import CubeMetadata, Dimension, DimensionMember
from tests.test_supervisor import (
    GT05_DRAFT,
    FakeStatCan,
    FakeValet,
    ScriptedPlanner,
    message,
    planned,
    planner_with,
    submit,
    tool_use,
)

QUESTION = "How many housing units were started in Smiths Falls in 2025?"
TABLE = "34-10-0154-01"
CA, TOWN, OTTAWA = 1, 2, 3
SMITHS_FALLS = Clarification(
    term="Smiths Falls",
    table_id=TABLE,
    dimension_position=1,
    dimension="Geography",
    question="Which Smiths Falls do you mean?",
    candidates=(
        Candidate(CA, "Smiths Falls, Ontario (census agglomeration)"),
        Candidate(TOWN, "Smiths Falls, Ontario (town)"),
    ),
)


def asks(clarification: Clarification = SMITHS_FALLS) -> PlannerResult:
    return PlannerResult(None, None, 900, 90, (), clarification)


def chose(member_id: int) -> Resolution:
    name = next(c.name for c in SMITHS_FALLS.candidates if c.member_id == member_id)
    return Resolution("Smiths Falls", TABLE, 1, member_id, name)


# ---------------------------------------------------------------------------------------------
# Matching an answer to an option
# ---------------------------------------------------------------------------------------------


def test_an_answer_picks_an_option_by_id_or_exact_name_only() -> None:
    town = SMITHS_FALLS.candidates[1]
    for answer in (TOWN, "2", " 2 ", "smiths falls, ontario (town)", {"member_id": 2}):
        assert SMITHS_FALLS.choose(answer) == town, answer
    for answer in (99, "Smiths Falls", True, None, {"name": "Ottawa"}, 2.0):
        assert SMITHS_FALLS.choose(answer) is None, answer
    assert Clarification.from_json(json.loads(json.dumps(SMITHS_FALLS.to_json()))) == SMITHS_FALLS


# ---------------------------------------------------------------------------------------------
# Planner: same-name members are marked, refused, and offered only as discovered
# ---------------------------------------------------------------------------------------------


class TwoSmithsFalls(FakeStatCan):
    async def get_cube_metadata(self, product_id: int | str) -> CubeMetadata:
        geo = Dimension(
            1,
            "Geography",
            None,
            False,
            (
                DimensionMember(CA, None, "Smiths Falls, Ontario", None, None),
                DimensionMember(TOWN, None, "Smiths  Falls, Ontario", None, None),  # spacing
                DimensionMember(OTTAWA, None, "Ottawa, Ontario", None, None),
            ),
        )
        return CubeMetadata(
            34100154, None, "Housing starts", None, None, None, None, 6, "Monthly", (geo,)
        )


def planner_on_two_smiths_falls(*responses: Any) -> tuple[Any, Any]:
    planner, client = planner_with(*responses)
    planner._statcan = TwoSmithsFalls()  # pyright: ignore[reportPrivateUsage]
    return planner, client


async def test_the_planner_must_ask_before_using_a_member_whose_name_is_shared() -> None:
    find = {"table_id": TABLE, "dimension": "Geography", "query": "Smiths Falls"}
    ask = {"term": "Smiths Falls", "table_id": TABLE, "dimension_position": 1,
           "question": "Which Smiths Falls do you mean?"}  # fmt: skip
    planner, client = planner_on_two_smiths_falls(
        message(tool_use("t1", "find_members", find)),
        message(tool_use("t2", "lookup_series", {"table_id": TABLE, "coordinate": "1"})),
        message(tool_use("t3", "request_clarification", {**ask, "member_ids": [CA, OTTAWA]})),
        message(tool_use("t4", "request_clarification", {**ask, "member_ids": [CA, TOWN]})),
    )
    result = await planner.plan(QUESTION)

    found = json.loads(client.messages.requests[1]["messages"][-1]["content"][0]["content"])
    marks = {
        m["member_id"]: m.get("same_name_as_another_member") for m in found["dims"][0]["matches"]
    }
    assert marks == {CA: True, TOWN: True}  # Ottawa doesn't match the query

    refused = client.messages.requests[2]["messages"][-1]["content"][0]
    assert refused["is_error"] and "request_clarification" in refused["content"]
    unknown = client.messages.requests[3]["messages"][-1]["content"][0]
    assert unknown["is_error"] and "3 were not returned by find_members" in unknown["content"]

    assert result.plan is None and result.clarification is not None
    assert [c.member_id for c in result.clarification.candidates] == [CA, TOWN]
    assert result.clarification.dimension == "Geography"
    assert [(r.tool, r.outcome) for r in result.audit] == [
        ("find_members", "ok"),
        ("lookup_series", "rejected"),
        ("request_clarification", "rejected"),
        ("request_clarification", "ok"),
    ]


async def test_after_the_user_chooses_the_planner_may_use_that_member_only() -> None:
    find = {"table_id": TABLE, "dimension": "", "query": "Smiths Falls"}
    planner, client = planner_on_two_smiths_falls(
        message(tool_use("t1", "find_members", find)),
        message(tool_use("t2", "lookup_series", {"table_id": TABLE, "coordinate": "1"})),
        message(tool_use("t3", "lookup_series", {"table_id": TABLE, "coordinate": "2"})),
        message(tool_use("t4", "submit_plan", submit(GT05_DRAFT))),
    )
    result = await planner.plan(QUESTION, resolved=[chose(TOWN)])

    first = client.messages.requests[0]["messages"][0]["content"]
    assert first.startswith(QUESTION) and "member 2 in dimension 1 of table" in first
    assert [(r.tool, r.outcome) for r in result.audit] == [
        ("find_members", "ok"),
        ("lookup_series", "rejected"),  # the member the user did not choose
        ("lookup_series", "ok"),
        ("submit_plan", "ok"),
    ]
    assert result.plan is not None


# ---------------------------------------------------------------------------------------------
# The graph: pause, resume, replay and fork on one thread (guardrail 26)
# ---------------------------------------------------------------------------------------------


@pytest_asyncio.fixture
async def saver(tmp_path: Path) -> AsyncGenerator[AsyncSqliteSaver, None]:
    async with AsyncSqliteSaver(tmp_path / "clarify.db") as checkpointer:
        yield checkpointer


def ask(text: str) -> dict[str, Any]:
    return {
        "session_id": "s",
        "thread_id": "t",
        "messages": (AgentMessage(role=MessageRole.USER, content=text),),
    }


CONFIG: Any = {"configurable": {"thread_id": "t"}}


def graph(saver: AsyncSqliteSaver, planner: ScriptedPlanner) -> Any:
    return build_agent_graph(
        planner=planner, statcan=FakeStatCan(), valet=FakeValet(), checkpointer=saver
    )


async def paused_payload(app: Any) -> dict[str, Any]:
    snapshot = await app.aget_state(CONFIG)
    assert snapshot.next == (HUMAN_CLARIFICATION,)
    (value,) = [i.value for task in snapshot.tasks for i in task.interrupts]
    return value


async def test_an_ambiguous_question_pauses_and_resumes_with_the_users_choice(
    saver: AsyncSqliteSaver,
) -> None:
    planner = ScriptedPlanner(asks(), planned(GT05_DRAFT), planned(GT05_DRAFT))
    app = graph(saver, planner)

    await app.ainvoke(ask(QUESTION), CONFIG)
    payload = await paused_payload(app)
    assert payload["question"] == "Which Smiths Falls do you mean?"
    assert [o["member_id"] for o in payload["options"]] == [CA, TOWN] and "error" not in payload
    state = (await app.aget_state(CONFIG)).values
    assert state["active_interrupt"].interrupt_type == "ambiguous_member"
    assert state["messages"][-1].content.startswith("Needs clarification:")

    await app.ainvoke(Command(resume="Smiths Falls"), CONFIG)  # not one of the options
    assert "not one of the options" in (await paused_payload(app))["error"]
    assert len(planner.questions) == 1  # a bad answer never re-runs the planner

    done = await app.ainvoke(Command(resume=TOWN), CONFIG)
    assert done["verification"]["passed"]
    assert planner.questions == [QUESTION, QUESTION]
    assert planner.resolved == [(), (chose(TOWN),)]
    saved = (await app.aget_state(CONFIG)).values
    assert saved["active_interrupt"] is None and saved["scratchpad"][CLARIFICATIONS] == [
        chose(TOWN).to_json()
    ]
    contents = [m.content for m in saved["messages"]]
    assert any(c.startswith("Needs clarification:") for c in contents)  # merged, not replaced
    assert 'Clarified: "Smiths Falls" means Smiths Falls, Ontario (town) (member 2).' in contents
    assert PLANNER_AUDIT in saved["scratchpad"]

    # Time travel: fork from the paused checkpoint and choose the other member instead.
    history = [h async for h in app.aget_state_history(CONFIG)]
    paused = next(h for h in reversed(history) if h.next == (HUMAN_CLARIFICATION,))
    forked = await app.ainvoke(Command(resume=CA), paused.config)
    assert forked["verification"]["passed"] and planner.resolved[-1] == (chose(CA),)


async def test_cancelling_declines_without_planning_again(saver: AsyncSqliteSaver) -> None:
    planner = ScriptedPlanner(asks())
    app = graph(saver, planner)
    await app.ainvoke(ask(QUESTION), CONFIG)
    done = await app.ainvoke(Command(resume="cancel"), CONFIG)
    assert done["plan"] is None and done["active_interrupt"] is None
    assert done["messages"][-1].content == "Declined: the clarification was cancelled."
    assert planner.questions == [QUESTION]


async def test_a_new_question_replaces_an_unanswered_clarification(
    saver: AsyncSqliteSaver,
) -> None:
    planner = ScriptedPlanner(asks(), planned(GT05_DRAFT))
    app = graph(saver, planner)
    await app.ainvoke(ask(QUESTION), CONFIG)
    other = "How many housing units were started in the Toronto CMA in 2025?"
    done = await app.ainvoke(ask(other), CONFIG)
    assert done["verification"]["passed"] and done["active_interrupt"] is None
    assert planner.questions == [QUESTION, other] and planner.resolved == [(), ()]
    assert not (await app.aget_state(CONFIG)).next  # nothing left paused


async def test_the_planner_gets_at_most_three_clarifications(saver: AsyncSqliteSaver) -> None:
    planner = ScriptedPlanner(*(asks() for _ in range(MAX_CLARIFICATIONS + 1)))
    app = graph(saver, planner)
    await app.ainvoke(ask(QUESTION), CONFIG)
    for _ in range(MAX_CLARIFICATIONS):
        await paused_payload(app)
        done = await app.ainvoke(Command(resume=TOWN), CONFIG)
    assert done["messages"][-1].content.startswith("Declined: the question is still ambiguous")
    assert len(planner.questions) == MAX_CLARIFICATIONS + 1
    assert not (await app.aget_state(CONFIG)).next


# ---------------------------------------------------------------------------------------------
# UI stream
# ---------------------------------------------------------------------------------------------


async def test_the_ui_stream_reports_the_pause_and_resumes_it(saver: AsyncSqliteSaver) -> None:
    app = graph(saver, ScriptedPlanner(asks(), planned(GT05_DRAFT)))
    first = [e async for e in stream_question(app, QUESTION, thread_id="t", session_id="s")]
    (needed,) = [e for e in first if isinstance(e, ClarificationNeeded)]
    assert needed.question == "Which Smiths Falls do you mean?"
    assert needed.options == tuple((c.member_id, c.name) for c in SMITHS_FALLS.candidates)
    assert isinstance(first[-1], RunFinished) and first[-1].result.clarification == needed

    second = [
        e async for e in stream_question(app, QUESTION, thread_id="t", session_id="s", resume="2")
    ]
    result = second[-1].result if isinstance(second[-1], RunFinished) else None
    assert result is not None and result.verified and result.clarification is None
    assert [s.source for s in result.series] == ["v42127475"]
    shown = [m.content for m in result.messages]
    assert not any(c.startswith("Needs clarification") for c in shown)  # from the first run
    assert shown[0].startswith('Clarified: "Smiths Falls"')


@pytest.mark.parametrize("answer", [TOWN, "2", "Smiths Falls, Ontario (town)"])
def test_resolution_instructions_name_the_member(answer: object) -> None:
    choice = SMITHS_FALLS.choose(answer)
    assert choice is not None
    resolution = Resolution("Smiths Falls", TABLE, 1, choice.member_id, choice.name)
    assert resolution.as_instruction() == (
        'By "Smiths Falls" the user means Smiths Falls, Ontario (town) '
        "(member 2 in dimension 1 of table 34-10-0154-01). Use that member."
    )
