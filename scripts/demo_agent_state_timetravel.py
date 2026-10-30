"""Interactive demonstration for CAN-21 LangGraph AgentState and AsyncSqliteSaver.

Walks through:
1. Pydantic v2 AgentState initialization with strict schema validation.
2. Supervisor query planning and Data Analyst SQL artifact tracking.
3. Human-in-the-Loop (HITL) ambiguity breakpoint triggering and resumption.
4. AsyncSqliteSaver WAL-mode persistence and checkpoint history inspection.
5. Time-Travel rewind (`arollback_to`) and conversation branching/forking.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "packages" / "agent-orchestrator" / "src"))
sys.path.insert(0, str(ROOT_DIR / "packages" / "candata-mcp" / "src"))

# ruff: noqa: E402
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


def _print_header(title: str) -> None:
    print(f"\n{'=' * 78}")
    print(f"  {title}")
    print(f"{'=' * 78}")


async def run_demonstration() -> None:
    _print_header("CAN-21 LangGraph Multi-Agent State & Time-Travel Demo")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_file = Path(tmpdir) / "agent_checkpoints.db"
        print(f"[*] Initialized temporary SQLite checkpoint store: {db_file.name}")

        async with AsyncSqliteSaver(db_file) as checkpointer:
            thread_id = "thread_cpi_analysis_001"
            config = {"configurable": {"thread_id": thread_id}}

            # ------------------------------------------------------------------
            # Phase 1: User Query & Initial State
            # ------------------------------------------------------------------
            _print_header("Phase 1: User Query Ingestion (Step 0)")
            user_msg = AgentMessage(
                role=MessageRole.USER,
                content=(
                    "Compare shelter CPI between Toronto CMA and Ottawa-Gatineau from 2024 to 2025."
                ),
            )
            state = AgentState(
                session_id=thread_id,
                thread_id=thread_id,
                messages=add_messages((), user_msg),
                trace_context=TraceContext(
                    traceparent="00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
                    span_id="span_root_001",
                ),
                token_budget=TokenBudget(max_budget=128000, prompt_tokens_used=120),
            )
            chk_0 = await checkpointer.aput(config, state)
            print(f"[OK] State saved to checkpoint: {chk_0}")
            print(f"     Active Thread: {state.thread_id}")
            print(f"     Messages: {len(state.messages)} message(s)")
            print(f"     Token Budget Remaining: {state.token_budget.remaining_tokens}")

            # ------------------------------------------------------------------
            # Phase 2: Supervisor Planning Node
            # ------------------------------------------------------------------
            _print_header("Phase 2: Supervisor Decomposition & Query Plan (Step 1)")
            plan = QueryPlan(
                objective="Compare shelter CPI (Toronto vs Ottawa-Gatineau, 2024-2025)",
                steps=(
                    PlanStep(
                        step_id=1,
                        description="Resolve Toronto shelter CPI coordinate in table 18-10-0004-01",
                        assigned_agent="catalog_agent",
                        status=StepStatus.COMPLETED,
                    ),
                    PlanStep(
                        step_id=2,
                        description="Resolve Ottawa shelter CPI coordinate in table 18-10-0004-01",
                        assigned_agent="catalog_agent",
                        status=StepStatus.PENDING,
                    ),
                    PlanStep(
                        step_id=3,
                        description="Execute DuckDB SQL percentage change comparison",
                        assigned_agent="analyst_agent",
                        status=StepStatus.PENDING,
                    ),
                ),
                active_step_id=1,
            )
            supervisor_msg = AgentMessage(
                role=MessageRole.ASSISTANT,
                name="supervisor",
                content="Query plan formulated with 3 deterministic steps.",
            )
            state = state.model_copy(
                update={
                    "plan": plan,
                    "messages": add_messages(state.messages, supervisor_msg),
                    "token_budget": state.token_budget.model_copy(
                        update={"total_tokens_used": 650}
                    ),
                }
            )
            chk_1 = await checkpointer.aput(config, state)
            print(f"[OK] Query Plan committed to checkpoint: {chk_1}")
            for s in plan.steps:
                print(
                    f"     Step {s.step_id} [{s.status.value.upper()}]: "
                    f"{s.description} ({s.assigned_agent})"
                )

            # ------------------------------------------------------------------
            # Phase 3: Analytical SQL Execution & Official Citations
            # ------------------------------------------------------------------
            _print_header("Phase 3: Data Analyst Execution & Two-Tier Citations (Step 2)")
            sql_artifact = SQLArtifact(
                source_series_id="v41690973",
                sql_query=(
                    "SELECT ref_per, value, "
                    "((value - LAG(value, 12) OVER (ORDER BY ref_per)) / "
                    "LAG(value, 12) OVER (ORDER BY ref_per)) * 100 AS yoy_inflation "
                    "FROM statcan_cpi WHERE ref_per >= '2024-01' ORDER BY ref_per;"
                ),
                row_count=12,
                rows=(
                    {"ref_per": "2024-01", "value": 158.3, "yoy_inflation": 2.9},
                    {"ref_per": "2024-12", "value": 161.2, "yoy_inflation": 2.4},
                ),
            )
            citation = CitationEnvelope(
                publisher="Statistics Canada",
                core=CoreVerificationTuple(
                    table_id="18-10-0004-01",
                    vector_id="v41690973",
                    reference_period="2024-01/2024-12",
                ),
                enrichment=MetadataEnrichment(
                    coordinate="2.1",
                    release_or_revision_date="2025-01-15T08:30",
                    bilingual_title=BilingualTitle(
                        en="Consumer Price Index, monthly, not seasonally adjusted",
                        fr="Indice des prix à la consommation, mensuel, non désaisonnalisé",
                    ),
                    canonical_url="https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810000401",
                ),
            )
            state = state.model_copy(
                update={
                    "sql_artifacts": (*state.sql_artifacts, sql_artifact),
                    "citations": merge_citations(state.citations, citation),
                }
            )
            chk_2 = await checkpointer.aput(config, state)
            print(f"[OK] SQL Artifact & Citation saved to checkpoint: {chk_2}")
            print(f"     Artifact ID: {sql_artifact.artifact_id}")
            print(f"     Rows calculated: {sql_artifact.row_count}")
            print(f"     Cited Table: {citation.core.table_id} (Vector: {citation.core.vector_id})")

            # ------------------------------------------------------------------
            # Phase 4: Human-in-the-Loop Interruption Trigger
            # ------------------------------------------------------------------
            _print_header("Phase 4: Human-in-the-Loop (HITL) Interruption (Step 3)")
            interrupt = HITLInterrupt(
                interrupt_type=InterruptType.AMBIGUOUS_MEMBER,
                reason="Ambiguous geography name: multiple Ottawa boundaries detected.",
                details={
                    "candidates": [
                        "Ottawa (City)",
                        "Ottawa-Gatineau (CMA Ontario part)",
                        "Ottawa-Gatineau (CMA Total)",
                    ]
                },
                suggested_options=(
                    "Ottawa-Gatineau (CMA Total, Ontario/Quebec)",
                    "Ottawa-Gatineau (Ontario part, CMA)",
                    "Ottawa (City / Single Tier)",
                ),
            )
            state = state.model_copy(update={"active_interrupt": interrupt})
            chk_3 = await checkpointer.aput(config, state)
            print(f"[!] HITL Interruption triggered and checkpointed: {chk_3}")
            print(f"     Type: {interrupt.interrupt_type.value}")
            print(f"     Reason: {interrupt.reason}")
            print(f"     Suggested Options: {list(interrupt.suggested_options)}")

            # ------------------------------------------------------------------
            # Phase 5: Checkpoint History & Time-Travel Rewind
            # ------------------------------------------------------------------
            _print_header("Phase 5: Time-Travel Rollback & Conversation Forking")
            history = await checkpointer.alist(config)
            print(f"[*] Checkpoint history for thread '{thread_id}':")
            for h in history:
                print(
                    f"     - Checkpoint {h['checkpoint_id']} "
                    f"(run: {h['run_id']}) at {h['created_at']}"
                )

            # Rewind to Phase 2 (before the interrupt occurred)
            print(f"\n[*] Rewinding state back to Checkpoint {chk_1} (pre-interruption)...")
            rewound_state = await checkpointer.arollback_to(
                thread_id=thread_id,
                target_checkpoint_id=chk_1,
            )
            print(f"[OK] Successfully rolled back thread '{thread_id}'!")
            print(f"     Active Interrupt: {rewound_state.active_interrupt} (None expected)")
            print(f"     SQL Artifacts: {len(rewound_state.sql_artifacts)} (0 expected)")
            plan_obj = rewound_state.plan.objective if rewound_state.plan else None
            print(f"     Query Plan Objective: {plan_obj}")

            # Fork conversation into alternate exploration branch
            forked_thread = "thread_cpi_alt_ontario_only"
            print(
                f"\n[*] Forking conversation from Checkpoint {chk_1} "
                f"into new thread '{forked_thread}'..."
            )
            forked_state = await checkpointer.arollback_to(
                thread_id=thread_id,
                target_checkpoint_id=chk_1,
                new_thread_id=forked_thread,
            )
            print(f"[OK] Conversation forked into '{forked_state.thread_id}'!")
            print(f"     Session ID: {forked_state.session_id}")
            print(f"     Plan Preserved: {forked_state.plan is not None}")

            print("\n" + "=" * 78)
            print("  CAN-21 LangGraph State & Checkpoint Demo Successfully Finished!")
            print("=" * 78)


if __name__ == "__main__":
    asyncio.run(run_demonstration())
