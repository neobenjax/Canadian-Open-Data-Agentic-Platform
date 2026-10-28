"""Comprehensive test suite for CAN-23 Data Analyst Node, Recipes, and Zero-Trust Sandbox."""

from __future__ import annotations

import duckdb
import pyarrow as pa
import pytest

from candata_agent.analyst import (
    SandboxedDuckDB,
    SecurityValidationError,
    affordability_burden_ratio,
    annual_inflation_rate,
    calendar_year_aggregation,
    cross_geography_ranking,
    data_analyst_node,
    discrete_regime_change_counter,
    multi_year_cagr,
    percentage_point_spread,
    validate_sql_security,
    yoy_point_to_point,
)
from candata_agent.state import (
    AgentState,
    PlanStep,
    QueryPlan,
    StepStatus,
)

# ==============================================================================
# 1. Zero-Trust Sandbox & Injection Resistance Tests
# ==============================================================================


def test_validate_sql_allows_clean_select() -> None:
    """Standard read-only SELECT and WITH statements pass validation."""
    validate_sql_security("SELECT * FROM series_table WHERE date >= '2024-01-01'")
    validate_sql_security("WITH cte AS (SELECT value FROM t) SELECT * FROM cte")


def test_validate_sql_rejects_empty_query() -> None:
    """Empty queries are rejected."""
    with pytest.raises(SecurityValidationError, match="Empty SQL query"):
        validate_sql_security("   ")


def test_validate_sql_rejects_multistatement_semicolon() -> None:
    """Chained statements via semicolons are blocked."""
    with pytest.raises(SecurityValidationError, match="Multi-statement queries"):
        validate_sql_security("SELECT 1; DROP TABLE users;")


def test_validate_sql_rejects_forbidden_commands() -> None:
    """DDL, DML, administrative commands, and settings changes are blocked."""
    forbidden = [
        "INSERT INTO table VALUES (1, 2)",
        "UPDATE table SET val = 0",
        "DELETE FROM table",
        "DROP TABLE users",
        "ALTER TABLE series ADD COLUMN x INT",
        "CREATE TABLE backdoor AS SELECT 1",
        "ATTACH 'database.db'",
        "DETACH database",
        "COPY series TO 'out.parquet'",
        "PRAGMA version",
        "CALL test_proc()",
        "INSTALL httpfs",
        "LOAD httpfs",
        "SET enable_external_access = true",
        "EXPORT DATABASE 'backup'",
        "CHECKPOINT",
    ]
    for sql in forbidden:
        with pytest.raises(SecurityValidationError, match="Security Violation"):
            validate_sql_security(sql)


def test_validate_sql_rejects_dangerous_table_functions() -> None:
    """File readers, scanners, and environment inspection functions are blocked."""
    dangerous = [
        "SELECT * FROM read_csv('/etc/passwd')",
        "SELECT * FROM read_parquet('s3://bucket/data.parquet')",
        "SELECT * FROM read_text('C:/Windows/win.ini')",
        "SELECT * FROM read_blob('key.pem')",
        "SELECT * FROM read_json('config.json')",
        "SELECT * FROM glob('*')",
        "SELECT current_setting('home_directory')",
    ]
    for sql in dangerous:
        with pytest.raises(SecurityValidationError, match="Security Violation"):
            validate_sql_security(sql)


def test_sandbox_driver_lockdown_blocks_external_access() -> None:
    """DuckDB C++ driver configuration strictly blocks external filesystem reads."""
    with SandboxedDuckDB() as db:
        with pytest.raises(duckdb.Error):
            # Attempt direct execution of file read if bypass validation was attempted
            db.connection.execute("SELECT * FROM read_csv('test.csv')")


# ==============================================================================
# 2. Economic Recipes Mathematical Accuracy Tests
# ==============================================================================


