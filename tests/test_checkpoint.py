# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false
"""Verification tests for AsyncSqliteSaver checkpoint resumption (Issue #51).

Adheres strictly to Guardrail 26 ("Press the Start Button" Invariant):
1. Multi-turn graph invocation across seeded checkpoints.
2. Channel reducer merging (messages, citations) without overwrite.
3. Chronological step metadata progression in state history.
4. Checkpointer state roundtrip with strict type fidelity (Decimal, date, dataclasses).
5. Resuming and forking execution from past checkpoints.
"""

from __future__ import annotations

import tempfile
from collections.abc import AsyncGenerator
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from candata_agent.checkpoint import AsyncSqliteSaver, seed_thread
from candata_agent.state import (
    AgentMessage,
    AgentState,
    HITLInterrupt,
    InterruptType,
    MessageRole,
    PlanStep,
    QueryPlan,
    SQLArtifact,
    StepStatus,
    TokenBudget,
    TraceContext,
)
from candata_mcp.citation import (
    BilingualTitle,
    CitationEnvelope,
    CoreVerificationTuple,
    MetadataEnrichment,
)


@pytest_asyncio.fixture
async def checkpointer() -> AsyncGenerator[AsyncSqliteSaver, None]:
    with tempfile.TemporaryDirectory() as tmpdir:
        async with AsyncSqliteSaver(Path(tmpdir) / "checkpoints_test.db") as saver:
            yield saver


def _create_sample_citation(
    vector_id: str = "v41690973",
    ref_per: str = "2024-01",
    title: str = "Consumer Price Index",
) -> CitationEnvelope:
    return CitationEnvelope(
        publisher="Statistics Canada",
        core=CoreVerificationTuple(
            table_id="18-10-0004-01",
            vector_id=vector_id,
            reference_period=ref_per,
        ),
        enrichment=MetadataEnrichment(
            coordinate="2.1",
            release_or_revision_date="2024-02-15T08:30",
            bilingual_title=BilingualTitle(en=title, fr=None),
            canonical_url=f"https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810000401#{vector_id}",
        ),
    )


def _build_test_graph(checkpointer: AsyncSqliteSaver) -> Any:
    """Build a minimal compiled graph that exercises state channel reducers."""

    async def step_node(state: AgentState) -> dict[str, Any]:
        count = int(state.scratchpad.get("invocation_count") or 0) + 1
        return {
            "scratchpad": {
                **state.scratchpad,
                "invocation_count": count,
                "last_step": f"step_{count}",
            }
        }

    builder = StateGraph(AgentState)
    builder.add_node("step_node", step_node)
    builder.add_edge(START, "step_node")
    builder.add_edge("step_node", END)
    return builder.compile(checkpointer=checkpointer)


# ==============================================================================
# 1. Multi-Turn Resumption after aput(AgentState) (Issue #51 Core Verification)
# ==============================================================================


@pytest.mark.asyncio
async def test_checkpoint_multi_turn_resumption_after_aput_seed(
    checkpointer: AsyncSqliteSaver,
) -> None:
    """Seeding a thread with checkpointer.aput(AgentState) synthesizes valid step metadata

    allowing LangGraph to resume execution across multiple turns without KeyError: 'step'.
    """
    app = _build_test_graph(checkpointer)
    config: RunnableConfig = {"configurable": {"thread_id": "thread_resumption_test"}}

    # Initial seed state with message, citation, and SQL artifact
    init_msg = AgentMessage(
        role=MessageRole.USER,
        content="What is the CPI for 2024?",
    )
    init_cit = _create_sample_citation("v41690973", "2024-01")
    init_artifact = SQLArtifact(
        source_series_id="v41690973",
        sql_query="SELECT date, amount FROM cpi_table WHERE date = '2024-01'",
        row_count=1,
        rows=({"date": date(2024, 1, 1), "amount": Decimal("158.30")},),
    )
    initial_state = AgentState(
        session_id="session_resumption_01",
        thread_id="thread_resumption_test",
        messages=(init_msg,),
        citations=(init_cit,),
        sql_artifacts=(init_artifact,),
        scratchpad={"initial_flag": True},
    )

    # 1. Seed thread directly through checkpointer.aput(AgentState)
    put_res = await checkpointer.aput(config, initial_state)
    assert put_res["configurable"]["checkpoint_id"]

    # Verify seed checkpoint has valid step metadata synthesized
    tuple_seeded = await checkpointer.aget_tuple(config)
    assert tuple_seeded is not None
    assert tuple_seeded.metadata.get("step") == 0
    assert tuple_seeded.metadata.get("source") == "input"
    assert len(tuple_seeded.checkpoint["channel_versions"]) > 0

    # 2. Turn 1: app.ainvoke on seeded thread (MUST NOT raise KeyError: 'step')
    turn1_msg = AgentMessage(
        role=MessageRole.ASSISTANT,
        content="Here is the CPI observation for January 2024.",
    )
    turn1_cit = _create_sample_citation("v41690973", "2024-02")
    out1 = await app.ainvoke(
        {"messages": (turn1_msg,), "citations": (turn1_cit,)},
        config,
    )

    # Assert turn 1 execution succeeded
    assert out1["scratchpad"]["invocation_count"] == 1
    # Channel reducers merged rather than overwrote
    assert len(out1["messages"]) == 2
    assert out1["messages"][0].content == init_msg.content
    assert out1["messages"][1].content == turn1_msg.content
    assert len(out1["citations"]) == 2

    # 3. Turn 2: app.ainvoke on the same thread
    turn2_msg = AgentMessage(
        role=MessageRole.USER,
        content="What about the Bank of Canada policy rate?",
    )
    out2 = await app.ainvoke({"messages": (turn2_msg,)}, config)

    # Assert turn 2 execution succeeded and state channels continued to merge
    assert out2["scratchpad"]["invocation_count"] == 2
    assert len(out2["messages"]) == 3
    assert out2["messages"][2].content == turn2_msg.content
    assert len(out2["citations"]) == 2

    # 4. Check chronological integrity of history
    history = [s async for s in app.aget_state_history(config)]
    assert len(history) >= 3

    # History is ordered latest -> earliest by LangGraph conventions
    steps = [h.metadata.get("step") for h in history if h.metadata.get("step") is not None]
    assert steps == sorted(steps, reverse=True)
    assert steps[-1] == 0  # Initial seed checkpoint at step 0


