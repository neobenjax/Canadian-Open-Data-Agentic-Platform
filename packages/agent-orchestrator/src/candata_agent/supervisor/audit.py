"""Audit trail of the planner's LLM tool calls (CAN-43).

Every tool call the model makes is recorded with its outcome, whether it was allowed, rejected
by a validator, or failed upstream, and every recorded call is also logged as one JSON line
on the ``candata_agent.audit`` logger. The Supervisor stores the trail for each question in
the thread's scratchpad, so it is checkpointed with the run.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from typing import Any, Final, Literal

AUDIT_LOGGER: Final = logging.getLogger("candata_agent.audit")
MAX_RECORDED_INPUT: Final = 500

Outcome = Literal["ok", "rejected", "error", "blocked"]


@dataclass(frozen=True, slots=True)
class ToolCallRecord:
    """One model tool call. ``input`` is the model's arguments as JSON, truncated."""

    turn: int
    tool: str
    input: str
    outcome: Outcome
    detail: str = ""
    duration_ms: int = 0

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


def record(
    turn: int,
    tool: str,
    arguments: object,
    outcome: Outcome,
    detail: str = "",
    duration_ms: int = 0,
) -> ToolCallRecord:
    """Build a record and log it."""
    try:
        shown = json.dumps(arguments, ensure_ascii=False, sort_keys=True, default=str)
    except (TypeError, ValueError):
        shown = repr(arguments)
    if len(shown) > MAX_RECORDED_INPUT:
        shown = shown[: MAX_RECORDED_INPUT - 1] + "…"
    entry = ToolCallRecord(turn, tool, shown, outcome, detail[:500], duration_ms)
    level = logging.INFO if outcome == "ok" else logging.WARNING
    AUDIT_LOGGER.log(level, json.dumps({"event": "planner_tool_call", **entry.to_json()}))
    return entry
