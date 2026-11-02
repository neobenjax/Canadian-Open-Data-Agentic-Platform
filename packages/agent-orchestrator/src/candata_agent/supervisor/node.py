# pyright: reportMissingTypeStubs=false
"""Supervisor, Data Fetcher and input-verification nodes, plus the router between them (CAN-22).

Flow for one question:

    supervisor --plan--> data_fetcher / data_analyst (one step each, back to supervisor)
              --plan complete--> citation_verifier --> END

The Supervisor plans once per question (a new user message after a completed plan starts a new
plan) and otherwise only routes. Every executor marks its step COMPLETED or FAILED and moves
``active_step_id`` on; a FAILED step ends the run with the failure in the messages.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Final, Protocol

from langgraph.graph import END

from candata_agent.state import (
    AgentMessage,
    AgentState,
    MessageRole,
    PlanStep,
    QueryPlan,
    StepStatus,
    TokenBudget,
)
from candata_agent.supervisor.registry import (
    DATA_ANALYST,
    DATA_FETCHER,
    FetchStatCanArgs,
    FetchValetArgs,
    period_bounds,
)
from candata_agent.verifier import CitationVerifier, Claim, StatCanSource, ValetSource
from candata_mcp.citation import CitationEnvelope

SUPERVISOR: Final = "supervisor"
CITATION_VERIFIER: Final = "citation_verifier"
RUN_CITATIONS: Final = "run_citations"

Node = Callable[[AgentState], Awaitable[dict[str, Any]]]


class Planner(Protocol):
    async def plan(self, question: str) -> PlannerOutcome: ...


class PlannerOutcome(Protocol):
    @property
    def plan(self) -> QueryPlan | None: ...

    @property
    def declined_reason(self) -> str | None: ...

    @property
    def input_tokens(self) -> int: ...

    @property
    def output_tokens(self) -> int: ...


def make_supervisor_node(planner: Planner) -> Node:
    """Plan the latest user question when there is no plan in progress; otherwise do nothing."""

    async def supervisor(state: AgentState) -> dict[str, Any]:
        if state.plan is not None and not state.plan.completed and not _failed(state.plan):
            return {}
        question = _latest_question(state)
        if question is None:
            return {"messages": (_say("No question to plan: the thread has no user message."),)}
        if state.plan is not None and _planned_for(state, question):
            return {}  # this question already ran; nothing new to plan

        try:
            outcome = await planner.plan(question)
        except Exception as error:  # planner errors end the run with a visible message
            return {
                "plan": None,
                "verification": None,
                "messages": (_say(f"Planning failed: {type(error).__name__}: {error}"),),
            }

        budget = state.token_budget
        update: dict[str, Any] = {
            "token_budget": TokenBudget(
                max_budget=budget.max_budget,
                prompt_tokens_used=budget.prompt_tokens_used + outcome.input_tokens,
                completion_tokens_used=budget.completion_tokens_used + outcome.output_tokens,
            ),
            # A new question starts a new set of citations to verify, and drops the last report.
            "scratchpad": {**state.scratchpad, "planned_question": question, RUN_CITATIONS: []},
            "verification": None,
        }

        if outcome.plan is None:
            reason = outcome.declined_reason or "no plan"
            update["plan"] = None
            update["messages"] = (_say(f"Declined: {reason}"),)
            return update

        plan = outcome.plan
        steps = "\n".join(f"{s.step_id}. [{s.assigned_agent}] {s.description}" for s in plan.steps)
        update["plan"] = plan
        update["messages"] = (_say(f"Plan for: {plan.objective}\n{steps}"),)
        return update

    return supervisor


def route_from_supervisor(state: AgentState) -> str:
    """Pick the node for the active step, the verifier once the plan is done, or END."""
    plan = state.plan
    if plan is None or _failed(plan):
        return END
    if plan.completed:
        return CITATION_VERIFIER if state.scratchpad.get(RUN_CITATIONS) else END
    step = _active_step(plan)
    if step is None:
        return END
    if step.assigned_agent in (DATA_FETCHER, DATA_ANALYST):
        return step.assigned_agent
    return END


def make_data_fetcher_node(statcan: StatCanSource, valet: ValetSource) -> Node:
    """Run the active fetch step: load the series into its slot and record its citation."""

    async def data_fetcher(state: AgentState) -> dict[str, Any]:
        plan = state.plan
        step = _active_step(plan) if plan is not None else None
        if plan is None or step is None or step.assigned_agent != DATA_FETCHER:
            return {}

        try:
            if step.tool_name == "fetch_statcan_vector":
                args = FetchStatCanArgs.model_validate(step.tool_args)
                first, last = period_bounds(args.start, args.end)
                result = await statcan.get_data_by_reference_period(args.vector_id, first, last)
                rows = [
                    {
                        "date": o.ref_per,
                        "value": o.value,
                        "status_code": o.status_code,
                        "symbol_code": o.symbol_code,
                    }
                    for o in result.observations
                ]
                into, source = args.into, args.vector_id
                citation = result.citation() if rows else None
                unit = f" ({result.unit})" if result.unit else ""
                summary = f"{len(rows)} observations of {source}{unit}"
            elif step.tool_name == "fetch_valet_series":
                vargs = FetchValetArgs.model_validate(step.tool_args)
                first, last = period_bounds(vargs.start, vargs.end)
                found = await valet.get_observations(
                    vargs.series_id, start_date=first, end_date=last
                )
                rows = [{"date": o.date, "value": o.value} for o in found.observations]
                into, source = vargs.into, vargs.series_id
                citation = found.citation() if rows else None
                summary = f"{len(rows)} observations of {source}"
            else:
                raise ValueError(f"data_fetcher cannot run tool {step.tool_name!r}")
            if citation is None:
                raise ValueError(f"no observations for {source} between {first} and {last}")
        except Exception as error:
            message = f"Fetch failed on step {step.step_id}: {type(error).__name__}: {error}"
            return {
                "plan": _finish_step(plan, step, StepStatus.FAILED, message),
                "messages": (_say(message, name=DATA_FETCHER),),
            }

        return {
            "plan": _finish_step(plan, step, StepStatus.COMPLETED, summary),
            "scratchpad": {
                **state.scratchpad,
                into: rows,
                f"{into}_source": source,
                RUN_CITATIONS: [*state.scratchpad.get(RUN_CITATIONS, []), _label(citation)],
            },
            "citations": (citation,),
            "messages": (_say(f"Loaded {summary} into {into}.", name=DATA_FETCHER),),
        }

    return data_fetcher


def make_input_verifier_node(verifier: CitationVerifier) -> Node:
    """Verify every citation the run gathered against the official source before answering.

    Inputs are verified as citation-only claims (no value): the Analyst's figures are computed
    from exactly these series by SQL, so a verified input means a traceable result.
    """

    async def citation_verifier(state: AgentState) -> dict[str, Any]:
        wanted = set(state.scratchpad.get(RUN_CITATIONS, []))
        cited = [c for c in _unique(state.citations) if _label(c) in wanted]
        claims = [Claim(c, label=_label(c)) for c in cited]
        report = await verifier.verify(claims)
        verdict = "all citations verified" if report.passed else "VERIFICATION FAILED"
        lines = [f"{v.claim.label}: {v.code.value}" for v in report.verdicts]
        return {
            "verification": report.to_dict(),
            "messages": (_say(f"{verdict}\n" + "\n".join(lines), name=CITATION_VERIFIER),),
        }

    return citation_verifier


def _finish_step(plan: QueryPlan, step: PlanStep, status: StepStatus, summary: str) -> QueryPlan:
    steps = tuple(
        s.model_copy(update={"status": status, "result_summary": summary})
        if s.step_id == step.step_id
        else s
        for s in plan.steps
    )
    if status is StepStatus.FAILED:
        return plan.model_copy(update={"steps": steps})
    later = [s.step_id for s in steps if s.step_id > step.step_id]
    return plan.model_copy(
        update={
            "steps": steps,
            "active_step_id": later[0] if later else None,
            "completed": all(s.status is StepStatus.COMPLETED for s in steps),
        }
    )


def _active_step(plan: QueryPlan) -> PlanStep | None:
    return next((s for s in plan.steps if s.step_id == plan.active_step_id), None)


def _failed(plan: QueryPlan) -> bool:
    return any(s.status is StepStatus.FAILED for s in plan.steps)


def _latest_question(state: AgentState) -> str | None:
    for message in reversed(state.messages):
        if message.role is MessageRole.USER and message.content.strip():
            return message.content.strip()
    return None


def _planned_for(state: AgentState, question: str) -> bool:
    return state.scratchpad.get("planned_question") == question


def _unique(citations: tuple[CitationEnvelope, ...]) -> list[CitationEnvelope]:
    seen: dict[tuple[str, str, str], CitationEnvelope] = {}
    for c in citations:
        seen[(c.core.table_id, c.core.vector_id, c.core.reference_period)] = c
    return list(seen.values())


def _label(citation: CitationEnvelope) -> str:
    core = citation.core
    return f"{core.table_id} {core.vector_id} {core.reference_period}"


def _say(content: str, *, name: str = SUPERVISOR) -> AgentMessage:
    return AgentMessage(role=MessageRole.ASSISTANT, content=content, name=name)
