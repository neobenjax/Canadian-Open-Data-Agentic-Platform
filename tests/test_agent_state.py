"""Unit and integration test suite for CAN-21 LangGraph AgentState and AsyncSqliteSaver."""

from __future__ import annotations

import tempfile
from collections.abc import AsyncGenerator
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest
import pytest_asyncio
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from candata_agent.checkpoint import AsyncSqliteSaver
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
    add_messages,
    merge_citations,
)
from candata_mcp.citation import (
    BilingualTitle,
    CitationEnvelope,
    CoreVerificationTuple,
    MetadataEnrichment,
)


@pytest.fixture
def sample_citation() -> CitationEnvelope:
    return CitationEnvelope(
        publisher="Statistics Canada",
        core=CoreVerificationTuple(
            table_id="18-10-0004-01",
            vector_id="v41690973",
            reference_period="2024-01",
        ),
        enrichment=MetadataEnrichment(
            coordinate="2.1",
            release_or_revision_date="2024-02-15T08:30",
            bilingual_title=BilingualTitle(
                en="Consumer Price Index",
                fr="Indice des prix à la consommation",
            ),
            canonical_url="https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810000401",
        ),
    )


@pytest_asyncio.fixture
async def checkpointer() -> AsyncGenerator[AsyncSqliteSaver, None]:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_checkpoints.db"
        saver = AsyncSqliteSaver(db_path)
        async with saver:
            yield saver


# ==============================================================================
# 1. AgentState & Models Validation Tests
# ==============================================================================


def test_agent_state_defaults() -> None:
    """AgentState initializes with canonical defaults and strict immutability."""
    state = AgentState(session_id="sess_123", thread_id="th_456")

    assert state.schema_version == 1
    assert state.session_id == "sess_123"
    assert state.thread_id == "th_456"
    assert state.run_id.startswith("run_")
    assert state.messages == ()
    assert state.plan is None
    assert state.sql_artifacts == ()
    assert state.citations == ()
    assert state.active_interrupt is None
    assert state.scratchpad == {}
    assert state.token_budget.remaining_tokens == 128000


def test_agent_state_frozen_immutability() -> None:
    """AgentState fields cannot be mutated in place."""
    state = AgentState(session_id="sess_1", thread_id="th_1")
    with pytest.raises(ValidationError):
        # pyright: ignore[reportAttributeAccessIssue]
        state.session_id = "sess_2"  # type: ignore[misc]


def test_token_budget_remaining_and_sync() -> None:
    """TokenBudget calculates remaining token capacity and validates totals."""
    budget = TokenBudget(
        max_budget=10000,
        prompt_tokens_used=6000,
        completion_tokens_used=2000,
        total_tokens_used=8000,
    )
    assert budget.remaining_tokens == 2000

    auto_computed = TokenBudget(prompt_tokens_used=1500, completion_tokens_used=500)
    assert auto_computed.total_tokens_used == 2000

    exhausted = TokenBudget(max_budget=1000, total_tokens_used=1200)
    assert exhausted.remaining_tokens == 0


def test_agent_message_creation_and_immutability() -> None:
    """AgentMessage generates unique IDs and enforces role validation."""
    msg = AgentMessage(role=MessageRole.ASSISTANT, content="Test response")
    assert msg.id.startswith("msg_")
    assert msg.role == MessageRole.ASSISTANT
    assert msg.content == "Test response"


def test_query_plan_and_step_lifecycle() -> None:
    """QueryPlan tracks step progress deterministically."""
    s1 = PlanStep(
        step_id=1,
        description="Fetch BoC series",
        assigned_agent="analyst",
        status=StepStatus.IN_PROGRESS,
    )
    plan = QueryPlan(objective="Analyze policy rates", steps=(s1,), active_step_id=1)
    assert plan.plan_id.startswith("plan_")
    assert len(plan.steps) == 1
    assert plan.steps[0].status == StepStatus.IN_PROGRESS
    assert not plan.completed


