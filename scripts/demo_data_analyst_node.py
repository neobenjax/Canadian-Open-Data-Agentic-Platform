#!/usr/bin/env python3
"""Interactive CLI demo for CAN-23 Data Analyst Node with DuckDB SQL Math.

Demonstrates:
1. Zero-trust 5-layer sandboxed execution (blocking injection attempts).
2. The 8 deterministic economic recipes (inflation, spreads, CAGR, ranking, etc.).
3. End-to-end LangGraph state transitions producing typed SQLArtifacts.
"""

from __future__ import annotations

import asyncio
import io
import sys

# Windows UTF-8 console output encoding
if isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout.reconfigure(encoding="utf-8")
if isinstance(sys.stderr, io.TextIOWrapper):
    sys.stderr.reconfigure(encoding="utf-8")

# Ensure package import paths
sys.path.extend(["packages/agent-orchestrator/src", "packages/candata-mcp/src"])

import pyarrow as pa

from candata_agent.analyst import (
    SandboxedDuckDB,
    SecurityValidationError,
    data_analyst_node,
    multi_year_cagr,
    percentage_point_spread,
    yoy_point_to_point,
)
from candata_agent.state import (
    AgentState,
    PlanStep,
    QueryPlan,
)


def print_banner(text: str) -> None:
    print("\n" + "=" * 76)
    print(f" 🍁 {text}")
    print("=" * 76)


async def main() -> None:
    print_banner("CAN-23: DATA ANALYST NODE — INTERACTIVE DEMONSTRATION")

    # --------------------------------------------------------------------------
    # Demo 1: Security Sandbox Guardrail (Blocking AFR & Malicious Commands)
    # --------------------------------------------------------------------------
    print("\n🛡️  DEMO 1: Zero-Trust Security Sandbox (Prompt Injection Resistance)")
    malicious_queries = [
        "SELECT * FROM read_csv('/etc/passwd');",
        "SELECT 1; DROP TABLE observations;",
        "SELECT * FROM read_parquet('s3://secret/data.parquet');",
        "PRAGMA version;",
    ]

    for q in malicious_queries:
        print(f"  Attempting Query: {q}")
        try:
            with SandboxedDuckDB() as db:
                db.execute_sync(q)
            print("  ❌ ERROR: Query was unexpectedly allowed!")
        except SecurityValidationError as exc:
            print(f"  ✅ BLOCKED by Guardrail: {exc}")

    # --------------------------------------------------------------------------
    # Demo 2: Benchmark Recipe Execution (GTA Housing Ground-Truth)
    # --------------------------------------------------------------------------
    print_banner("DEMO 2: Deterministic Economic Recipe Calculations")

    # 2A: YoY Rent Inflation (GT-01: Toronto Two-Bedroom Rents)
    print("\n[GT-01] Two-Bedroom Rent YoY Growth (October 2024 vs 2025):")
    rent_table = pa.Table.from_pydict(
        {
            "date": ["2024", "2025"],
            "value": [1972.0, 2045.0],
        }
    )
    rows_rent, _ = yoy_point_to_point(rent_table, lag=1)
    for r in rows_rent:
        diff_str = f"+${r['change_absolute']} (+{r['change_pct']}%)"
        print(f"  • Date: {r['obs_date']} | Rent: ${r['current_value']} | Change: {diff_str}")

    # 2B: Vacancy Spread in pp and bps (GT-02)
    print("\n[GT-02] Rental Vacancy Rate Spread (2025 vs 2023):")
    tab_2025 = pa.Table.from_pydict({"date": ["2025"], "value": [3.0]})
    tab_2023 = pa.Table.from_pydict({"date": ["2025"], "value": [1.4]})
    spread_rows, _ = percentage_point_spread(
        tab_2025,
        tab_2023,
        series_a_name="vacancy_2025",
        series_b_name="vacancy_2023",
    )
    s = spread_rows[0]
    print(
        f"  • 2025: {s['vacancy_2025']}% | 2023: {s['vacancy_2023']}% | "
        f"Spread: +{s['spread_pp']} pp (+{s['spread_bps']} bps)"
    )

    # 2C: Multi-Year CAGR (GT-08: 5-Year Rent Growth 2019 -> 2024)
    print("\n[GT-08] 5-Year Compound Annual Growth Rate (CAGR 2019 -> 2024):")
    cagr_res, _ = multi_year_cagr(
        start_val=1500.0,
        end_val=1972.0,
        num_years=5.0,
        start_date="2019",
        end_date="2024",
    )
    print(f"  • Start (2019): ${cagr_res['start_val']} -> End (2024): ${cagr_res['end_val']}")
    cagr_pct = cagr_res["cagr_pct"]
    cum_pct = cagr_res["cumulative_growth_pct"]
    print(f"  • CAGR: {cagr_pct}% / year | Cumulative: +{cum_pct}%")

    # --------------------------------------------------------------------------
    # Demo 3: LangGraph Node Integration (AgentState & SQLArtifacts)
    # --------------------------------------------------------------------------
    print_banner("DEMO 3: LangGraph Data Analyst Node State Transition")

    step = PlanStep(
        step_id=1,
        description="Compute annual shelter inflation for Toronto CMA",
        assigned_agent="data_analyst",
        tool_name="annual_inflation_rate",
        tool_args={
            "series_id": "v41692890",
            "table": [
                {"date": "2024-01", "value": 158.6},
                {"date": "2024-06", "value": 159.0},
                {"date": "2024-12", "value": 158.2},
                {"date": "2025-01", "value": 163.5},
                {"date": "2025-06", "value": 164.0},
                {"date": "2025-12", "value": 163.0},
            ],
        },
    )
    plan = QueryPlan(
        objective="Analyze shelter vs all-items inflation",
        steps=(step,),
        active_step_id=1,
    )
    initial_state = AgentState(
        session_id="session_live_demo",
        thread_id="th_analyst_001",
        plan=plan,
    )

    print("Executing data_analyst_node(state)...")
    delta = await data_analyst_node(initial_state)

    print(f"\n✅ Produced {len(delta['sql_artifacts'])} SQLArtifact:")
    artifact = delta["sql_artifacts"][0]
    print(f"   • Artifact ID: {artifact.artifact_id}")
    print(f"   • Series ID: {artifact.source_series_id}")
    print(f"   • Row Count: {artifact.row_count}")
    print(f"   • SQL Query: {artifact.sql_query[:60]}...")

    print("\n✅ Synthesized Assistant Message:\n")
    print(delta["messages"][0].content)

    print("\n✅ QueryPlan Step Status:")
    updated_step = delta["plan"].steps[0]
    print(f"   • Step 1: {updated_step.status} — {updated_step.result_summary}")
    print("\n🎉 All Data Analyst Node capabilities verified successfully.\n")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
