"""Canadian Open Data Agentic Platform — LangGraph Multi-Agent Orchestrator."""

from candata_agent.checkpoint import AsyncSqliteSaver
from candata_agent.pricing import TokenPricing
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

try:
    from candata_agent.tracing import (
        current_trace_context,
        setup_tracing,
        traced_node,
        traced_run,
    )
except ModuleNotFoundError as error:
    # Only the optional `tracing` extra may be missing; any other missing module is a real bug.
    if not (error.name or "").startswith("opentelemetry"):
        raise
    from candata_agent._tracing_off import (  # type: ignore[assignment]
        current_trace_context,
        setup_tracing,
        traced_node,
        traced_run,
    )

__all__ = [
    "AgentMessage",
    "AgentState",
    "AsyncSqliteSaver",
    "HITLInterrupt",
    "InterruptType",
    "MessageRole",
    "PlanStep",
    "QueryPlan",
    "SQLArtifact",
    "StepStatus",
    "TokenBudget",
    "TokenPricing",
    "TraceContext",
    "add_messages",
    "current_trace_context",
    "merge_citations",
    "setup_tracing",
    "traced_node",
    "traced_run",
]
