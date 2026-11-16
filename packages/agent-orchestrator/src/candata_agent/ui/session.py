# pyright: reportMissingTypeStubs=false
"""Open the agent graph against the live official sources for the UI (CAN-32).

The planner is Claude when ``ANTHROPIC_API_KEY`` is set. Without a key the UI runs the demo
planner: fixed, validated plans for three benchmark questions, still executed, analysed and
verified against live WDS and Valet data. Nothing in demo mode is pre-computed.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from langgraph.graph.state import CompiledStateGraph

from candata_agent.checkpoint import AsyncSqliteSaver
from candata_agent.supervisor import DraftStep, PlanDraft, build_agent_graph, validate_plan
from candata_agent.supervisor.clarification import Resolution
from candata_agent.supervisor.context import PlanContext
from candata_agent.supervisor.node import Planner
from candata_agent.supervisor.planner import PlannerResult
from candata_mcp.connectors.boc_valet import ValetClient
from candata_mcp.connectors.statcan_wds import StatCanClient

DEFAULT_DB: Final = Path(".candata") / "ui_threads.db"


@dataclass(frozen=True, slots=True)
class DemoQuestion:
    question: str
    draft: PlanDraft


def _draft(objective: str, *steps: tuple[str, str, str]) -> PlanDraft:
    return PlanDraft(
        objective=objective,
        steps=tuple(DraftStep(tool=t, args_json=a, description=d) for t, a, d in steps),
    )


# GT-05, GT-12 and GT-13 from the GTA benchmark, with the plans the Claude planner produces
# for them after discovery (vectors confirmed with lookup_series on 2026-11-03).
DEMO_QUESTIONS: Final = (
    DemoQuestion(
        "In August 2026, how did shelter prices in Toronto change year over year, compared "
        "with overall consumer prices?",
        _draft(
            "Toronto shelter vs all-items CPI, Aug 2026 year over year",
            ("fetch_statcan_vector",
             '{"vector_id": "v41692889", "start": "2025-08", "end": "2026-08", "into": "table_a"}',
             "Toronto shelter CPI"),
            ("fetch_statcan_vector",
             '{"vector_id": "v41692888", "start": "2025-08", "end": "2026-08", "into": "table_b"}',
             "Toronto all-items CPI"),
            ("yoy_point_to_point", '{"slot": "table_a"}', "Toronto shelter CPI"),
            ("yoy_point_to_point", '{"slot": "table_b"}', "Toronto all-items CPI"),
        ),
    ),
    DemoQuestion(
        "How many housing units were started in the Toronto CMA in calendar year 2025, and "
        "how does that compare with 2024?",
        _draft(
            "Toronto CMA housing starts, 2025 vs 2024",
            ("fetch_statcan_vector", '{"vector_id": "v42127475", "start": "2024", "end": "2025"}',
             "Toronto CMA housing starts"),
            ("calendar_year_aggregation", '{"agg_func": "SUM"}', "Toronto CMA housing starts"),
        ),
    ),
    DemoQuestion(
        "How many times did the Bank of Canada change its policy rate in 2025?",
        _draft(
            "Policy rate changes in 2025",
            ("fetch_valet_series", '{"series_id": "V39079", "start": "2025", "end": "2025"}',
             "Target for the overnight rate"),
            ("discrete_regime_change_counter", '{"year": 2025}', "Policy rate changes"),
        ),
    ),
)  # fmt: skip


class DemoPlanner:
    """Plans only the demo questions; declines anything else with a pointer to live mode."""

    def __init__(self, questions: tuple[DemoQuestion, ...] = DEMO_QUESTIONS) -> None:
        self._plans = {_normal(q.question): q.draft for q in questions}

    async def plan(
        self,
        question: str,
        *,
        resolved: Sequence[Resolution] = (),
        context: PlanContext | None = None,
    ) -> PlannerResult:
        found = self._plans.get(_normal(question))
        if found is None:
            return PlannerResult(
                None,
                "demo mode plans only the example questions; set ANTHROPIC_API_KEY to plan "
                "any question with Claude",
            )
        return PlannerResult(validate_plan(found))


def _normal(text: str) -> str:
    return " ".join(text.lower().split())


def live_planner_available(api_key: str | None = None) -> bool:
    return bool(api_key or os.environ.get("ANTHROPIC_API_KEY"))


@asynccontextmanager
async def open_agent(
    *,
    db_path: Path = DEFAULT_DB,
    demo: bool | None = None,
    api_key: str | None = None,
) -> AsyncGenerator[tuple[CompiledStateGraph[Any, Any, Any, Any], bool]]:
    """Yield the compiled graph and whether it is in demo mode.

    Threads are checkpointed to ``db_path`` so a conversation survives Streamlit reruns.
    ``api_key`` allows session-isolated credentials without modifying process-wide
    ``os.environ``.
    """
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    use_demo = not key if demo is None else demo
    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with (
        StatCanClient() as statcan,
        ValetClient() as valet,
        AsyncSqliteSaver(db_path) as saver,
    ):
        planner: Planner
        if use_demo:
            planner = DemoPlanner()
        else:
            from anthropic import AsyncAnthropic

            from candata_agent.supervisor.planner import ClaudePlanner

            planner = ClaudePlanner(AsyncAnthropic(api_key=key), statcan)
        yield (
            build_agent_graph(planner=planner, statcan=statcan, valet=valet, checkpointer=saver),
            use_demo,
        )