def test_sql_artifact_provenance() -> None:
    """SQLArtifact captures query provenance and row data."""
    art = SQLArtifact(
        source_series_id="v41690973",
        sql_query="SELECT date, value FROM data WHERE date >= '2024-01'",
        row_count=2,
        rows=({"date": "2024-01", "value": 158.3}, {"date": "2024-02", "value": 158.8}),
    )
    assert art.artifact_id.startswith("sql_")
    assert art.row_count == 2
    assert len(art.rows) == 2


# ==============================================================================
# 2. Channel Reducers Tests (add_messages, merge_citations)
# ==============================================================================


def test_add_messages_reducer() -> None:
    """add_messages appends new messages and updates existing ones by message ID."""
    m1 = AgentMessage(id="msg_1", role=MessageRole.USER, content="Hello")
    m2 = AgentMessage(id="msg_2", role=MessageRole.ASSISTANT, content="Hi there")

    # Initial append
    s1 = add_messages((), (m1, m2))
    assert len(s1) == 2
    assert s1[0].content == "Hello"
    assert s1[1].content == "Hi there"

    # In-place update for m2, plus append m3
    m2_updated = AgentMessage(id="msg_2", role=MessageRole.ASSISTANT, content="Updated greeting")
    m3 = AgentMessage(id="msg_3", role=MessageRole.USER, content="How are you?")

    s2 = add_messages(s1, (m2_updated, m3))
    assert len(s2) == 3
    assert s2[0].content == "Hello"
    assert s2[1].content == "Updated greeting"
    assert s2[2].content == "How are you?"


def test_merge_citations_reducer(sample_citation: CitationEnvelope) -> None:
    """merge_citations deduplicates by (table_id, vector_id, reference_period)."""
    cit1 = sample_citation
    cit2 = CitationEnvelope(
        publisher="Statistics Canada",
        core=CoreVerificationTuple(
            table_id="18-10-0004-01",
            vector_id="v41690973",
            reference_period="2024-02",  # Different period
        ),
        enrichment=MetadataEnrichment(
            coordinate="2.1",
            release_or_revision_date="2024-03-15T08:30",
            bilingual_title=BilingualTitle(en="Consumer Price Index", fr=None),
            canonical_url="https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810000401",
        ),
    )

    merged = merge_citations((cit1,), cit2)
    assert len(merged) == 2

    # Provide duplicate of cit1 with updated metadata
    cit1_revision = CitationEnvelope(
        publisher="Statistics Canada",
        core=CoreVerificationTuple(
            table_id="18-10-0004-01",
            vector_id="v41690973",
            reference_period="2024-01",  # Same tuple as cit1
        ),
        enrichment=MetadataEnrichment(
            coordinate="2.1",
            release_or_revision_date="2024-02-20T08:30",  # Revised
            bilingual_title=BilingualTitle(en="Consumer Price Index (Revised)", fr=None),
            canonical_url="https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810000401",
        ),
    )

    merged_updated = merge_citations(merged, cit1_revision)
    assert len(merged_updated) == 2
    # Verify cit1 was replaced with cit1_revision
    revised = [c for c in merged_updated if c.core.reference_period == "2024-01"][0]
    assert revised.enrichment.bilingual_title.en == "Consumer Price Index (Revised)"


# ==============================================================================
# 3. LangGraph 0.2+ StateGraph Compatibility & Channel Reducer Detection
# ==============================================================================


def test_langgraph_stategraph_compilation_and_channel_reducers(
    checkpointer: AsyncSqliteSaver,
) -> None:
    """StateGraph(AgentState) compiles with AsyncSqliteSaver and registers aggregate reducers."""
    builder = StateGraph(AgentState)
    builder.add_node("dummy", lambda s: {})
    builder.add_edge(START, "dummy")
    builder.add_edge("dummy", END)

    # Must cleanly compile accepting BaseCheckpointSaver instance
    graph = builder.compile(checkpointer=checkpointer)
    assert graph is not None

    # Channels must register as BinaryOperatorAggregate due to Annotated[..., reducer]
    assert type(builder.channels["messages"]).__name__ == "BinaryOperatorAggregate"
    assert type(builder.channels["citations"]).__name__ == "BinaryOperatorAggregate"


