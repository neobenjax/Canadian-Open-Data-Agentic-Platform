# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
"""Run benchmark questions through the agent graph and record what it answered (CAN-41).

Each question gets its own thread, so one question's citations never leak into the next.
Runs are written as JSONL (one ``AgentRun`` per line) so they can be graded offline later,
for example in CI, without calling the agent or the public APIs again.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from langgraph.graph.state import CompiledStateGraph

from candata_agent.evals.ground_truth import GroundTruthQuestion, envelope_from_dict
from candata_agent.state import AgentMessage, MessageRole, QueryPlan, StepStatus
from candata_mcp.citation import CitationEnvelope


@dataclass(frozen=True, slots=True)
class AgentRun:
    """What the agent did for one question, as the graders need it."""

    question_id: str
    question: str
    answer: str
    citations: tuple[CitationEnvelope, ...] = ()
    produced_figures: bool = False
    verified: bool | None = None
    declined: str | None = None
    failed_step: str | None = None
    error: str | None = None
    planner: str = ""
    started_at: str = ""
    seconds: float = 0.0
    tool_calls: tuple[str, ...] = field(default_factory=tuple)

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> AgentRun:
        citations = tuple(envelope_from_dict(c) for c in raw.get("citations", ()))
        return cls(
            question_id=str(raw["question_id"]),
            question=str(raw["question"]),
            answer=str(raw.get("answer", "")),
            citations=citations,
            produced_figures=bool(raw.get("produced_figures", False)),
            verified=raw.get("verified"),
            declined=raw.get("declined"),
            failed_step=raw.get("failed_step"),
            error=raw.get("error"),
            planner=str(raw.get("planner", "")),
            started_at=str(raw.get("started_at", "")),
            seconds=float(raw.get("seconds", 0.0)),
            tool_calls=tuple(raw.get("tool_calls", ())),
        )


async def run_question(
    app: CompiledStateGraph[Any, Any, Any, Any],
    question: GroundTruthQuestion,
    *,
    planner: str,
    run_label: str,
) -> AgentRun:
    """Ask one question on a fresh thread and capture the final state.

    The thread ID is unique per call: reusing a thread would merge the previous run's
    citations into this one (the ``citations`` channel accumulates).
    """
    thread = f"eval_{run_label}_{question.id}_{uuid.uuid4().hex[:8]}"
    asked = AgentMessage(role=MessageRole.USER, content=question.question)
    started = datetime.now(UTC)
    clock = time.perf_counter()
    base = AgentRun(
        question_id=question.id,
        question=question.question,
        answer="",
        planner=planner,
        started_at=started.isoformat(timespec="seconds"),
    )
    try:
        state = cast(
            dict[str, Any],
            await app.ainvoke(
                {"session_id": run_label, "thread_id": thread, "messages": (asked,)},
                {"configurable": {"thread_id": thread}},
            ),
        )
    except Exception as error:  # a crash is a result to grade, not a reason to stop the suite
        return replace(
            base,
            error=f"{type(error).__name__}: {error}",
            seconds=round(time.perf_counter() - clock, 2),
        )
    return _from_state(state, base, round(time.perf_counter() - clock, 2))


def _from_state(state: dict[str, Any], base: AgentRun, seconds: float) -> AgentRun:
    messages = [
        m for m in cast(Sequence[AgentMessage], state.get("messages", ()))
        if m.role is not MessageRole.USER
    ]  # fmt: skip
    plan = state.get("plan")
    failed = declined = None
    calls: tuple[str, ...] = ()
    if isinstance(plan, QueryPlan):
        calls = tuple(s.tool_name or "" for s in plan.steps)
        failed = next((s.result_summary for s in plan.steps if s.status is StepStatus.FAILED), None)
    for message in messages:
        if message.content.startswith(("Declined:", "Planning failed")):
            declined = message.content
    verification = cast(dict[str, Any] | None, state.get("verification"))
    return replace(
        base,
        answer="\n\n".join(m.content for m in messages),
        citations=tuple(cast(Sequence[CitationEnvelope], state.get("citations", ()))),
        produced_figures=bool(state.get("sql_artifacts")),
        verified=None if verification is None else bool(verification.get("passed")),
        declined=declined,
        failed_step=failed,
        seconds=seconds,
        tool_calls=calls,
    )


async def run_benchmark(
    app: CompiledStateGraph[Any, Any, Any, Any],
    questions: Iterable[GroundTruthQuestion],
    *,
    planner: str,
    run_label: str | None = None,
) -> list[AgentRun]:
    label = run_label or datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    return [await run_question(app, q, planner=planner, run_label=label) for q in questions]


def write_runs(runs: Iterable[AgentRun], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = (json.dumps(r.to_json(), ensure_ascii=False) for r in runs)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def read_runs(path: Path) -> list[AgentRun]:
    rows = (line for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    return [AgentRun.from_json(cast(dict[str, Any], json.loads(line))) for line in rows]
