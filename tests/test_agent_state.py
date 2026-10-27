"""Unit and integration test suite for CAN-21 LangGraph AgentState and AsyncSqliteSaver."""

from __future__ import annotations

import tempfile
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
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


def test_token_budget_remaining() -> None:
    """TokenBudget calculates remaining token capacity correctly."""
    budget = TokenBudget(
        max_budget=10000,
        prompt_tokens_used=6000,
        completion_tokens_used=2000,
        total_tokens_used=8000,
    )
    assert budget.remaining_tokens == 2000

    exhausted = TokenBudget(max_budget=1000, total_tokens_used=1200)
    assert exhausted.remaining_tokens == 0


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
# 3. AsyncSqliteSaver Checkpointer Persistence Tests
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
    chk_id = await checkpointer.aput({"configurable": {"thread_id": "thread_alpha"}}, initial_state)
    assert chk_id.startswith("chk_")

    # Recover state
    loaded_state = await checkpointer.aget({"configurable": {"thread_id": "thread_alpha"}})
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
async def test_checkpointer_thread_isolation(checkpointer: AsyncSqliteSaver) -> None:
    """States stored under different threads remain completely isolated."""
    state_a = AgentState(session_id="s1", thread_id="thread_A")
    state_b = AgentState(session_id="s2", thread_id="thread_B")

    await checkpointer.aput({"configurable": {"thread_id": "thread_A"}}, state_a)
    await checkpointer.aput({"configurable": {"thread_id": "thread_B"}}, state_b)

    rec_a = await checkpointer.aget({"configurable": {"thread_id": "thread_A"}})
    rec_b = await checkpointer.aget({"configurable": {"thread_id": "thread_B"}})

    assert rec_a is not None and rec_a.thread_id == "thread_A"
    assert rec_b is not None and rec_b.thread_id == "thread_B"


# ==============================================================================
# 4. Time-Travel History & Rollback Tests (arollback_to)
# ==============================================================================


@pytest.mark.asyncio
async def test_time_travel_rollback_and_forking(checkpointer: AsyncSqliteSaver) -> None:
    """AsyncSqliteSaver supports time-travel rewind within the same thread and forking."""
    # Step 1: User asks question
    m1 = AgentMessage(role=MessageRole.USER, content="Query BoC policy rate")
    s1 = AgentState(session_id="th1", thread_id="th1", messages=(m1,))
    chk1 = await checkpointer.aput(
        {"configurable": {"thread_id": "th1", "checkpoint_id": "chk_step_1"}}, s1
    )

    # Step 2: Supervisor generates plan
    plan = QueryPlan(objective="Fetch BoC policy rate")
    s2 = s1.model_copy(update={"plan": plan})
    chk2 = await checkpointer.aput(
        {"configurable": {"thread_id": "th1", "checkpoint_id": "chk_step_2"}}, s2
    )

    # Step 3: Bad step or hallucinated action
    bad_msg = AgentMessage(role=MessageRole.ASSISTANT, content="Hallucinated answer")
    s3 = s2.model_copy(update={"messages": (*s2.messages, bad_msg)})
    await checkpointer.aput(
        {"configurable": {"thread_id": "th1", "checkpoint_id": "chk_step_3"}}, s3
    )

    # Verify latest is step 3
    latest = await checkpointer.aget({"configurable": {"thread_id": "th1"}})
    assert latest is not None and len(latest.messages) == 2

    # Time-travel rewind to step 1 (before plan and bad action)
    rewound = await checkpointer.arollback_to(thread_id="th1", target_checkpoint_id=chk1)
    assert len(rewound.messages) == 1
    assert rewound.plan is None

    # Conversation forking into a new branch thread
    forked = await checkpointer.arollback_to(
        thread_id="th1",
        target_checkpoint_id=chk2,
        new_thread_id="th1_fork_alt_path",
    )
    assert forked.thread_id == "th1_fork_alt_path"
    assert forked.plan is not None
    assert len(forked.messages) == 1

    # Verify forked thread is independently fetchable
    forked_rec = await checkpointer.aget({"configurable": {"thread_id": "th1_fork_alt_path"}})
    assert forked_rec is not None
    assert forked_rec.thread_id == "th1_fork_alt_path"


@pytest.mark.asyncio
async def test_time_travel_keyerror_on_unknown_checkpoint(
    checkpointer: AsyncSqliteSaver,
) -> None:
    """arollback_to raises KeyError if target checkpoint does not exist."""
    with pytest.raises(KeyError, match="Checkpoint 'chk_unknown' not found"):
        await checkpointer.arollback_to(
            thread_id="th_nonexistent", target_checkpoint_id="chk_unknown"
        )
