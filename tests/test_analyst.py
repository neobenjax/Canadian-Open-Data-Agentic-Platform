"""Tests for Issue #50: Data Analyst Node SQL timeout and dual citation retention."""

from __future__ import annotations

import asyncio
import time

import pyarrow as pa
import pytest

from candata_agent.analyst import (
    affordability_burden_ratio,
    data_analyst_node,
    percentage_point_spread,
)
from candata_agent.state import (
    AgentState,
    PlanStep,
    QueryPlan,
    SQLArtifact,
    StepStatus,
)
from candata_mcp.citation import (
    BilingualTitle,
    CitationEnvelope,
    CoreVerificationTuple,
    MetadataEnrichment,
)


def _make_citation(table_id: str, vector_id: str, title: str) -> CitationEnvelope:
    """Helper to build a Two-Tier Citation Envelope."""
    clean_pid = table_id.replace("-", "")
    return CitationEnvelope(
        publisher="StatCan",
        core=CoreVerificationTuple(
            table_id=table_id,
            vector_id=vector_id,
            reference_period="2024",
        ),
        enrichment=MetadataEnrichment(
            coordinate="1.1.0.0.0.0.0.0.0.0",
            release_or_revision_date="2024-10-15",
            bilingual_title=BilingualTitle(en=title, fr=None),
            canonical_url=f"https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid={clean_pid}",
        ),
    )


@pytest.mark.asyncio
async def test_data_analyst_node_timeout_marks_step_failed_without_blocking() -> None:
    """Slow query with 0.5s timeout marks step FAILED in <1s without freezing event loop."""
    heartbeat_ticks = 0
    stop_heartbeat = asyncio.Event()

    async def heartbeat() -> None:
        nonlocal heartbeat_ticks
        while not stop_heartbeat.is_set():
            await asyncio.sleep(0.05)
            heartbeat_ticks += 1

    heartbeat_task = asyncio.create_task(heartbeat())

    # Generate 100M rows with recursive CTE to simulate a slow execution
    slow_query = (
        "WITH recursive gen(x) AS ("
        "SELECT 1 UNION ALL SELECT x+1 FROM gen WHERE x < 100000000"
        ") SELECT count(*) FROM gen"
    )

    step = PlanStep(
        step_id=1,
        description="Execute slow analytical query with strict timeout",
        assigned_agent="data_analyst",
        tool_name="custom_sql",
        tool_args={
            "series_id": "v123456",
            "query": slow_query,
            "timeout": 0.5,
        },
    )
    plan = QueryPlan(objective="Verify async timeout", steps=(step,), active_step_id=1)
    state = AgentState(session_id="s_test", thread_id="t_test", plan=plan)

    start_time = time.monotonic()
    try:
        delta = await data_analyst_node(state)
    finally:
        stop_heartbeat.set()
        await heartbeat_task

    duration = time.monotonic() - start_time

    # 1. Verification of duration: timed out around ~0.5s and finished well under 1.5s
    assert duration < 1.5, f"Expected timeout under 1.5s, took {duration:.3f}s"

    # 2. Verification of non-blocking event loop: concurrent heartbeat continued ticking
    assert heartbeat_ticks > 0, "Concurrent heartbeat coroutine was frozen by DuckDB execution!"

    # 3. Verification of plan and step failure status
    assert delta["plan"] is not None
    failed_step = delta["plan"].steps[0]
    assert failed_step.status == StepStatus.FAILED
    assert failed_step.error is not None
    assert "timed out" in failed_step.error.lower()
    assert "0.5s" in failed_step.error

    # 4. Warnings and scratchpad error tracking
    assert any("timed out" in w.lower() for w in delta.get("warnings", ()))
    assert "last_analyst_error" in delta.get("scratchpad", {})
    assert "timed out" in delta["scratchpad"]["last_analyst_error"].lower()