# ==============================================================================
# 4. AsyncSqliteSaver Checkpointer Persistence & Type Fidelity Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_checkpointer_persistence_roundtrip(
    checkpointer: AsyncSqliteSaver, sample_citation: CitationEnvelope
) -> None:
    """AsyncSqliteSaver stores and recovers complete AgentState with all complex structures."""
    msg = AgentMessage(role=MessageRole.USER, content="Analyze CPI inflation")
    step = PlanStep(
        step_id=1,
        description="Query StatCan CPI vector",
        assigned_agent="data_analyst",
        status=StepStatus.COMPLETED,
    )
    plan = QueryPlan(objective="Analyze inflation", steps=(step,), completed=True)
    artifact = SQLArtifact(
        source_series_id="v41690973",
        sql_query="SELECT date, value FROM statcan WHERE date >= '2024-01'",
        row_count=12,
        rows=({"date": "2024-01", "value": 158.3},),
    )
    interrupt = HITLInterrupt(
        interrupt_type=InterruptType.AMBIGUOUS_MEMBER,
        reason="Multiple geography matches found",
        suggested_options=("Toronto (CMA)", "Toronto (Municipality)"),
    )

    initial_state = AgentState(
        session_id="session_test",
        thread_id="thread_alpha",
        messages=(msg,),
        plan=plan,
        sql_artifacts=(artifact,),
        citations=(sample_citation,),
        active_interrupt=interrupt,
        trace_context=TraceContext(
            traceparent="00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
        ),
        token_budget=TokenBudget(max_budget=100000, total_tokens_used=2450),
        scratchpad={"flag": "ready"},
    )

    # Save state
    res = await checkpointer.aput(
        cast(RunnableConfig, {"configurable": {"thread_id": "thread_alpha"}}), initial_state
    )
    chk_id = res["configurable"]["checkpoint_id"] if isinstance(res, dict) else res
    assert str(chk_id).startswith("chk_")

    # Recover state
    loaded_state = await checkpointer.aget_state({"configurable": {"thread_id": "thread_alpha"}})
    assert loaded_state is not None
    assert loaded_state.session_id == "session_test"
    assert loaded_state.thread_id == "thread_alpha"
    assert len(loaded_state.messages) == 1
    assert loaded_state.messages[0].content == "Analyze CPI inflation"
    assert loaded_state.plan is not None
    assert loaded_state.plan.objective == "Analyze inflation"
    assert len(loaded_state.sql_artifacts) == 1
    assert loaded_state.sql_artifacts[0].sql_query == artifact.sql_query
    assert len(loaded_state.citations) == 1
    assert loaded_state.citations[0].core.vector_id == "v41690973"
    assert loaded_state.active_interrupt is not None
    assert loaded_state.active_interrupt.interrupt_type == InterruptType.AMBIGUOUS_MEMBER
    assert loaded_state.token_budget.total_tokens_used == 2450
    assert loaded_state.scratchpad == {"flag": "ready"}


@pytest.mark.asyncio
async def test_exact_decimal_and_date_serialization_fidelity(
    checkpointer: AsyncSqliteSaver,
) -> None:
    """Decimal values and datetime.date instances in SQLArtifact.rows retain exact types."""
    artifact = SQLArtifact(
        source_series_id="v41690973",
        sql_query="SELECT date, amount FROM cpi_table",
        row_count=1,
        rows=({"date": date(2025, 1, 1), "amount": Decimal("2045.50")},),
    )
    state = AgentState(
        session_id="sess_math",
        thread_id="th_math",
        sql_artifacts=(artifact,),
    )
    await checkpointer.aput(cast(RunnableConfig, {"configurable": {"thread_id": "th_math"}}), state)
    loaded = await checkpointer.aget_state({"configurable": {"thread_id": "th_math"}})
    assert loaded is not None
    row = loaded.sql_artifacts[0].rows[0]

    # Assert exact Decimal fidelity
    assert isinstance(row["amount"], Decimal)
    assert row["amount"] == Decimal("2045.50")

    # Assert exact datetime.date fidelity (not string, not datetime)
    assert isinstance(row["date"], date)
    assert not isinstance(row["date"], datetime)
    assert row["date"] == date(2025, 1, 1)


