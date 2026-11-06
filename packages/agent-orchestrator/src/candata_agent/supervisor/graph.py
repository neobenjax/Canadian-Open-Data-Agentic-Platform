# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
"""The CAN-22 agent graph: Supervisor, Data Fetcher, Data Analyst and Citation Verifier.

Run it through ``traced_run`` (CAN-25) so one question is one trace; every node is wrapped in
``traced_node`` here, so callers don't decorate anything themselves.
"""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from candata_agent import traced_node
from candata_agent.analyst import data_analyst_node
from candata_agent.state import AgentState
from candata_agent.supervisor.node import (
    CITATION_VERIFIER,
    HUMAN_CLARIFICATION,
    SUPERVISOR,
    Planner,
    make_clarification_node,
    make_data_fetcher_node,
    make_input_verifier_node,
    make_supervisor_node,
    route_from_supervisor,
)
from candata_agent.supervisor.registry import DATA_ANALYST, DATA_FETCHER
from candata_agent.verifier import CitationVerifier, StatCanSource, ValetSource


def build_agent_graph(
    *,
    planner: Planner,
    statcan: StatCanSource,
    valet: ValetSource,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
) -> CompiledStateGraph[Any, Any, Any, Any]:
    """Compile the graph. ``statcan``/``valet`` serve both the fetcher and the verifier."""
    builder: StateGraph[Any, Any, Any, Any] = StateGraph(AgentState)
    builder.add_node(SUPERVISOR, traced_node(SUPERVISOR)(make_supervisor_node(planner)))
    fetcher = make_data_fetcher_node(statcan, valet)
    builder.add_node(DATA_FETCHER, traced_node(DATA_FETCHER)(fetcher))
    builder.add_node(DATA_ANALYST, traced_node(DATA_ANALYST)(data_analyst_node))
    builder.add_node(
        CITATION_VERIFIER,
        traced_node(CITATION_VERIFIER)(make_input_verifier_node(CitationVerifier(statcan, valet))),
    )
    # CAN-33: pauses with interrupt() until the user picks a member; needs a checkpointer.
    builder.add_node(
        HUMAN_CLARIFICATION, traced_node(HUMAN_CLARIFICATION)(make_clarification_node())
    )
    builder.add_edge(START, SUPERVISOR)
    builder.add_conditional_edges(
        SUPERVISOR,
        route_from_supervisor,
        [DATA_FETCHER, DATA_ANALYST, CITATION_VERIFIER, HUMAN_CLARIFICATION, END],
    )
    builder.add_edge(HUMAN_CLARIFICATION, SUPERVISOR)
    builder.add_edge(DATA_FETCHER, SUPERVISOR)
    builder.add_edge(DATA_ANALYST, SUPERVISOR)
    builder.add_edge(CITATION_VERIFIER, END)
    return builder.compile(checkpointer=checkpointer)
