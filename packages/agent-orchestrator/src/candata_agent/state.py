"""Typed Pydantic v2 AgentState schema for LangGraph 0.2+ multi-agent orchestration.

Provides state channels for multi-agent messages, supervisor query plans, exact DuckDB
SQL mathematical artifacts, Two-Tier Citation Envelopes, OpenTelemetry distributed trace
lineage, and Human-in-the-Loop interruption payloads.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from candata_mcp.citation import CitationEnvelope


class MessageRole(StrEnum):
    """Roles for multi-agent conversation messages."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class AgentMessage(BaseModel):
    """Structured message exchanged between supervisor, analyst, and verifier agents."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: f"msg_{uuid.uuid4().hex[:12]}")
    role: MessageRole
    content: str
    name: str | None = None
    tool_calls: tuple[dict[str, Any], ...] = Field(default_factory=tuple)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


def add_messages(
    existing: Sequence[AgentMessage],
    incoming: Sequence[AgentMessage] | AgentMessage,
) -> tuple[AgentMessage, ...]:
    """Append-only message channel reducer with ID-based deduplication and replacement."""
    indexed: dict[str, AgentMessage] = {m.id: m for m in existing}
    new_items = (incoming,) if isinstance(incoming, AgentMessage) else incoming
    for item in new_items:
        indexed[item.id] = item
    return tuple(indexed.values())


class StepStatus(StrEnum):
    """Lifecycle status for a supervisor plan step."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class PlanStep(BaseModel):
    """Deterministic step created by the Query Planner node."""

    model_config = ConfigDict(frozen=True)

    step_id: int
    description: str
    assigned_agent: str
    status: StepStatus = StepStatus.PENDING
    tool_name: str | None = None
    tool_args: dict[str, Any] = Field(default_factory=dict)
    result_summary: str | None = None


class QueryPlan(BaseModel):
    """Supervisor decomposition plan for multi-agent execution."""

    model_config = ConfigDict(frozen=True)

    plan_id: str = Field(default_factory=lambda: f"plan_{uuid.uuid4().hex[:8]}")
    objective: str
    steps: tuple[PlanStep, ...] = Field(default_factory=tuple)
    active_step_id: int | None = None
    completed: bool = False


class SQLArtifact(BaseModel):
    """Deterministic SQL calculation output produced by the Data Analyst agent."""

    model_config = ConfigDict(frozen=True)

    artifact_id: str = Field(default_factory=lambda: f"sql_{uuid.uuid4().hex[:8]}")
    source_series_id: str
    sql_query: str
    row_count: int
    rows: tuple[dict[str, Any], ...] = Field(default_factory=tuple)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def merge_citations(
    existing: Sequence[CitationEnvelope],
    incoming: Sequence[CitationEnvelope] | CitationEnvelope,
) -> tuple[CitationEnvelope, ...]:
    """Deterministic deduplication reducer matching on Core Verification Tuple.

    Prevents duplicate citations when multiple agents cite the same official table,
    vector ID, and reference period.
    """
    merged: dict[tuple[str, str, str], CitationEnvelope] = {}
    for cit in existing:
        key = (cit.core.table_id, cit.core.vector_id, cit.core.reference_period)
        merged[key] = cit
    inc_list = (incoming,) if isinstance(incoming, CitationEnvelope) else incoming
    for cit in inc_list:
        key = (cit.core.table_id, cit.core.vector_id, cit.core.reference_period)
        merged[key] = cit
    return tuple(merged.values())


class InterruptType(StrEnum):
    """Categorization for Human-in-the-Loop interruptions."""

    AMBIGUOUS_MEMBER = "ambiguous_member"
    CONFIDENTIALITY_SUPPRESSED = "confidentiality_suppressed"
    POLICY_EXCEPTION = "policy_exception"
    USER_CONFIRMATION = "user_confirmation"


class HITLInterrupt(BaseModel):
    """Human-in-the-Loop breakpoint payload when statistical ambiguities arise."""

    model_config = ConfigDict(frozen=True)

    interrupt_id: str = Field(default_factory=lambda: f"hitl_{uuid.uuid4().hex[:8]}")
    interrupt_type: InterruptType
    reason: str
    details: dict[str, Any] = Field(default_factory=dict)
    suggested_options: tuple[str, ...] = Field(default_factory=tuple)
    resolved: bool = False
    resolution: str | None = None
    resolved_at: datetime | None = None


class TraceContext(BaseModel):
    """Distributed tracing context carrier matching W3C TraceContext standards."""

    model_config = ConfigDict(frozen=True)

    traceparent: str | None = None
    tracestate: str | None = None
    span_id: str | None = None
    parent_span_id: str | None = None


class TokenBudget(BaseModel):
    """Token consumption and context-window monitoring per sub-agent run."""

    model_config = ConfigDict(frozen=True)

    max_budget: int = 128000
    prompt_tokens_used: int = 0
    completion_tokens_used: int = 0
    total_tokens_used: int = 0

    @model_validator(mode="after")
    def validate_or_compute_total_tokens(self) -> Self:
        """Ensure total_tokens_used remains synchronized with prompt and completion counts."""
        computed = self.prompt_tokens_used + self.completion_tokens_used
        if self.total_tokens_used == 0 and computed > 0:
            object.__setattr__(self, "total_tokens_used", computed)
        elif computed > 0 and self.total_tokens_used != computed:
            object.__setattr__(self, "total_tokens_used", computed)
        return self

    @property
    def remaining_tokens(self) -> int:
        return max(0, self.max_budget - self.total_tokens_used)


class AgentState(BaseModel):
    """Top-level immutable state container for LangGraph multi-agent execution."""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    schema_version: int = Field(
        default=1,
        description="Schema version number for checkpoint migration resilience",
    )
    session_id: str
    thread_id: str
    run_id: str = Field(default_factory=lambda: f"run_{uuid.uuid4().hex[:8]}")

    # Conversation history with append-only reducer
    messages: Annotated[tuple[AgentMessage, ...], add_messages] = Field(default_factory=tuple)

    # Supervisor query planning
    plan: QueryPlan | None = None

    # Analytical SQL executions
    sql_artifacts: tuple[SQLArtifact, ...] = Field(default_factory=tuple)

    # Official citations with deduplication reducer
    citations: Annotated[tuple[CitationEnvelope, ...], merge_citations] = Field(
        default_factory=tuple
    )

    # Active HITL breakpoint
    active_interrupt: HITLInterrupt | None = None

    # Observability & token tracking
    trace_context: TraceContext = Field(default_factory=TraceContext)
    token_budget: TokenBudget = Field(default_factory=TokenBudget)

    # Working memory
    scratchpad: dict[str, Any] = Field(default_factory=dict)