@pytest.mark.asyncio
async def test_checkpointer_thread_isolation(checkpointer: AsyncSqliteSaver) -> None:
    """States stored under different threads remain completely isolated."""
    state_a = AgentState(session_id="s1", thread_id="thread_A")
    state_b = AgentState(session_id="s2", thread_id="thread_B")

    await checkpointer.aput(
        cast(RunnableConfig, {"configurable": {"thread_id": "thread_A"}}), state_a
    )
    await checkpointer.aput(
        cast(RunnableConfig, {"configurable": {"thread_id": "thread_B"}}), state_b
    )

    rec_a = await checkpointer.aget_state({"configurable": {"thread_id": "thread_A"}})
    rec_b = await checkpointer.aget_state({"configurable": {"thread_id": "thread_B"}})

    assert rec_a is not None and rec_a.thread_id == "thread_A"
    assert rec_b is not None and rec_b.thread_id == "thread_B"


# ==============================================================================
# 5. Time-Travel History & Rollback Tests (arollback_to)
# ==============================================================================


@pytest.mark.asyncio
async def test_time_travel_rollback_preserves_session_id(checkpointer: AsyncSqliteSaver) -> None:
    """arollback_to supports time-travel rewind while strictly preserving original session_id."""
    # Step 1: User asks question in session 'user_session_99'
    m1 = AgentMessage(role=MessageRole.USER, content="Query BoC policy rate")
    s1 = AgentState(session_id="user_session_99", thread_id="th1", messages=(m1,))
    res1 = await checkpointer.aput(
        cast(RunnableConfig, {"configurable": {"thread_id": "th1", "checkpoint_id": "chk_step_1"}}),
        s1,
    )
    chk1 = res1["configurable"]["checkpoint_id"] if isinstance(res1, dict) else res1

    # Step 2: Supervisor generates plan
    plan = QueryPlan(objective="Fetch BoC policy rate")
    s2 = s1.model_copy(update={"plan": plan})
    res2 = await checkpointer.aput(
        cast(RunnableConfig, {"configurable": {"thread_id": "th1", "checkpoint_id": "chk_step_2"}}),
        s2,
    )
    chk2 = res2["configurable"]["checkpoint_id"] if isinstance(res2, dict) else res2

    # Step 3: Bad step or hallucinated action
    bad_msg = AgentMessage(role=MessageRole.ASSISTANT, content="Hallucinated answer")
    s3 = s2.model_copy(update={"messages": (*s2.messages, bad_msg)})
    await checkpointer.aput(
        cast(RunnableConfig, {"configurable": {"thread_id": "th1", "checkpoint_id": "chk_step_3"}}),
        s3,
    )

    # Verify latest is step 3
    latest = await checkpointer.aget_state({"configurable": {"thread_id": "th1"}})
    assert latest is not None and len(latest.messages) == 2

    # Time-travel rewind to step 1 (before plan and bad action)
    rewound = await checkpointer.arollback_to(thread_id="th1", target_checkpoint_id=chk1)
    assert len(rewound.messages) == 1
    assert rewound.plan is None
    # CRITICAL: Assert session_id was preserved!
    assert rewound.session_id == "user_session_99"

    # Conversation forking into a new branch thread
    forked = await checkpointer.arollback_to(
        thread_id="th1",
        target_checkpoint_id=chk2,
        new_thread_id="th1_fork_alt_path",
    )
    assert forked.thread_id == "th1_fork_alt_path"
    assert forked.plan is not None
    assert len(forked.messages) == 1
    # CRITICAL: Assert session_id was preserved across fork!
    assert forked.session_id == "user_session_99"

    # Verify forked thread is independently fetchable
    forked_rec = await checkpointer.aget_state({"configurable": {"thread_id": "th1_fork_alt_path"}})
    assert forked_rec is not None
    assert forked_rec.thread_id == "th1_fork_alt_path"
    assert forked_rec.session_id == "user_session_99"