def test_affordability_burden_ratio_returns_sql_artifact_with_dual_citations() -> None:
    """affordability_burden_ratio recipe produces SQLArtifact containing dual citations."""
    rent_tbl = pa.Table.from_pydict({"date": ["2024"], "value": [2000.0]})  # $2k/mo = $24k/yr
    inc_tbl = pa.Table.from_pydict({"date": ["2024"], "value": [60000.0]})  # $60k/yr

    rent_cit = _make_citation("34-10-0143-01", "v3823103", "Average Monthly Rent")
    income_cit = _make_citation("11-10-0239-01", "v11223344", "Median After-Tax Income")

    # Call recipe directly with dual citations
    artifact = affordability_burden_ratio(
        rent_tbl,
        inc_tbl,
        rent_citation=rent_cit,
        income_citation=income_cit,
    )

    # 1. Assert return type is SQLArtifact
    assert isinstance(artifact, SQLArtifact)

    # 2. Assert multi-series citations lineage is preserved
    assert len(artifact.citations) == 2
    assert artifact.citations[0] == rent_cit
    assert artifact.citations[1] == income_cit

    # 3. Assert backwards compatibility: primary citation defaults to citations[0]
    assert artifact.citation == rent_cit

    # 4. Assert mathematical accuracy
    assert artifact.row_count == 1
    assert artifact.rows[0]["monthly_rent"] == 2000.0
    assert artifact.rows[0]["annual_rent"] == 24000.0
    assert artifact.rows[0]["annual_income"] == 60000.0
    assert artifact.rows[0]["rent_to_income_pct"] == 40.0

    # 5. Assert 2-tuple unpacking backwards compatibility: (rows, sql_query)
    rows, sql = artifact
    assert len(rows) == 1
    assert rows[0]["rent_to_income_pct"] == 40.0
    assert "rent_to_income_pct" in sql


@pytest.mark.asyncio
async def test_data_analyst_node_affordability_burden_ratio_dual_citations() -> None:
    """data_analyst_node preserves both series citations on the emitted SQLArtifact."""
    rent_cit = _make_citation("34-10-0143-01", "v3823103", "Average Monthly Rent")
    income_cit = _make_citation("11-10-0239-01", "v11223344", "Median After-Tax Income")

    step = PlanStep(
        step_id=1,
        description="Calculate GT-07 affordability burden ratio",
        assigned_agent="data_analyst",
        tool_name="affordability_burden_ratio",
        tool_args={
            "rent_table": [{"date": "2024", "value": 2000.0}],
            "income_table": [{"date": "2024", "value": 60000.0}],
            "rent_citation": rent_cit,
            "income_citation": income_cit,
            "series_id": "v3823103",
        },
    )
    plan = QueryPlan(objective="GT-07", steps=(step,), active_step_id=1)
    state = AgentState(
        session_id="s1",
        thread_id="t1",
        plan=plan,
        citations=(rent_cit, income_cit),
    )

    delta = await data_analyst_node(state)

    assert "sql_artifacts" in delta
    assert len(delta["sql_artifacts"]) == 1
    artifact = delta["sql_artifacts"][0]

    assert isinstance(artifact, SQLArtifact)
    assert len(artifact.citations) == 2
    assert artifact.citations[0] == rent_cit
    assert artifact.citations[1] == income_cit
    assert artifact.citation == rent_cit


def test_percentage_point_spread_dual_citations() -> None:
    """percentage_point_spread recipe produces SQLArtifact with citations for both series."""
    table_a = pa.Table.from_pydict({"date": ["2025"], "value": [3.0]})
    table_b = pa.Table.from_pydict({"date": ["2025"], "value": [1.4]})

    cit_a = _make_citation("10-10-0122-01", "v11111", "Series A")
    cit_b = _make_citation("10-10-0122-01", "v22222", "Series B")

    artifact = percentage_point_spread(
        table_a,
        table_b,
        citation_a=cit_a,
        citation_b=cit_b,
    )

    assert isinstance(artifact, SQLArtifact)
    assert len(artifact.citations) == 2
    assert artifact.citations[0] == cit_a
    assert artifact.citations[1] == cit_b
    assert artifact.citation == cit_a
    assert artifact.rows[0]["spread_pp"] == 1.6


def test_sql_artifact_sync_and_data_alias() -> None:
    """SQLArtifact correctly synchronizes citations, citation, and data property."""
    cit = _make_citation("11-10-0239-01", "v9999", "Test Series")

    # 1. Instantiating with citations tuple defaults citation to citations[0]
    art1 = SQLArtifact(
        source_series_id="v9999",
        sql_query="SELECT 1",
        row_count=1,
        citations=(cit,),
        data=[{"val": 42}],
    )
    assert art1.citation == cit
    assert art1.citations == (cit,)
    assert art1.data == [{"val": 42}]
    assert art1.rows == ({"val": 42},)

    # 2. Instantiating with citation defaults citations to (citation,)
    art2 = SQLArtifact(
        source_series_id="v9999",
        sql_query="SELECT 1",
        row_count=1,
        citation=cit,
    )
    assert art2.citations == (cit,)
    assert art2.citation == cit