# ==============================================================================
# 2. Seeding via seed_thread Helper & app.aupdate_state
# ==============================================================================


@pytest.mark.asyncio
async def test_checkpoint_seed_thread_helper_delegation(
    checkpointer: AsyncSqliteSaver,
) -> None:
    """seed_thread correctly delegates checkpoint construction and enables seamless resumption."""
    app = _build_test_graph(checkpointer)
    config: RunnableConfig = {"configurable": {"thread_id": "thread_seed_helper_test"}}

    initial_state = AgentState(
        session_id="session_seed_helper",
        thread_id="thread_seed_helper_test",
        messages=(AgentMessage(role=MessageRole.USER, content="Initial seeded prompt"),),
        scratchpad={"seeded": True},
    )

    # Seed using module-level helper
    await seed_thread(app, config, initial_state)

    # Turn 1
    out1 = await app.ainvoke(
        {"messages": (AgentMessage(role=MessageRole.ASSISTANT, content="Reply 1"),)},
        config,
    )
    assert len(out1["messages"]) == 2
    assert out1["scratchpad"]["invocation_count"] == 1

    # Turn 2 using saver.seed_thread method on another thread
    config2: RunnableConfig = {"configurable": {"thread_id": "thread_seed_method_test"}}
    await checkpointer.seed_thread(
        app,
        config2,
        AgentState(
            session_id="session_seed_method",
            thread_id="thread_seed_method_test",
            messages=(AgentMessage(role=MessageRole.USER, content="Method prompt"),),
        ),
    )
    out2 = await app.ainvoke(
        {"messages": (AgentMessage(role=MessageRole.ASSISTANT, content="Method reply"),)},
        config2,
    )
    assert len(out2["messages"]) == 2
    assert out2["scratchpad"]["invocation_count"] == 1


# ==============================================================================
# 3. Time-Travel Fork Resumption from Intermediate Checkpoints
# ==============================================================================