@pytest.mark.asyncio
async def test_time_travel_keyerror_on_unknown_checkpoint(
    checkpointer: AsyncSqliteSaver,
) -> None:
    """arollback_to raises KeyError if target checkpoint does not exist."""
    with pytest.raises(KeyError, match="Checkpoint 'chk_unknown' not found"):
        await checkpointer.arollback_to(
            thread_id="th_nonexistent", target_checkpoint_id="chk_unknown"
        )


@pytest.mark.asyncio
async def test_checkpoint_scratchpad_deepcopy_immutability(
    checkpointer: AsyncSqliteSaver,
) -> None:
    """Activity 21.2: Mutating mutable scratchpad after aput must not corrupt saved checkpoint."""
    initial_scratch = {"series_data": [1, 2, 3], "meta": {"owner": "benjamin"}}
    s = AgentState(
        session_id="sess_immutable",
        thread_id="th_immutable",
        messages=[],
        scratchpad=initial_scratch,
    )
    cfg = cast(
        RunnableConfig,
        {"configurable": {"thread_id": "th_immutable", "checkpoint_id": "chk_imm_1"}},
    )
    await checkpointer.aput(cfg, s)

    # Mutate the in-memory scratchpad dictionary in place
    initial_scratch["series_data"].append(999)
    initial_scratch["meta"]["owner"] = "corrupted"

    # Fetch stored state from checkpointer
    restored = await checkpointer.aget_state(cfg)
    assert restored is not None
    assert restored.scratchpad["series_data"] == [1, 2, 3]
    assert restored.scratchpad["meta"]["owner"] == "benjamin"


@pytest.mark.asyncio
async def test_checkpoint_strict_citation_typeadapter(
    checkpointer: AsyncSqliteSaver,
) -> None:
    """Activity 21.1: CitationEnvelope must roundtrip via TypeAdapter without defaults."""
    envelope = CitationEnvelope(
        publisher="Statistics Canada",
        core=CoreVerificationTuple(
            table_id="18-10-0004-01",
            vector_id="v41690973",
            reference_period="2024-01/2024-12",
        ),
        enrichment=MetadataEnrichment(
            coordinate="2.1",
            release_or_revision_date="2024-12-15T08:30",
            bilingual_title=BilingualTitle(en="Consumer Price Index", fr="IPC"),
            canonical_url="https://statcan.gc.ca",
        ),
    )
    s = AgentState(
        session_id="sess_cit",
        thread_id="th_cit",
        messages=[],
        citations=(envelope,),
        scratchpad={"target_val": Decimal("105.75"), "as_of": date(2024, 6, 1)},
    )
    cfg = cast(
        RunnableConfig, {"configurable": {"thread_id": "th_cit", "checkpoint_id": "chk_cit_1"}}
    )
    await checkpointer.aput(cfg, s)

    restored = await checkpointer.aget_state(cfg)
    assert restored is not None
    assert len(restored.citations) == 1
    assert restored.citations[0] == envelope
    assert restored.scratchpad["target_val"] == Decimal("105.75")
    assert restored.scratchpad["as_of"] == date(2024, 6, 1)


def test_token_budget_non_negative_and_derived_total() -> None:
    """Activity 21.4: TokenBudget must enforce non-negative values and synchronized total."""
    tb = TokenBudget(prompt_tokens_used=150, completion_tokens_used=50)
    assert tb.total_tokens_used == 200

    with pytest.raises(ValidationError):
        TokenBudget(prompt_tokens_used=-10)

    with pytest.raises(ValidationError):
        TokenBudget(completion_tokens_used=-5)


# ==============================================================================
# 6. Full-Lifecycle Graph Execution & Dynamic Verification (Guardrail 26)
# ==============================================================================


