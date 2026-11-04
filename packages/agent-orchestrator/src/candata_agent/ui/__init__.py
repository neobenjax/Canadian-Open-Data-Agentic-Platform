"""Streamlit UI support (CAN-32): stream a question through the graph and chart what it fetched.

``stream`` and ``session`` need only the core install; ``charts`` needs the ``ui`` extra
(``uv sync --extra ui``) for Plotly. The page itself is ``apps/agent-ui/app.py``.
"""

from candata_agent.ui.stream import (
    NODE_LABELS,
    AnalysisResult,
    FetchedSeries,
    NodeFinished,
    NodeStarted,
    RunEvent,
    RunFinished,
    RunResult,
    stream_question,
)

__all__ = [
    "NODE_LABELS",
    "AnalysisResult",
    "FetchedSeries",
    "NodeFinished",
    "NodeStarted",
    "RunEvent",
    "RunFinished",
    "RunResult",
    "stream_question",
]