@pytest.mark.asyncio
async def test_dual_citations_never_fill_unmatched_inputs_by_position() -> None:
    """Unmatched series IDs must never fall back to positional citations in state."""
    cpi_cit = _make_citation("18-10-0004-01", "v41690973", "CPI")
    rent_cit = _make_citation("34-10-0143-01", "v3823103", "Average Monthly Rent")
    income_cit = _make_citation("11-10-0239-01", "v11223344", "Median After-Tax Income")

    # Case 1: state has (CPI, rent, income); only rent series_id is provided -> only rent cited
    step1 = PlanStep(
        step_id=1,
        description="GT-07 without income_series_id",
        assigned_agent="data_analyst",
        tool_name="affordability_burden_ratio",
        tool_args={
            "rent_table": [{"date": "2024", "value": 2000.0}],
            "income_table": [{"date": "2024", "value": 60000.0}],
            "series_id": "v3823103",
        },
    )
    state1 = AgentState(
        session_id="s1",
        thread_id="t1",
        plan=QueryPlan(objective="GT-07", steps=(step1,), active_step_id=1),
        citations=(cpi_cit, rent_cit, income_cit),
    )
    delta1 = await data_analyst_node(state1)
    art1 = delta1["sql_artifacts"][0]
    assert art1.citations == (rent_cit,)
    assert art1.citation == rent_cit

    # Case 2: state has (CPI, income); series_id="v3823103" is missing -> no CPI positional match
    state2 = AgentState(
        session_id="s2",
        thread_id="t2",
        plan=QueryPlan(objective="GT-07", steps=(step1,), active_step_id=1),
        citations=(cpi_cit, income_cit),
    )
    delta2 = await data_analyst_node(state2)
    art2 = delta2["sql_artifacts"][0]
    assert art2.citations == ()
    assert art2.citation is None


@pytest.mark.asyncio
async def test_data_analyst_node_invalid_timeout_marks_step_failed() -> None:
    """Non-numeric or non-positive timeout_seconds marks step FAILED cleanly."""
    for bad_timeout in ("abc", -1.0, 0.0, float("nan"), float("inf")):
        step = PlanStep(
            step_id=1,
            description="Run SQL with bad timeout",
            assigned_agent="data_analyst",
            tool_name="custom_sql",
            tool_args={
                "series_id": "v123456",
                "query": "SELECT 1 AS val",
                "timeout_seconds": bad_timeout,
            },
        )
        state = AgentState(
            session_id="s_bad",
            thread_id="t_bad",
            plan=QueryPlan(objective="Bad timeout", steps=(step,), active_step_id=1),
        )
        delta = await data_analyst_node(state)
        assert delta["plan"] is not None
        failed_step = delta["plan"].steps[0]
        assert failed_step.status == StepStatus.FAILED
        assert failed_step.error is not None
        assert "timeout_seconds" in failed_step.error or "float" in failed_step.error


@pytest.mark.asyncio
async def test_data_analyst_node_clamps_excessive_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Excessive timeout_seconds from planner args is clamped to MAX_ANALYST_TIMEOUT_SECONDS."""
    from candata_agent.analyst import MAX_ANALYST_TIMEOUT_SECONDS, SandboxedDuckDB

    observed_timeouts: list[float] = []

    async def fake_execute_async(
        self: SandboxedDuckDB,
        query: str,
        params: object = None,
        *,
        max_rows: int = 1000,
        timeout_seconds: float = 2.0,
    ) -> list[dict[str, object]]:
        observed_timeouts.append(timeout_seconds)
        return [{"val": 1}]

    monkeypatch.setattr(SandboxedDuckDB, "execute_async", fake_execute_async)

    step = PlanStep(
        step_id=1,
        description="Run SQL with huge timeout",
        assigned_agent="data_analyst",
        tool_name="custom_sql",
        tool_args={
            "series_id": "v123456",
            "query": "SELECT 1 AS val",
            "timeout_seconds": 86400,
        },
    )
    state = AgentState(
        session_id="s_clamp",
        thread_id="t_clamp",
        plan=QueryPlan(objective="Clamp timeout", steps=(step,), active_step_id=1),
    )
    delta = await data_analyst_node(state)
    assert delta["plan"] is not None
    assert delta["plan"].steps[0].status == StepStatus.COMPLETED
    assert observed_timeouts == [MAX_ANALYST_TIMEOUT_SECONDS]