@pytest.mark.asyncio
async def test_langgraph_full_lifecycle_ainvoke_multi_turn_and_history_replay(
    checkpointer: AsyncSqliteSaver,
    sample_citation: CitationEnvelope,
) -> None:
    """Guardrail 26: Full graph lifecycle via ainvoke with parallel nodes, history, and replay."""
    builder = StateGraph(AgentState)

    # 1. Parallel node A: adds user message and citation
    def node_a(state: AgentState) -> dict[str, Any]:
        return {
            "messages": [AgentMessage(role=MessageRole.ASSISTANT, content="from a")],
            "citations": [sample_citation],
        }

    # 2. Parallel node B: adds assistant message and SQLArtifact with exact Decimal and date
    def node_b(state: AgentState) -> dict[str, Any]:
        artifact = SQLArtifact(
            source_series_id="v41690973",
            sql_query="SELECT date, amount FROM cpi_table",
            row_count=1,
            rows=({"date": date(2025, 1, 1), "amount": Decimal("2045.50")},),
        )
        return {
            "messages": [AgentMessage(role=MessageRole.ASSISTANT, content="from b")],
            "sql_artifacts": [artifact],
        }

    # 3. Downstream Analyst node: joins both parallel branches
    def node_analyst(state: AgentState) -> dict[str, Any]:
        return {
            "messages": [AgentMessage(role=MessageRole.ASSISTANT, content="analyst")],
        }

    builder.add_node("node_a", node_a)
    builder.add_node("node_b", node_b)
    builder.add_node("node_analyst", node_analyst)

    builder.add_edge(START, "node_a")
    builder.add_edge(START, "node_b")
    builder.add_edge("node_a", "node_analyst")
    builder.add_edge("node_b", "node_analyst")
    builder.add_edge("node_analyst", END)

    app = builder.compile(checkpointer=checkpointer)

    thread_cfg = cast(RunnableConfig, {"configurable": {"thread_id": "thread_lifecycle_test"}})

    # Check 1: ainvoke, two parallel nodes then one -> NO Foreign Key crash, reducers merge
    input_state: dict[str, Any] = {
        "session_id": "sess_lifecycle",
        "thread_id": "thread_lifecycle_test",
        "messages": [AgentMessage(role=MessageRole.USER, content="user q1")],
    }
    res1 = await app.ainvoke(input_state, config=thread_cfg)

    # Messages merged in order: user q1, from a, from b, analyst (4 messages)
    assert len(res1["messages"]) == 4
    contents = [m.content for m in res1["messages"]]
    assert contents[0] == "user q1"
    assert "from a" in contents
    assert "from b" in contents
    assert contents[-1] == "analyst"

    # Citation reducer merged citation from node_a
    assert len(res1["citations"]) == 1
    assert res1["citations"][0].core.vector_id == "v41690973"

    # Check 2: Decimal and date preserved in SQLArtifact.rows after graph run
    assert len(res1["sql_artifacts"]) == 1
    row = res1["sql_artifacts"][0].rows[0]
    assert isinstance(row["amount"], Decimal)
    assert row["amount"] == Decimal("2045.50")
    assert isinstance(row["date"], date)
    assert not isinstance(row["date"], datetime)
    assert row["date"] == date(2025, 1, 1)

    # Check 3: Second question on the same thread -> appends to thread
    res2 = await app.ainvoke(
        {"messages": [AgentMessage(role=MessageRole.USER, content="user q2")]},
        config=thread_cfg,
    )
    # Total messages now: 4 previous + 1 user q2 + 3 from nodes = 8 messages
    assert len(res2["messages"]) == 8
    assert res2["messages"][4].content == "user q2"

    # Check 4: aget_state_history -> retrieves chronological checkpoints
    history = [s async for s in app.aget_state_history(thread_cfg)]
    assert len(history) >= 4

    # Check 5: Replay from a historical checkpoint_id
    historical_chk = history[-2]  # Earlier checkpoint from the first invocation
    replay_cfg = cast(
        RunnableConfig,
        {
            "configurable": {
                "thread_id": "thread_lifecycle_test",
                "checkpoint_id": historical_chk.config["configurable"]["checkpoint_id"],
            }
        },
    )
    historical_state = await app.aget_state(replay_cfg)
    assert historical_state is not None
    assert len(historical_state.values["messages"]) < 8
    assert historical_state.values["session_id"] == "sess_lifecycle"
