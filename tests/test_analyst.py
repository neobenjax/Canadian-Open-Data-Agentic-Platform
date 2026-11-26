"""Tests for Issue #50: Data Analyst Node SQL timeout and dual citation retention."""

from __future__ import annotations

import asyncio
import time

import pyarrow as pa
import pytest

from candata_agent.analyst import (
    affordability_burden_ratio,
    change_vs_standard_error,
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
    table_a = pa.Table.from_pydict(
        {"date": ["2025"], "value": [3.0]}, metadata={b"unit": b"Percent"}
    )
    table_b = pa.Table.from_pydict(
        {"date": ["2025"], "value": [1.4]}, metadata={b"unit": b"Percent"}
    )

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
async def test_dual_citations_fail_loud_when_missing_or_unmatched() -> None:
    """Dual-series recipes fail loud when either input citation is missing or unmatched."""
    cpi_cit = _make_citation("18-10-0004-01", "v41690973", "CPI")
    rent_cit = _make_citation("34-10-0143-01", "v3823103", "Average Monthly Rent")
    income_cit = _make_citation("11-10-0239-01", "v11223344", "Median After-Tax Income")

    # Case 1: state has (CPI, rent, income); only rent series_id given -> fails naming income
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
    assert "sql_artifacts" not in delta1
    assert delta1["plan"] is not None
    failed1 = delta1["plan"].steps[0]
    assert failed1.status == StepStatus.FAILED
    assert failed1.error is not None
    assert "income" in failed1.error
    assert "v3823103" not in failed1.error

    # Case 2: state has (CPI, income); rent v3823103 missing -> fails naming both rent & income
    state2 = AgentState(
        session_id="s2",
        thread_id="t2",
        plan=QueryPlan(objective="GT-07", steps=(step1,), active_step_id=1),
        citations=(cpi_cit, income_cit),
    )
    delta2 = await data_analyst_node(state2)
    assert "sql_artifacts" not in delta2
    assert delta2["plan"] is not None
    failed2 = delta2["plan"].steps[0]
    assert failed2.status == StepStatus.FAILED
    assert failed2.error is not None
    assert "rent (v3823103)" in failed2.error
    assert "income" in failed2.error

    # Case 3: both series_id and income_series_id provided -> resolves exact pair from state
    step3 = PlanStep(
        step_id=1,
        description="GT-07 with both series IDs",
        assigned_agent="data_analyst",
        tool_name="affordability_burden_ratio",
        tool_args={
            "rent_table": [{"date": "2024", "value": 2000.0}],
            "income_table": [{"date": "2024", "value": 60000.0}],
            "series_id": "v3823103",
            "income_series_id": "v11223344",
        },
    )
    state3 = AgentState(
        session_id="s3",
        thread_id="t3",
        plan=QueryPlan(objective="GT-07", steps=(step3,), active_step_id=1),
        citations=(cpi_cit, rent_cit, income_cit),
    )
    delta3 = await data_analyst_node(state3)
    assert delta3["plan"] is not None
    assert delta3["plan"].steps[0].status == StepStatus.COMPLETED
    art3 = delta3["sql_artifacts"][0]
    assert art3.citations == (rent_cit, income_cit)
    assert art3.citation == rent_cit


@pytest.mark.asyncio
async def test_data_analyst_node_invalid_timeout_marks_step_failed() -> None:
    """Non-numeric or non-positive timeout_seconds marks step FAILED cleanly."""
    for bad_timeout in ("abc", -1.0, 0.0, float("nan"), float("inf"), True, False):
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


@pytest.mark.asyncio
async def test_validate_plan_to_analyst_dual_series_handoff() -> None:
    """Planner-to-analyst handoff binds both dual-series IDs and fails loud on gaps."""
    import json

    from candata_agent.supervisor.registry import (
        DraftStep,
        PlanDraft,
        PlanValidationError,
        validate_plan,
    )

    cpi_cit = _make_citation("18-10-0004-01", "v41690973", "CPI")
    cit_a = _make_citation("10-10-0122-01", "v2293021", "Policy Rate")
    cit_b = _make_citation("10-10-0122-01", "v39079", "5-Year Yield")
    rent_cit = _make_citation("34-10-0143-01", "v3823103", "Average Monthly Rent")
    income_cit = _make_citation("11-10-0239-01", "v11223344", "Median After-Tax Income")

    # 1. percentage_point_spread via validate_plan
    spread_draft = PlanDraft(
        objective="Spread between policy rate and 5-year yield",
        steps=(
            DraftStep(
                tool="fetch_statcan_vector",
                args_json=json.dumps(
                    {
                        "vector_id": "v2293021",
                        "start": "2024-01",
                        "end": "2024-02",
                        "into": "table_a",
                    }
                ),
                description="Fetch series A",
            ),
            DraftStep(
                tool="fetch_statcan_vector",
                args_json=json.dumps(
                    {"vector_id": "v39079", "start": "2024-01", "end": "2024-02", "into": "table_b"}
                ),
                description="Fetch series B",
            ),
            DraftStep(
                tool="percentage_point_spread",
                args_json=json.dumps({"series_a_name": "policy", "series_b_name": "yield_5y"}),
                description="Compute percentage point spread",
            ),
        ),
    )
    spread_plan = validate_plan(spread_draft)
    spread_step = spread_plan.steps[2]
    assert spread_step.tool_args["series_id"] == "v2293021"
    assert spread_step.tool_args["series_b_id"] == "v39079"

    spread_state = AgentState(
        session_id="s_spread",
        thread_id="t_spread",
        plan=spread_plan.model_copy(update={"active_step_id": spread_step.step_id}),
        scratchpad={
            "table_a": [{"date": "2024-01-01", "value": 5.0}],
            "table_a_source": "v2293021",
            "table_a_unit": "Percent",
            "table_b": [{"date": "2024-01-01", "value": 3.5}],
            "table_b_source": "v39079",
            "table_b_unit": "Percent",
        },
        citations=(cpi_cit, cit_a, cit_b),
    )
    spread_delta = await data_analyst_node(spread_state)
    assert spread_delta["plan"].steps[2].status == StepStatus.COMPLETED
    assert spread_delta["sql_artifacts"][0].citations == (cit_a, cit_b)

    # 2. affordability_burden_ratio via validate_plan
    gt07_draft = PlanDraft(
        objective="Affordability burden ratio",
        steps=(
            DraftStep(
                tool="fetch_statcan_vector",
                args_json=json.dumps(
                    {"vector_id": "v3823103", "start": "2024", "end": "2024", "into": "rent_table"}
                ),
                description="Fetch rent",
            ),
            DraftStep(
                tool="fetch_statcan_vector",
                args_json=json.dumps(
                    {
                        "vector_id": "v11223344",
                        "start": "2024",
                        "end": "2024",
                        "into": "income_table",
                    }
                ),
                description="Fetch income",
            ),
            DraftStep(
                tool="affordability_burden_ratio",
                args_json="{}",
                description="Compute affordability burden ratio",
            ),
        ),
    )
    gt07_plan = validate_plan(gt07_draft)
    gt07_step = gt07_plan.steps[2]
    assert gt07_step.tool_args["series_id"] == "v3823103"
    assert gt07_step.tool_args["income_series_id"] == "v11223344"

    gt07_state = AgentState(
        session_id="s_gt07",
        thread_id="t_gt07",
        plan=gt07_plan.model_copy(update={"active_step_id": gt07_step.step_id}),
        scratchpad={
            "rent_table": [{"date": "2024", "value": 2000.0}],
            "rent_table_source": "v3823103",
            "income_table": [{"date": "2024", "value": 60000.0}],
            "income_table_source": "v11223344",
        },
        citations=(cpi_cit, rent_cit, income_cit),
    )
    gt07_delta = await data_analyst_node(gt07_state)
    assert gt07_delta["plan"].steps[2].status == StepStatus.COMPLETED
    assert gt07_delta["sql_artifacts"][0].citations == (rent_cit, income_cit)

    # 3. Break-it-on-purpose (missing/deleted citation): deleting second citation fails loud
    broken_state = gt07_state.model_copy(update={"citations": (cpi_cit, rent_cit)})
    broken_delta = await data_analyst_node(broken_state)
    assert "sql_artifacts" not in broken_delta
    assert broken_delta["plan"].steps[2].status == StepStatus.FAILED
    assert "v11223344" in (broken_delta["plan"].steps[2].error or "")

    # 4. Break-it-on-purpose (extras rejected): model cannot supply series_b_id or income_series_id
    with pytest.raises(PlanValidationError, match="series_b_id: Extra inputs"):
        validate_plan(
            PlanDraft(
                objective="Inject extra series_b_id",
                steps=(
                    spread_draft.steps[0],
                    spread_draft.steps[1],
                    DraftStep(
                        tool="percentage_point_spread",
                        args_json=json.dumps({"series_b_id": "v_spoofed"}),
                        description="Attempt to spoof second ID",
                    ),
                ),
            )
        )
    with pytest.raises(PlanValidationError, match="income_series_id: Extra inputs"):
        validate_plan(
            PlanDraft(
                objective="Inject extra income_series_id",
                steps=(
                    gt07_draft.steps[0],
                    gt07_draft.steps[1],
                    DraftStep(
                        tool="affordability_burden_ratio",
                        args_json=json.dumps({"income_series_id": "v_spoofed"}),
                        description="Attempt to spoof income ID",
                    ),
                ),
            )
        )

    # 5. Break-it-on-purpose (missing fetch step): omitting second slot fails validation
    with pytest.raises(PlanValidationError, match="no earlier fetch step fills table_b"):
        validate_plan(
            PlanDraft(
                objective="Missing table_b",
                steps=(
                    spread_draft.steps[0],
                    spread_draft.steps[2],
                ),
            )
        )


# ---------------------------------------------------------------------------------------------
# Issue #109: is a change statistically significant? (change vs its published standard error)
# ---------------------------------------------------------------------------------------------


def _monthly(unit: str, *points: tuple[str, float]) -> pa.Table:
    table = pa.table({"date": [d for d, _ in points], "value": [v for _, v in points]})
    return table.replace_schema_metadata({b"unit": unit.encode()})


def test_change_vs_standard_error_m2_follow_up() -> None:
    """The CAN-35 M2 follow-up, with October 2026 LFS values (14-10-0287-01, released Nov 6).

    Ontario 7.6 -> 7.3 with SE 0.3: the 68% interval is -0.6 to 0.0, which reaches zero, so
    the change is not significant. Alberta 7.6 -> 7.3 with SE 0.6 is well inside one SE.
    """
    ontario = change_vs_standard_error(
        _monthly("Percentage", ("2025-10-01", 7.6), ("2026-10-01", 7.3)),
        _monthly("Percentage", ("2026-10-01", 0.3)),
        source_series_id="v2063949",
    )
    (on,) = ontario.rows
    assert on["change_absolute"] == pytest.approx(-0.3)
    assert on["standard_error"] == 0.3
    assert on["change_in_se"] == pytest.approx(-1.0)
    assert (on["ci68_low"], on["ci68_high"]) == (pytest.approx(-0.6), pytest.approx(0.0))
    assert on["significant_68"] is False
    assert on["significant_95"] is False

    alberta = change_vs_standard_error(
        _monthly("Percentage", ("2025-10-01", 7.6), ("2026-10-01", 7.3)),
        _monthly("Percentage", ("2026-10-01", 0.6)),
    )
    assert alberta.rows[0]["change_in_se"] == pytest.approx(-0.5)
    assert alberta.rows[0]["significant_68"] is False


def test_change_vs_standard_error_follows_the_table_footnote_examples() -> None:
    """14-10-0287-01's footnote: +160,000 with SE 55,000 is significant; +40,000 is not."""
    se = _monthly("Persons in thousands", ("2026-10-01", 55.0))
    big = change_vs_standard_error(
        _monthly("Persons in thousands", ("2025-10-01", 1000.0), ("2026-10-01", 1160.0)), se
    )
    assert (big.rows[0]["ci68_low"], big.rows[0]["ci68_high"]) == (105.0, 215.0)
    assert big.rows[0]["significant_68"] is True
    assert big.rows[0]["significant_95"] is True  # 160 > 2 x 55

    small = change_vs_standard_error(
        _monthly("Persons in thousands", ("2025-10-01", 1000.0), ("2026-10-01", 1040.0)), se
    )
    assert (small.rows[0]["ci68_low"], small.rows[0]["ci68_high"]) == (-15.0, 95.0)
    assert small.rows[0]["significant_68"] is False


def test_change_equal_to_its_standard_error_is_not_flipped_by_float_noise() -> None:
    # 7.9 - 7.6 is 0.30000000000000071 in floating point; the interval still touches zero.
    art = change_vs_standard_error(
        _monthly("Percentage", ("2025-10-01", 7.6), ("2026-10-01", 7.9)),
        _monthly("Percentage", ("2026-10-01", 0.3)),
    )
    assert art.rows[0]["significant_68"] is False


def test_change_vs_standard_error_month_to_month_and_missing_prior() -> None:
    estimate = _monthly("Percentage", ("2026-08-01", 7.0), ("2026-09-01", 7.4), ("2026-10-01", 7.3))
    se = _monthly("Percentage", ("2026-09-01", 0.2), ("2026-10-01", 0.2))
    rows = change_vs_standard_error(estimate, se, change_period="month_to_month").rows
    assert [r["obs_date"] for r in rows] == ["2026-10-01", "2026-09-01"]  # periods with an SE
    assert rows[0]["change_absolute"] == pytest.approx(-0.1)
    assert rows[1]["change_absolute"] == pytest.approx(0.4)
    assert rows[1]["significant_68"] is True and rows[1]["significant_95"] is False

    yoy = change_vs_standard_error(estimate, se).rows  # no estimate a year earlier
    assert yoy[0]["lag_value"] is None and yoy[0]["significant_68"] is None
    assert "Missing prior period" in yoy[0]["warning"]


def test_change_vs_standard_error_fails_loud() -> None:
    estimate = _monthly("Percentage", ("2025-10-01", 7.6), ("2026-10-01", 7.3))
    with pytest.raises(ValueError, match="same unit"):
        change_vs_standard_error(estimate, _monthly("Persons in thousands", ("2026-10-01", 5.0)))
    with pytest.raises(ValueError, match="no period with both"):
        change_vs_standard_error(estimate, _monthly("Percentage", ("2024-10-01", 0.3)))
    with pytest.raises(ValueError, match="change_period"):
        change_vs_standard_error(estimate, estimate, change_period="quarterly")

    zero = change_vs_standard_error(estimate, _monthly("Percentage", ("2026-10-01", 0.0)))
    assert zero.rows[0]["significant_68"] is None
    assert "not positive" in zero.rows[0]["warning"]


async def test_analyst_node_tests_significance_with_both_citations() -> None:
    est_cit = _make_citation("14-10-0287-01", "v2063949", "Ontario unemployment rate")
    se_cit = _make_citation("14-10-0287-01", "v101887840", "Ontario SE of year-over-year change")
    step = PlanStep(
        step_id=1,
        description="Is Ontario's change significant?",
        assigned_agent="data_analyst",
        tool_name="change_vs_standard_error",
        tool_args={
            "estimate_slot": "table_a",
            "standard_error_slot": "table_c",
            "series_id": "v2063949",
            "standard_error_series_id": "v101887840",
        },
    )
    state = AgentState(
        session_id="s",
        thread_id="t",
        plan=QueryPlan(objective="significance", steps=(step,), active_step_id=1),
        citations=(se_cit, est_cit),
        scratchpad={
            "table_a": [{"date": "2025-10-01", "value": 7.6}, {"date": "2026-10-01", "value": 7.3}],
            "table_c": [{"date": "2026-10-01", "value": 0.3}],
            "table_a_unit": "Percentage",
            "table_c_unit": "Percentage",
        },
    )
    out = await data_analyst_node(state)
    (art,) = out["sql_artifacts"]
    assert art.source_series_id == "v2063949"
    assert [c.core.vector_id for c in art.citations] == ["v2063949", "v101887840"]
    assert art.rows[0]["significant_68"] is False
    assert out["plan"].steps[0].status is StepStatus.COMPLETED

    no_se_cit = state.model_copy(update={"citations": (est_cit,)})
    failed = await data_analyst_node(no_se_cit)
    assert failed["plan"].steps[0].status is StepStatus.FAILED
    assert "standard_error (v101887840)" in failed["plan"].steps[0].error


def test_change_vs_standard_error_keeps_only_periods_it_can_assess() -> None:
    """A 13-month fetch with a monthly SE has one assessable year-over-year change, not 13."""
    months = [f"2025-{m:02d}-01" for m in range(10, 13)] + [
        f"2026-{m:02d}-01" for m in range(1, 11)
    ]
    estimate = _monthly("Percentage", *((d, 7.0) for d in months))
    se = _monthly("Percentage", *((d, 0.3) for d in months))
    rows = change_vs_standard_error(estimate, se).rows
    assert [r["obs_date"] for r in rows] == ["2026-10-01"]
    assert rows[0]["warning"] is None
