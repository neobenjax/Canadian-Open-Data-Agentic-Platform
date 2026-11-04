"""CanData agent UI (CAN-32): ask a question, watch the agents work, see the official series.

Run from the repo root:

    uv sync --extra ui --extra agent
    uv run streamlit run apps/agent-ui/app.py

Without ANTHROPIC_API_KEY the page runs in demo mode (three benchmark questions with fixed
plans, executed against live StatCan and Bank of Canada data).
"""

from __future__ import annotations

import asyncio
import sys
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


def _state() -> Any:
    if "thread_id" not in st.session_state:
        st.session_state.thread_id = f"ui_{uuid.uuid4().hex[:10]}"
        st.session_state.session_id = f"session_{uuid.uuid4().hex[:8]}"
        st.session_state.turns = []
    return st.session_state


def _sidebar(demo: bool) -> str | None:
    with st.sidebar:
        st.header("CanData Agent")
        if demo:
            st.info(
                "**Demo mode.** No `ANTHROPIC_API_KEY`, so only the example questions are "
                "planned. Their data is fetched live from StatCan and the Bank of Canada."
            )
        else:
            st.success("**Live mode.** Claude plans each question from StatCan discovery.")
        st.caption(f"Conversation `{st.session_state.thread_id}`")
        if st.button("New conversation", use_container_width=True):
            for key in ("thread_id", "session_id", "turns"):
                st.session_state.pop(key, None)
            st.rerun()
        st.subheader("Example questions")
        for index, item in enumerate(DEMO_QUESTIONS):
            if st.button(item.question, key=f"example_{index}", use_container_width=True):
                return item.question
    return None


async def _ask(question: str, progress: Any, resume: object = None) -> RunResult:
    extra: dict[str, object] = {} if resume is None else {"resume": resume}
    async with open_agent(db_path=ROOT / DEFAULT_DB) as (app, _):
        async for event in stream_question(
            app,
            question,
            thread_id=st.session_state.thread_id,
            session_id=st.session_state.session_id,
            **extra,  # type: ignore[arg-type]
        ):
            if isinstance(event, NodeStarted):
                progress.update(label=f"{NODE_LABELS[event.node]} working…")
            elif isinstance(event, NodeFinished):
                for message in event.messages:
                    progress.markdown(f"**{NODE_LABELS.get(message.name or '', 'Agent')}**")
                    progress.markdown(message.content)
            elif isinstance(event, RunFinished):
                return event.result
    raise RuntimeError("the graph stream ended without a result")


def _render(result: RunResult, index: int) -> None:
    pending = result.clarification
    if pending is not None:  # CAN-33: the run is paused until the user picks a member
        st.info(pending.question, icon="❓")
        if pending.error:
            st.warning(pending.error)
        if index == len(st.session_state.turns):  # only the latest turn can be answered
            labels = {
                f"{name} (member {member_id})": member_id for member_id, name in pending.options
            }
            picked = st.radio("Which one do you mean?", list(labels), key=f"pick_{index}")
            left, right = st.columns(2)
            if left.button("Continue", key=f"go_{index}", type="primary"):
                st.session_state.resume = labels[picked]
                st.rerun()
            if right.button("Cancel", key=f"cancel_{index}"):
                st.session_state.resume = "cancel"
                st.rerun()
        return
    if result.failed_step:
        st.error(result.failed_step)
    declined = [
        m for m in result.messages if m.content.startswith(("Declined:", "Planning failed"))
    ]
    for message in declined:
        st.warning(message.content)

    if result.verification is not None:
        if result.verified:
            st.success("All cited series verified against the official source.", icon="✅")
        else:
            st.error("Citation verification failed: treat these figures as unverified.", icon="⚠️")

    if result.analyses:
        st.subheader("Result")
    figure = result_figure(result.analyses)
    if figure is not None:
        st.plotly_chart(figure, use_container_width=True)
    for analysis in result.analyses:
        st.markdown(f"**{analysis.name}**: `{analysis.recipe}`")
        for warning in analysis.artifact.warnings:
            st.warning(warning)
        st.dataframe(list(analysis.artifact.rows), use_container_width=True)
        with st.expander("SQL"):
            st.code(analysis.artifact.sql_query, language="sql")

    chart = series_figure(result.series)
    if chart is not None:
        st.subheader("Official series")
        st.plotly_chart(chart, use_container_width=True)
        flagged = sum(1 for s in result.series for r in s.rows if flag_text(r))
        if flagged:
            st.caption(f"⚠️ {flagged} observations carry a StatCan quality or status flag.")
        with st.expander("Data table"):
            for item in result.series:
                st.markdown(f"**{item.name}** ({item.unit or 'no unit'})")
                st.dataframe(list(item.rows), use_container_width=True)

    if result.citations:
        st.subheader("Sources")
        verdicts = {
            v["claim"]["citation"]["core"]["vector_id"]: v["code"]
            for v in (result.verification or {}).get("verdicts", [])
        }
        for citation in result.citations:
            core, more = citation.core, citation.enrichment
            verdict = verdicts.get(core.vector_id, "not verified")
            st.markdown(
                f"- **{more.bilingual_title.en}**: table `{core.table_id}`, "
                f"vector `{core.vector_id}`, period `{core.reference_period}`, "
                f"{citation.publisher}. Verification: `{verdict}`. [Source]({more.canonical_url})"
            )


def main() -> None:
    state = _state()
    demo = not live_planner_available()
    clicked = _sidebar(demo)
    st.title("Ask Canadian official statistics")
    st.caption(
        "Every figure is computed by SQL from an official series and its citation is checked "
        "against the publisher before it is shown."
    )

    for index, turn in enumerate(state.turns, start=1):
        with st.chat_message("user"):
            st.markdown(turn.question)
        with st.chat_message("assistant"):
            _render(turn, index)

    resume = state.pop("resume", None)
    if resume is not None and state.turns:
        question = state.turns[-1].question
        with st.chat_message("assistant"), st.status("Continuing…", expanded=True) as progress:
            result = asyncio.run(_ask(question, progress, resume))
            progress.update(label="Done", state="complete", expanded=False)
        state.turns.append(result)
        st.rerun()

    question = st.chat_input("Ask about StatCan or Bank of Canada data") or clicked
    if not question:
        return
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        with st.status("Planning…", expanded=True) as progress:
            try:
                result = asyncio.run(_ask(question, progress))
            except Exception as error:  # surface connector and API errors in the page
                progress.update(label="Run failed", state="error")
                st.error(f"{type(error).__name__}: {error}")
                return
            progress.update(label="Done", state="complete", expanded=False)
        _render(result, len(state.turns) + 1)
    state.turns.append(result)
    if result.clarification is not None:
        st.rerun()  # show the options as the latest, answerable turn


main()