def test_annual_inflation_rate_recipe() -> None:
    """Annual inflation rate calculates mean index per year and YoY % change (GT-10, GT-11)."""
    # 2024: 12 months with index 100.0 (average 100.0)
    dates_2024 = [f"2024-{m:02d}" for m in range(1, 13)]
    vals_2024 = [100.0] * 12

    # 2025: 12 months with index 103.1 (average 103.1 -> +3.1% inflation)
    dates_2025 = [f"2025-{m:02d}" for m in range(1, 13)]
    vals_2025 = [103.1] * 12

    table = pa.Table.from_pydict({"date": dates_2024 + dates_2025, "value": vals_2024 + vals_2025})

    rows, query = annual_inflation_rate(table)
    assert len(rows) == 2
    assert rows[0]["cal_year"] == "2025"
    assert rows[0]["avg_index"] == 103.1
    assert rows[0]["annual_inflation_pct"] == 3.1
    assert rows[1]["cal_year"] == "2024"
    assert rows[1]["annual_inflation_pct"] is None  # Baseline year


def test_yoy_point_to_point_recipe() -> None:
    """Point-to-point calculation with 12-month lag computes exact YoY change (GT-01, GT-12)."""
    dates = [f"2024-{m:02d}" for m in range(1, 13)] + [f"2025-{m:02d}" for m in range(1, 13)]
    # 2024-01 value = 1972.0, 2025-01 value = 2045.0 (GT-01 rents: +73.0, +3.7018%)
    values = [1972.0] + [2000.0] * 11 + [2045.0] + [2050.0] * 11

    table = pa.Table.from_pydict({"date": dates, "value": values})
    rows, _ = yoy_point_to_point(table, lag=12)

    # Latest row is 2025-12; find 2025-01 row
    jan_2025 = [r for r in rows if r["obs_date"] == "2025-01"][0]
    assert jan_2025["current_value"] == 2045.0
    assert jan_2025["lag_value"] == 1972.0
    assert jan_2025["change_absolute"] == 73.0
    assert jan_2025["change_pct"] == pytest.approx(3.7018, rel=1e-3)


def test_percentage_point_spread_recipe() -> None:
    """Rate spread calculates difference in percentage points and basis points (GT-02)."""
    table_a = pa.Table.from_pydict({"date": ["2025", "2023"], "value": [3.0, 1.4]})
    table_b = pa.Table.from_pydict({"date": ["2025", "2023"], "value": [1.4, 1.4]})

    rows, _ = percentage_point_spread(
        table_a,
        table_b,
        series_a_name="rate_2025",
        series_b_name="rate_2023",
    )
    assert len(rows) == 2
    row_2025 = rows[0]
    assert row_2025["spread_pp"] == 1.6
    assert row_2025["spread_bps"] == 160.0


def test_affordability_burden_ratio_recipe() -> None:
    """Affordability burden computes annual rent as share of median income (GT-07)."""
    rent_tbl = pa.Table.from_pydict({"date": ["2024"], "value": [2000.0]})  # $2k/mo = $24k/yr
    inc_tbl = pa.Table.from_pydict({"date": ["2024"], "value": [60000.0]})  # $60k/yr

    rows, _ = affordability_burden_ratio(rent_tbl, inc_tbl)
    assert len(rows) == 1
    assert rows[0]["monthly_rent"] == 2000.0
    assert rows[0]["annual_rent"] == 24000.0
    assert rows[0]["rent_to_income_pct"] == 40.0


def test_multi_year_cagr_recipe() -> None:
    """Multi-year CAGR computes compound annual growth and cumulative change (GT-08)."""
    res, _ = multi_year_cagr(
        start_val=100.0,
        end_val=121.0,
        num_years=2.0,
        start_date="2022",
        end_date="2024",
    )
    assert res["cagr_pct"] == 10.0
    assert res["cumulative_growth_pct"] == 21.0


def test_cross_geography_ranking_recipe() -> None:
    """Cross-regional ranking orders by value and computes gap to leader (GT-04)."""
    table = pa.Table.from_pydict(
        {
            "geography": ["Toronto", "Oshawa", "Hamilton"],
            "value": [3.0, 2.0, 1.5],
        }
    )
    rows, _ = cross_geography_ranking(table)
    assert len(rows) == 3
    assert rows[0]["geography"] == "Toronto"
    assert rows[0]["ranking"] == 1
    assert rows[0]["gap_to_leader_pp"] == 0.0

    assert rows[1]["geography"] == "Oshawa"
    assert rows[1]["ranking"] == 2
    assert rows[1]["gap_to_leader_pp"] == 1.0

    assert rows[2]["geography"] == "Hamilton"
    assert rows[2]["ranking"] == 3
    assert rows[2]["gap_to_leader_pp"] == 1.5


