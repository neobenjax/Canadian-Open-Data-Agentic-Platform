"""CanData agent UI (CAN-32): ask a question, watch the agents work, see the official series.

Two-pane workbench: the conversation and the agents' progress on the left, the evidence for one
question in tabs on the right (Result, Official series, SQL, Sources, Quality flags).

Run from the repo root:

    uv sync --extra ui --extra agent
    uv run streamlit run apps/agent-ui/app.py

Without ANTHROPIC_API_KEY the page runs in demo mode (three benchmark questions with fixed
plans, executed against live StatCan and Bank of Canada data).
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
for src in ("packages/candata-mcp/src", "packages/agent-orchestrator/src"):
    if str(ROOT / src) not in sys.path:
        sys.path.insert(0, str(ROOT / src))

from candata_agent.ui import (  # noqa: E402
    NODE_LABELS,
    AnalysisResult,
    NodeFinished,
    NodeStarted,
    RunFinished,
    RunResult,
    stream_question,
)
from candata_agent.ui.charts import flag_text, result_figure, series_figure  # noqa: E402
from candata_agent.ui.session import (  # noqa: E402
    DEFAULT_DB,
    DEMO_QUESTIONS,
    live_planner_available,
    open_agent,
)

st.set_page_config(page_title="CanData Agent", page_icon="🍁", layout="wide")

STATE_KEYS = ("thread_id", "session_id", "turns", "timings")


def _state() -> Any:
    if "thread_id" not in st.session_state:
        st.session_state.thread_id = f"ui_{uuid.uuid4().hex[:10]}"
        st.session_state.session_id = f"session_{uuid.uuid4().hex[:8]}"
        st.session_state.turns = []  # one RunResult per question
        st.session_state.timings = []  # per turn: seconds each agent took, in the order they ran
    return st.session_state


def _sidebar(demo: bool) -> str | None:
    with st.sidebar:
        st.header("CanData Agent")

        # Optional user-provided API key for cloud demo visitors
        custom_key = st.text_input(
            "Anthropic API Key (optional)",
            value=st.session_state.get("custom_api_key", ""),
            type="password",
            help=(
                "Bring your own API key to plan custom queries with Claude. "
                "Stored only in this browser session."
            ),
        )
        if custom_key != st.session_state.get("custom_api_key", ""):
            st.session_state.custom_api_key = custom_key
            if custom_key:
                os.environ["ANTHROPIC_API_KEY"] = custom_key
            elif "ANTHROPIC_API_KEY" in os.environ and not os.environ.get("CANDATA_SYSTEM_KEY"):
                os.environ.pop("ANTHROPIC_API_KEY", None)
            st.rerun()

        if demo and not st.session_state.get("custom_api_key"):
            st.info(
                "**Demo mode.** No `ANTHROPIC_API_KEY`, so only the example questions are "
                "planned. Their data is fetched live from StatCan and the Bank of Canada."
            )
        else:
            st.success("**Live mode.** Claude plans each question from StatCan discovery.")
        st.caption(f"Conversation `{st.session_state.thread_id}`")
        if st.button("New conversation", use_container_width=True):
            for key in STATE_KEYS:
                st.session_state.pop(key, None)
            st.rerun()
        st.subheader("Example questions")
        for index, item in enumerate(DEMO_QUESTIONS):
            if st.button(item.question, key=f"example_{index}", use_container_width=True):
                return item.question
    return None


async def _ask(
    question: str, progress: Any, resume: object = None
) -> tuple[RunResult, dict[str, float]]:
    """Run one question; return its result and how long each agent took."""
    extra: dict[str, object] = {} if resume is None else {"resume": resume}
    started: dict[str, float] = {}
    took: dict[str, float] = {}
    async with open_agent(db_path=ROOT / DEFAULT_DB) as (app, _):
        async for event in stream_question(
            app,
            question,
            thread_id=st.session_state.thread_id,
            session_id=st.session_state.session_id,
            **extra,  # type: ignore[arg-type]
        ):
            if isinstance(event, NodeStarted):
                started[event.node] = time.monotonic()
                progress.update(label=f"{NODE_LABELS[event.node]} working…")
            elif isinstance(event, NodeFinished):
                if event.node in started:
                    took[event.node] = took.get(event.node, 0.0) + (
                        time.monotonic() - started.pop(event.node)
                    )
                for message in event.messages:
                    progress.markdown(f"**{NODE_LABELS.get(message.name or '', 'Agent')}**")
                    progress.markdown(message.content)
            elif isinstance(event, RunFinished):
                return event.result, took
    raise RuntimeError("the graph stream ended without a result")


def _verdicts(result: RunResult) -> list[dict[str, Any]]:
    return list((result.verification or {}).get("verdicts", []))


def _claim_core(verdict: dict[str, Any]) -> dict[str, Any]:
    return verdict["claim"]["citation"]["core"]


def _badge(analysis: AnalysisResult, verdicts: list[dict[str, Any]]) -> str:
    """Whether the series a figure was computed from passed verification."""
    source = analysis.artifact.source_series_id
    mine = [v for v in verdicts if _claim_core(v)["vector_id"] == source]
    if not mine:
        return "⚪ not checked"
    if all(v["passed"] for v in mine):
        return "✅ verified"
    return (
        "⚠️ not verified ("
        + ", ".join(sorted({str(v["code"]) for v in mine if not v["passed"]}))
        + ")"
    )


def _flagged(result: RunResult) -> list[tuple[str, str, str]]:
    """(series, period, reason) for every observation that carries a quality flag."""
    return [
        (item.name, str(row.get("date", "")), why)
        for item in result.series
        for row in item.rows
        if (why := flag_text(row))
    ]


def _agents(took: dict[str, float]) -> None:
    for node, seconds in took.items():
        st.markdown(f"✅ **{NODE_LABELS.get(node, node)}** · {seconds:.1f} s")


def _clarification(result: RunResult, index: int) -> None:
    pending = result.clarification
    if pending is None:
        return
    st.info(pending.question, icon="❓")
    if pending.error:
        st.warning(pending.error)
    if index == len(st.session_state.turns):  # only the latest turn can be answered
        labels = {f"{name} (member {member_id})": member_id for member_id, name in pending.options}
        picked = st.radio("Which one do you mean?", list(labels), key=f"pick_{index}")
        left, right = st.columns(2)
        if left.button("Continue", key=f"go_{index}", type="primary"):
            st.session_state.resume = labels[picked]
            st.rerun()
        if right.button("Cancel", key=f"cancel_{index}"):
            st.session_state.resume = "cancel"
            st.rerun()


def _summary(result: RunResult, took: dict[str, float], index: int) -> None:
    """The left-pane part of a turn: agents, messages and the verification banner."""
    if result.clarification is not None:  # CAN-33: the run is paused until the user picks
        _clarification(result, index)
        return
    with st.container(border=True):
        st.caption("Agents")
        _agents(took)
    if result.failed_step:
        st.error(result.failed_step)
    for message in result.messages:
        if message.content.startswith(("Declined:", "Planning failed")):
            st.warning(message.content)
    if result.verification is not None:
        verdicts = _verdicts(result)
        passed = sum(1 for v in verdicts if v["passed"])
        if result.verified:
            st.success(
                f"All cited series verified against the official source ({passed} of "
                f"{len(verdicts)}).",
                icon="✅",
            )
        else:
            st.error(
                f"Citation verification failed ({passed} of {len(verdicts)} passed): treat "
                "these figures as unverified.",
                icon="⚠️",
            )


def _evidence(result: RunResult) -> None:
    """The right pane: the evidence for one question, in tabs."""
    flagged = _flagged(result)
    verdicts = _verdicts(result)
    result_tab, series_tab, sql_tab, sources_tab, flags_tab = st.tabs(
        ["Result", "Official series", "SQL", "Sources", f"Quality flags ({len(flagged)})"]
    )

    with result_tab:
        if not result.analyses:
            st.caption("No computed result for this question.")
        figure = result_figure(result.analyses)
        if figure is not None:
            st.plotly_chart(figure, use_container_width=True)
        for analysis in result.analyses:
            st.markdown(f"**{analysis.name}**: `{analysis.recipe}` · {_badge(analysis, verdicts)}")
            for warning in analysis.artifact.warnings:
                st.warning(warning)
            st.dataframe(list(analysis.artifact.rows), use_container_width=True)

    with series_tab:
        chart = series_figure(result.series)
        if chart is None:
            st.caption("No official series were loaded for this question.")
        else:
            st.plotly_chart(chart, use_container_width=True)
            for item in result.series:
                st.markdown(f"**{item.name}** ({item.unit or 'no unit'})")
                st.dataframe(list(item.rows), use_container_width=True)

    with sql_tab:
        if not result.analyses:
            st.caption("No SQL was run for this question.")
        for analysis in result.analyses:
            st.markdown(f"**{analysis.name}**")
            st.code(analysis.artifact.sql_query, language="sql")

    with sources_tab:
        if not result.citations:
            st.caption("No sources were cited for this question.")
        by_claim = {
            (
                _claim_core(v)["table_id"],
                _claim_core(v)["vector_id"],
                _claim_core(v)["reference_period"],
            ): str(v["code"])
            for v in verdicts
        }
        for citation in result.citations:
            core, more = citation.core, citation.enrichment
            verdict = by_claim.get((core.table_id, core.vector_id, core.reference_period))
            st.markdown(
                f"- **{more.bilingual_title.en}**: table `{core.table_id}`, "
                f"vector `{core.vector_id}`, period `{core.reference_period}`, "
                f"{citation.publisher}. Verification: `{verdict or 'not verified'}`. "
                f"[Source]({more.canonical_url})"
            )

    with flags_tab:
        if not flagged:
            st.caption("No observation carries a StatCan quality or status flag.")
        for name, period, why in flagged:
            st.markdown(f"- **{name}**, `{period}`: {why}")


def main() -> None:
    state = _state()
    demo = not live_planner_available()
    clicked = _sidebar(demo)
    st.title("Ask Canadian official statistics")
    st.caption(
        "Every figure is computed by SQL from an official series and its citation is checked "
        "against the publisher before it is shown."
    )

    conversation, evidence = st.columns([2, 3], gap="large")  # stacked on narrow screens

    with evidence:  # filled first, so the last answer stays visible while a new one runs
        st.subheader("Evidence")
        shown = None
        if state.turns:
            shown = len(state.turns) - 1
            if len(state.turns) > 1:
                shown = st.selectbox(
                    "Evidence for",
                    range(len(state.turns)),
                    index=shown,
                    format_func=lambda i: f"{i + 1}. {state.turns[i].question}",
                    key=f"evidence_for_{len(state.turns)}",
                )
            _evidence(state.turns[shown])
        else:
            st.caption("Ask a question. The chart, SQL, sources and quality flags appear here.")

    with conversation:
        st.subheader("Conversation")
        history = st.container()  # above the question box, so a running question appears here too
        with history:
            for index, turn in enumerate(state.turns, start=1):
                with st.chat_message("user"):
                    st.markdown(turn.question)
                with st.chat_message("assistant"):
                    _summary(
                        turn, state.timings[index - 1] if index <= len(state.timings) else {}, index
                    )

        resume = state.pop("resume", None)
        if resume is not None and state.turns:
            question = state.turns[-1].question
            with history, st.chat_message("assistant"):
                with st.status("Continuing…", expanded=True) as progress:
                    result, took = asyncio.run(_ask(question, progress, resume))
                    progress.update(label="Done", state="complete", expanded=False)
            state.turns.append(result)
            state.timings.append(took)
            st.rerun()

        question = (
            st.chat_input(
                "Ask a follow-up…" if state.turns else "Ask about StatCan or Bank of Canada data"
            )
            or clicked
        )
        if not question:
            return
        with history:
            with st.chat_message("user"):
                st.markdown(question)
            with st.chat_message("assistant"):
                with st.status("Planning…", expanded=True) as progress:
                    try:
                        result, took = asyncio.run(_ask(question, progress))
                    except Exception as error:  # surface connector and API errors in the page
                        progress.update(label="Run failed", state="error")
                        st.error(f"{type(error).__name__}: {error}")
                        return
                    progress.update(label="Done", state="complete", expanded=False)
        state.turns.append(result)
        state.timings.append(took)
        st.rerun()  # redraw with the new turn: its evidence on the right, its summary on the left


main()
