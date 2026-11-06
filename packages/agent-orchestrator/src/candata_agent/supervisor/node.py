# pyright: reportMissingTypeStubs=false
"""Supervisor, Data Fetcher and input-verification nodes, plus the router between them (CAN-22).

Flow for one question:

    supervisor --plan--> data_fetcher / data_analyst (one step each, back to supervisor)
              --plan complete--> citation_verifier --> END
              --ambiguous term--> human_clarification --interrupt(), resumed--> supervisor

The Supervisor plans once per user message (keyed on the message ID, so asking the same text
again plans again) and otherwise only routes. Before planning it screens the question for text
addressed to the agent (CAN-43) and declines without a model call when it finds any; the
planner's tool-call audit trail for the question is kept under ``PLANNER_AUDIT``.

When the planner asks which member a term means (CAN-33), the Supervisor stores the request as
``active_interrupt`` and routes to ``human_clarification``. That node calls LangGraph's
``interrupt()``, so the run pauses until the caller resumes the thread with
``Command(resume=<member ID or name>)``. The Supervisor then plans again with the user's
choice. Planning happens in the Supervisor and the pause in its own node, so resuming never
repeats the model call. A new question asked instead of answering replaces the pending one.

Every executor
marks its step COMPLETED or FAILED and moves ``active_step_id`` on; a FAILED step ends the run
with the failure in the messages.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Final, Protocol, cast

from langgraph.graph import END
from langgraph.types import interrupt

from candata_agent.state import (
    AgentMessage,
    AgentState,
    HITLInterrupt,
    InterruptType,
    MessageRole,
    PlanStep,
    QueryPlan,
    StepStatus,
    TokenBudget,
)
from candata_agent.supervisor.audit import ToolCallRecord, record
from candata_agent.supervisor.clarification import (
    MAX_CLARIFICATIONS,
    Clarification,
    Resolution,
    resolutions_from_json,
)
from candata_agent.supervisor.guardrails import screen_question
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
PLANNED_MESSAGE: Final = "planned_message_id"
PLANNER_AUDIT: Final = "planner_audit"
HUMAN_CLARIFICATION: Final = "human_clarification"
CLARIFICATIONS: Final = "clarifications"  # the user's choices for the current question
CANCEL_WORDS: Final = frozenset({"cancel", "stop", "none of these"})

Node = Callable[[AgentState], Awaitable[dict[str, Any]]]


class Planner(Protocol):
    async def plan(
        self, question: str, *, resolved: Sequence[Resolution] = ()
    ) -> PlannerOutcome: ...


class PlannerOutcome(Protocol):
    @property
    def plan(self) -> QueryPlan | None: ...

    @property
    def declined_reason(self) -> str | None: ...

    @property
    def input_tokens(self) -> int: ...

    @property
    def output_tokens(self) -> int: ...

    @property
    def cache_creation_input_tokens(self) -> int: ...

    @property
    def cache_read_input_tokens(self) -> int: ...


def make_supervisor_node(planner: Planner) -> Node:
    """Plan the latest user question when there is no plan in progress; otherwise do nothing."""

    async def supervisor(state: AgentState) -> dict[str, Any]:
        if state.plan is not None and not state.plan.completed and not _failed(state.plan):
            return {}
        asked = _latest_user_message(state)
        if asked is None:
            return {"messages": (_say("No question to plan: the thread has no user message."),)}
        pending = state.active_interrupt
        same_question = state.scratchpad.get(PLANNED_MESSAGE) == asked.id
        if pending is not None and not pending.resolved and same_question:
            return {}  # still waiting for the user; the router sends this to the pause node
        resuming = pending is not None and pending.resolved and same_question
        if same_question and not resuming:
            return {}  # this message was already planned; only route
        question = asked.content.strip()

        earlier_audit: list[dict[str, Any]] = []
        if resuming:
            assert pending is not None
            raw = cast(Sequence[Mapping[str, Any]], state.scratchpad.get(CLARIFICATIONS, []))
            resolutions = resolutions_from_json(raw)
            earlier_audit = list(state.scratchpad.get(PLANNER_AUDIT, []))
            fresh: dict[str, Any] = {**state.scratchpad, RUN_CITATIONS: []}
            if pending.resolution is None:  # the user cancelled
                return {
                    "active_interrupt": None,
                    "plan": None,
                    "scratchpad": fresh,
                    "messages": (_say("Declined: the clarification was cancelled."),),
                }
        else:  # a new question, which also replaces a clarification left unanswered
            resolutions = ()
            fresh = {
                **state.scratchpad,
                PLANNED_MESSAGE: asked.id,
                RUN_CITATIONS: [],
                CLARIFICATIONS: [],
            }
            screening = screen_question(question)
            if not screening.allowed:
                blocked = record(
                    0, "question_screen", question, "blocked", ", ".join(screening.reasons)
                )
                return {
                    "plan": None,
                    "verification": None,
                    "active_interrupt": None,
                    "scratchpad": {**fresh, PLANNER_AUDIT: [blocked.to_json()]},
                    "messages": (_say(f"Declined: {screening.message}"),),
                }

        try:
            outcome = await (
                planner.plan(question, resolved=resolutions)
                if resolutions
                else planner.plan(question)
            )
        except Exception as error:  # planner errors end the run with a visible message
            trail: tuple[ToolCallRecord, ...] = getattr(error, "audit", ())
            return {
                "plan": None,
                "verification": None,
                "active_interrupt": None,
                "scratchpad": {
                    **fresh,
                    PLANNER_AUDIT: earlier_audit + [r.to_json() for r in trail],
                },
                "messages": (_say(f"Planning failed: {type(error).__name__}: {error}"),),
            }

        audit: tuple[ToolCallRecord, ...] = getattr(outcome, "audit", ())
        budget = state.token_budget
        cache_creation = getattr(outcome, "cache_creation_input_tokens", 0) or 0
        cache_read = getattr(outcome, "cache_read_input_tokens", 0) or 0
        update: dict[str, Any] = {
            "token_budget": TokenBudget(
                max_budget=budget.max_budget,
                prompt_tokens_used=budget.prompt_tokens_used + outcome.input_tokens,
                completion_tokens_used=budget.completion_tokens_used + outcome.output_tokens,
                cache_creation_tokens_used=budget.cache_creation_tokens_used + cache_creation,
                cache_read_tokens_used=budget.cache_read_tokens_used + cache_read,
            ),
            # A new question starts a new set of citations to verify, and drops the last report.
            "scratchpad": {**fresh, PLANNER_AUDIT: earlier_audit + [r.to_json() for r in audit]},
            "verification": None,
            "active_interrupt": None,
        }

        clarification: Clarification | None = getattr(outcome, "clarification", None)
        if clarification is not None:
            update["plan"] = None
            if len(resolutions) >= MAX_CLARIFICATIONS:
                update["messages"] = (
                    _say(
                        f"Declined: the question is still ambiguous after {MAX_CLARIFICATIONS} "
                        "clarifications. Ask it again, naming the place or series exactly."
                    ),
                )
                return update
            update["active_interrupt"] = HITLInterrupt(
                interrupt_type=InterruptType.AMBIGUOUS_MEMBER,
                reason=clarification.question,
                details=clarification.to_json(),
                suggested_options=tuple(
                    f"{c.member_id}: {c.name}" for c in clarification.candidates
                ),
            )
            options = "\n".join(f"- {c.member_id}: {c.name}" for c in clarification.candidates)
            update["messages"] = (
                _say(f"Needs clarification: {clarification.question}\n{options}"),
            )
            return update

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


def make_clarification_node() -> Node:
    """Pause the run with ``interrupt()`` until the user picks one of the offered members.

    The resume value may be a member ID (int or text), a member's exact name, a mapping with
    ``member_id`` or ``name``, or "cancel". Anything else asks again, saying why.
    """

    async def human_clarification(state: AgentState) -> dict[str, Any]:
        pending = state.active_interrupt
        if pending is None or pending.resolved:
            return {}
        clarification = Clarification.from_json(pending.details)
        payload: dict[str, Any] = {
            "interrupt_id": pending.interrupt_id,
            "type": pending.interrupt_type.value,
            "question": clarification.question,
            "term": clarification.term,
            "table_id": clarification.table_id,
            "dimension": clarification.dimension,
            "options": [
                {"member_id": c.member_id, "name": c.name} for c in clarification.candidates
            ],
        }
        answer: object = interrupt(payload)
        while True:
            if isinstance(answer, str) and answer.strip().casefold() in CANCEL_WORDS:
                choice = None
                break
            choice = clarification.choose(answer)
            if choice is not None:
                break
            answer = interrupt(
                {
                    **payload,
                    "error": "That is not one of the options. Answer with a member ID or name "
                    "from the list, or 'cancel'.",
                }
            )

        resolved_at = datetime.now(UTC)
        if choice is None:
            return {
                "active_interrupt": pending.model_copy(
                    update={"resolved": True, "resolution": None, "resolved_at": resolved_at}
                ),
                "messages": (_say("Clarification cancelled."),),
            }
        resolution = Resolution(
            term=clarification.term,
            table_id=clarification.table_id,
            dimension_position=clarification.dimension_position,
            member_id=choice.member_id,
            name=choice.name,
        )
        chosen = [*state.scratchpad.get(CLARIFICATIONS, []), resolution.to_json()]
        return {
            "active_interrupt": pending.model_copy(
                update={
                    "resolved": True,
                    "resolution": str(choice.member_id),
                    "resolved_at": resolved_at,
                }
            ),
            "scratchpad": {**state.scratchpad, CLARIFICATIONS: chosen},
            "messages": (
                _say(
                    f'Clarified: "{clarification.term}" means {choice.name} '
                    f"(member {choice.member_id})."
                ),
            ),
        }

    return human_clarification


def route_from_supervisor(state: AgentState) -> str:
    """Pick the node for the active step, the verifier once the plan is done, or END."""
    pending = state.active_interrupt
    if pending is not None and not pending.resolved:
        return HUMAN_CLARIFICATION
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
                into, source, unit_name = args.into, args.vector_id, result.unit
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
                into, source, unit_name = vargs.into, vargs.series_id, found.series.unit
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
                f"{into}_unit": unit_name,
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


def _latest_user_message(state: AgentState) -> AgentMessage | None:
    for message in reversed(state.messages):
        if message.role is MessageRole.USER and message.content.strip():
            return message
    return None


def _unique(citations: tuple[CitationEnvelope, ...]) -> list[CitationEnvelope]:
    seen: dict[tuple[str, str, str | None], CitationEnvelope] = {}
    for c in citations:
        seen[(c.core.table_id, c.core.vector_id, c.core.reference_period)] = c
    return list(seen.values())


def _label(citation: CitationEnvelope) -> str:
    core = citation.core
    return f"{core.table_id} {core.vector_id} {core.reference_period}"


def _say(content: str, *, name: str = SUPERVISOR) -> AgentMessage:
    return AgentMessage(role=MessageRole.ASSISTANT, content=content, name=name)