def test_calendar_year_aggregation_recipe() -> None:
    """Aggregates monthly flows into annual totals (GT-05)."""
    dates = [f"2025-{m:02d}" for m in range(1, 13)]
    starts = [1000.0] * 12
    table = pa.Table.from_pydict({"date": dates, "value": starts})

    rows, _ = calendar_year_aggregation(table, agg_func="SUM")
    assert len(rows) == 1
    assert rows[0]["cal_year"] == "2025"
    assert rows[0]["aggregated_total"] == 12000.0
    assert rows[0]["observed_months"] == 12


def test_discrete_regime_change_counter_recipe() -> None:
    """Counts rate changes and records boundary values across a calendar year (GT-13)."""
    # 4 distinct dates with 3 changes in rate (5.0 -> 4.75 -> 4.5 -> 4.25)
    dates = ["2025-01-01", "2025-03-01", "2025-06-01", "2025-09-01"]
    rates = [5.0, 4.75, 4.5, 4.25]
    table = pa.Table.from_pydict({"date": dates, "value": rates})

    res, _ = discrete_regime_change_counter(table, year="2025")
    assert res["calendar_year"] == "2025"
    assert res["rate_change_count"] == 3
    assert res["year_start_rate"] == 5.0
    assert res["year_end_rate"] == 4.25
    assert res["min_rate"] == 4.25
    assert res["max_rate"] == 5.0


# ==============================================================================
# 3. LangGraph Data Analyst Node Integration Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_data_analyst_node_execution() -> None:
    """Data Analyst node executes recipe, produces SQLArtifact, and advances QueryPlan."""
    step = PlanStep(
        step_id=1,
        description="Calculate YoY rent inflation",
        assigned_agent="data_analyst",
        tool_name="yoy_point_to_point",
        tool_args={
            "series_id": "v3823103",
            "lag": 1,
            "table": [
                {"date": "2024", "value": 1972.0},
                {"date": "2025", "value": 2045.0},
            ],
        },
    )
    plan = QueryPlan(
        objective="Calculate rent inflation",
        steps=(step,),
        active_step_id=1,
    )
    state = AgentState(
        session_id="test_sess",
        thread_id="test_th",
        plan=plan,
    )

    delta = await data_analyst_node(state)

    # 1. Assert SQLArtifact creation
    assert "sql_artifacts" in delta
    assert len(delta["sql_artifacts"]) == 1
    artifact = delta["sql_artifacts"][0]
    assert artifact.source_series_id == "v3823103"
    assert artifact.row_count == 2
    assert "ROUND" in artifact.sql_query

    # 2. Assert Message generation
    assert "messages" in delta
    assert len(delta["messages"]) == 1
    msg = delta["messages"][0]
    assert "Data Analyst Execution" in msg.content
    assert "Zero mental math" in msg.content

    # 3. Assert PlanStep advancement
    assert "plan" in delta
    updated_plan = delta["plan"]
    assert updated_plan is not None
    assert updated_plan.steps[0].status == StepStatus.COMPLETED
    assert updated_plan.completed is True


@pytest.mark.asyncio
async def test_data_analyst_node_handles_failure_gracefully() -> None:
    """When an analytical step fails, node marks step as FAILED and returns descriptive error."""
    step = PlanStep(
        step_id=1,
        description="Attempt malicious query",
        assigned_agent="data_analyst",
        tool_name="custom_sql",
        tool_args={"query": "DROP TABLE critical_data;"},
    )
    plan = QueryPlan(
        objective="Execute test query",
        steps=(step,),
        active_step_id=1,
    )
    state = AgentState(
        session_id="test_sess",
        thread_id="test_th",
        plan=plan,
    )

    delta = await data_analyst_node(state)

    # Step marked FAILED
    updated_plan = delta["plan"]
    assert updated_plan is not None
    assert updated_plan.steps[0].status == StepStatus.FAILED
    assert "Security Violation" in str(updated_plan.steps[0].result_summary)

    # Error message logged
    assert len(delta["messages"]) == 1
    assert "Data Analyst Execution Failed" in delta["messages"][0].content