@pytest.mark.asyncio
async def test_time_travel_fork_resumption_from_intermediate_checkpoint(
    checkpointer: AsyncSqliteSaver,
) -> None:
    """Forking a thread via arollback_to from a multi-turn run resumes on the new thread."""
    app = _build_test_graph(checkpointer)
    main_cfg: RunnableConfig = {"configurable": {"thread_id": "main_thread"}}

    # Turn 1
    await app.ainvoke(
        {
            "session_id": "session_fork_test",
            "thread_id": "main_thread",
            "messages": (AgentMessage(role=MessageRole.USER, content="Question 1"),),
        },
        main_cfg,
    )
    checkpoint_turn1 = (await app.aget_state(main_cfg)).config["configurable"]["checkpoint_id"]

    # Turn 2
    await app.ainvoke(
        {"messages": (AgentMessage(role=MessageRole.USER, content="Question 2"),)},
        main_cfg,
    )

    # Rollback / Fork to turn 1 on a new branch thread
    fork_thread_id = "fork_branch_thread"
    forked_state = await checkpointer.arollback_to(
        thread_id="main_thread",
        target_checkpoint_id=checkpoint_turn1,
        new_thread_id=fork_thread_id,
    )
    assert forked_state.thread_id == fork_thread_id
    assert forked_state.session_id == "session_fork_test"
    assert len(forked_state.messages) == 1

    # Resume execution on the forked thread with a different follow-up question
    fork_cfg: RunnableConfig = {"configurable": {"thread_id": fork_thread_id}}
    fork_out = await app.ainvoke(
        {"messages": (AgentMessage(role=MessageRole.USER, content="Alternate Question 2"),)},
        fork_cfg,
    )

    assert fork_out["session_id"] == "session_fork_test"
    assert fork_out["thread_id"] == fork_thread_id
    # Forked messages must contain Question 1 and Alternate Question 2, but NOT Question 2
    user_contents = [m.content for m in fork_out["messages"] if m.role == MessageRole.USER]
    assert user_contents == ["Question 1", "Alternate Question 2"]


# ==============================================================================
# 4. Strict Deserialization Type Fidelity for Nested Objects
# ==============================================================================


@pytest.mark.asyncio
async def test_deserialization_fidelity_nested_pydantic_and_dataclasses(
    checkpointer: AsyncSqliteSaver,
) -> None:
    """aget_state and aput preserve exact dataclass and Pydantic types upon deserialization."""
    cit = _create_sample_citation("v41690973", "2024-01", "CPI All-items")
    plan = QueryPlan(
        objective="Analyze CPI and BoC rates",
        steps=(
            PlanStep(
                step_id=1,
                description="Fetch CPI",
                assigned_agent="data_fetcher",
                status=StepStatus.COMPLETED,
            ),
        ),
    )
    artifact = SQLArtifact(
        source_series_id="v41690973",
        sql_query="SELECT date, amount FROM cpi_data",
        row_count=1,
        rows=({"date": date(2024, 1, 1), "amount": Decimal("158.30")},),
    )
    hitl = HITLInterrupt(
        interrupt_type=InterruptType.AMBIGUOUS_MEMBER,
        reason="Disambiguate geography",
        suggested_options=("Toronto", "Montreal"),
    )
    trace = TraceContext(traceparent="00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01")
    budget = TokenBudget(max_budget=50000, prompt_tokens_used=120, completion_tokens_used=40)

    initial_state = AgentState(
        session_id="session_fidelity",
        thread_id="thread_fidelity",
        messages=(AgentMessage(role=MessageRole.USER, content="Calculate rate"),),
        plan=plan,
        sql_artifacts=(artifact,),
        citations=(cit,),
        active_interrupt=hitl,
        trace_context=trace,
        token_budget=budget,
        scratchpad={"metric": "CPI"},
    )

    config: RunnableConfig = {"configurable": {"thread_id": "thread_fidelity"}}
    await checkpointer.aput(config, initial_state)

    loaded = await checkpointer.aget_state(config)
    assert loaded is not None

    # 1. Dataclass citation fidelity
    assert len(loaded.citations) == 1
    loaded_cit = loaded.citations[0]
    assert isinstance(loaded_cit, CitationEnvelope)
    assert isinstance(loaded_cit.core, CoreVerificationTuple)
    assert isinstance(loaded_cit.enrichment, MetadataEnrichment)
    assert isinstance(loaded_cit.enrichment.bilingual_title, BilingualTitle)
    assert loaded_cit.core.vector_id == "v41690973"

    # 2. Pydantic models fidelity
    assert isinstance(loaded.plan, QueryPlan)
    assert len(loaded.plan.steps) == 1
    assert isinstance(loaded.plan.steps[0], PlanStep)
    assert loaded.plan.steps[0].status == StepStatus.COMPLETED

    assert isinstance(loaded.active_interrupt, HITLInterrupt)
    assert loaded.active_interrupt.interrupt_type == InterruptType.AMBIGUOUS_MEMBER

    assert isinstance(loaded.trace_context, TraceContext)
    assert loaded.trace_context.traceparent == trace.traceparent

    assert isinstance(loaded.token_budget, TokenBudget)
    assert loaded.token_budget.total_tokens_used == 160

    # 3. Exact Decimal and date fidelity in SQLArtifact.rows
    loaded_row = loaded.sql_artifacts[0].rows[0]
    assert isinstance(loaded_row["amount"], Decimal)
    assert loaded_row["amount"] == Decimal("158.30")
    assert isinstance(loaded_row["date"], date)
    assert not isinstance(loaded_row["date"], datetime)
    assert loaded_row["date"] == date(2024, 1, 1)
