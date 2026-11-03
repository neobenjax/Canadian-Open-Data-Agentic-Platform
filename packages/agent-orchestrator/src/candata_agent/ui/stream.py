# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
"""Stream one question through the agent graph as UI events (CAN-32).

``stream_question`` drives ``astream_events(version="v2")`` and turns the node start and end
events into a small, typed sequence the UI can render as it arrives:

    NodeStarted(supervisor) -> NodeFinished(supervisor, plan, messages) -> NodeStarted(...)
    ... -> RunFinished(result)

Everything shown for a run comes from that run's node outputs, never from the thread's final
state, so a second question on the same thread doesn't show the first question's series.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, cast

from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from pydantic import ValidationError

from candata_agent.state import (
    AgentMessage,
    MessageRole,
    PlanStep,
    QueryPlan,
    SQLArtifact,
    StepStatus,
)
from candata_agent.supervisor.node import CITATION_VERIFIER, SUPERVISOR
from candata_agent.supervisor.registry import (
    DATA_ANALYST,
    DATA_FETCHER,
    FetchStatCanArgs,
    FetchValetArgs,
)
from candata_mcp.citation import CitationEnvelope

NODES: Final = (SUPERVISOR, DATA_FETCHER, DATA_ANALYST, CITATION_VERIFIER)
NODE_LABELS: Final = {
    SUPERVISOR: "Supervisor",
    DATA_FETCHER: "Data Fetcher",
    DATA_ANALYST: "Data Analyst",
    CITATION_VERIFIER: "Citation Verifier",
}
_FETCH_ARGS: Final = {
    "fetch_statcan_vector": FetchStatCanArgs,
    "fetch_valet_series": FetchValetArgs,
}


@dataclass(frozen=True, slots=True)
class FetchedSeries:
    """One official series a fetch step loaded, with its quality flags kept per observation."""

    slot: str
    source: str
    unit: str | None
    rows: tuple[dict[str, Any], ...]
    label: str = ""

    @property
    def name(self) -> str:
        """The plan step's description with the series ID, or the ID alone."""
        return f"{self.label} ({self.source})" if self.label else self.source


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    recipe: str
    artifact: SQLArtifact
    label: str = ""

    @property
    def name(self) -> str:
        source = self.artifact.source_series_id
        return f"{self.label} ({source})" if self.label else source


@dataclass(slots=True)
class RunResult:
    """What one question produced, gathered from its own node outputs."""

    question: str
    plan: QueryPlan | None = None
    messages: list[AgentMessage] = field(default_factory=list[AgentMessage])
    series: list[FetchedSeries] = field(default_factory=list[FetchedSeries])
    analyses: list[AnalysisResult] = field(default_factory=list[AnalysisResult])
    citations: list[CitationEnvelope] = field(default_factory=list[CitationEnvelope])
    verification: dict[str, Any] | None = None

    @property
    def failed_step(self) -> str | None:
        """The summary of the step that failed, if one did."""
        if self.plan is None:
            return None
        failed = [s for s in self.plan.steps if s.status is StepStatus.FAILED]
        return failed[0].result_summary if failed else None

    @property
    def verified(self) -> bool:
        return bool(self.verification and self.verification.get("passed"))


@dataclass(frozen=True, slots=True)
class NodeStarted:
    node: str


@dataclass(frozen=True, slots=True)
class NodeFinished:
    node: str
    messages: tuple[AgentMessage, ...]
    plan: QueryPlan | None


@dataclass(frozen=True, slots=True)
class RunFinished:
    result: RunResult


RunEvent = NodeStarted | NodeFinished | RunFinished


async def stream_question(
    app: CompiledStateGraph[Any, Any, Any, Any],
    question: str,
    *,
    thread_id: str,
    session_id: str,
) -> AsyncIterator[RunEvent]:
    """Ask ``question`` on ``thread_id`` and yield progress events, ending with ``RunFinished``."""
    asked = AgentMessage(role=MessageRole.USER, content=question)
    graph_input = {"session_id": session_id, "thread_id": thread_id, "messages": (asked,)}
    config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
    result = RunResult(question=question)
    seen: set[str] = {asked.id}
    done_steps: set[int] = set()

    async for raw in app.astream_events(graph_input, config, version="v2"):
        event = cast(dict[str, Any], raw)
        node = str(event.get("name"))
        metadata = cast(dict[str, Any], event.get("metadata") or {})
        if node not in NODES or metadata.get("langgraph_node") != node:
            continue  # the graph itself, the router, or anything nested inside a node
        if event["event"] == "on_chain_start":
            yield NodeStarted(node)
        elif event["event"] == "on_chain_end":
            output: object = cast(dict[str, Any], event.get("data") or {}).get("output")
            update = cast(dict[str, Any], output) if isinstance(output, dict) else {}
            new = _new_messages(update.get("messages", ()), seen)
            result.messages.extend(new)
            if "plan" in update:
                result.plan = update["plan"]
            _collect(node, update, result, done_steps)
            yield NodeFinished(node, tuple(new), result.plan)

    yield RunFinished(result)


def _new_messages(messages: Sequence[AgentMessage], seen: set[str]) -> list[AgentMessage]:
    """Messages not shown yet; the Data Analyst returns the whole history, not a delta."""
    new = [m for m in messages if m.id not in seen and m.role is not MessageRole.USER]
    seen.update(m.id for m in messages)
    return new


def _collect(node: str, update: dict[str, Any], result: RunResult, done: set[int]) -> None:
    plan = update.get("plan")
    if node == SUPERVISOR and isinstance(plan, QueryPlan):
        done.clear()  # a new plan for this question
    if node == DATA_FETCHER and isinstance(plan, QueryPlan):
        scratchpad: dict[str, Any] = update.get("scratchpad", {})
        for step in _newly_completed(plan, done):
            spec = _FETCH_ARGS.get(step.tool_name or "")
            if spec is None:
                continue
            try:
                into: str = spec.model_validate(step.tool_args).into
            except ValidationError:
                continue
            rows: object = scratchpad.get(into)
            if isinstance(rows, list):
                result.series.append(
                    FetchedSeries(
                        slot=into,
                        source=str(scratchpad.get(f"{into}_source", into)),
                        unit=scratchpad.get(f"{into}_unit"),
                        rows=tuple(_as_rows(cast(list[object], rows))),
                        label=step.description.strip(),
                    )
                )
        result.citations.extend(update.get("citations", ()))
    elif node == DATA_ANALYST and isinstance(plan, QueryPlan):
        artifacts: Sequence[SQLArtifact] = update.get("sql_artifacts", ())
        finished = _newly_completed(plan, done)
        if finished and artifacts:
            recipe = str(update.get("scratchpad", {}).get("last_analysis_recipe", "custom_sql"))
            label = finished[0].description.strip()
            result.analyses.append(AnalysisResult(recipe, artifacts[-1], label))
    elif node == CITATION_VERIFIER:
        result.verification = update.get("verification")


def _newly_completed(plan: QueryPlan, done: set[int]) -> list[PlanStep]:
    fresh = [s for s in plan.steps if s.status is StepStatus.COMPLETED and s.step_id not in done]
    done.update(s.step_id for s in fresh)
    return fresh


def _as_rows(rows: list[object]) -> list[dict[str, Any]]:
    return [cast(dict[str, Any], r) for r in rows if isinstance(r, dict)]
