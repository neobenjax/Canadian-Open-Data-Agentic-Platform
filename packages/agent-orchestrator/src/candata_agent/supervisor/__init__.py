"""Supervisor agent (CAN-22): plans a question into validated, deterministic tool calls.

The Claude-backed planner lives in ``candata_agent.supervisor.planner`` and needs the optional
``agent`` extra (``uv sync --extra agent``); everything exported here works without it.
"""

from candata_agent.supervisor.graph import build_agent_graph
from candata_agent.supervisor.node import (
    Planner,
    make_data_fetcher_node,
    make_input_verifier_node,
    make_supervisor_node,
    route_from_supervisor,
)
from candata_agent.supervisor.registry import (
    TOOLS,
    DraftStep,
    PlanDraft,
    PlanValidationError,
    period_bounds,
    validate_plan,
)

__all__ = [
    "TOOLS",
    "DraftStep",
    "PlanDraft",
    "PlanValidationError",
    "Planner",
    "build_agent_graph",
    "make_data_fetcher_node",
    "make_input_verifier_node",
    "make_supervisor_node",
    "period_bounds",
    "route_from_supervisor",
    "validate_plan",
]
