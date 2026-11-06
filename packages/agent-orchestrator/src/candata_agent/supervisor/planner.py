"""Claude-backed planner for the Supervisor (CAN-22). Needs the optional ``agent`` extra.

Claude gets three read-only discovery tools (search StatCan tables, find dimension members,
look up the vector at a coordinate) and two terminal tools: ``submit_plan`` or ``decline``.
Every submitted plan goes through ``validate_plan``; problems go back to Claude as an error
tool result, so it can fix them within the same turn budget. The planner never sees or quotes
data values: it only decides which official series to load and which recipe to run.
"""

from __future__ import annotations

import json
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Final, Protocol, cast

from anthropic import AsyncAnthropic
from anthropic.types.beta import (
    BetaMessageParam,
    BetaTextBlockParam,
    BetaToolParam,
    BetaToolUseBlock,
)

from candata_agent.state import QueryPlan
from candata_agent.supervisor.registry import (
    TOOLS,
    PlanDraft,
    PlanValidationError,
    validate_plan,
)
from candata_mcp.connectors.statcan_wds import (
    CubeMetadata,
    CubeSearchResult,
    StatCanSeriesResult,
)

DEFAULT_MODEL: Final = "claude-opus-5-5"
FALLBACK_BETA: Final = "server-side-fallback-2026-07-01"
PROMPT_CACHING_BETA: Final = "prompt-caching-2024-07-31"
MAX_MEMBERS: Final = 15


class StatCanDiscovery(Protocol):
    async def search_cubes(self, query: str, *, limit: int = 10) -> CubeSearchResult: ...

    async def get_cube_metadata(self, product_id: int | str) -> CubeMetadata: ...

    async def get_data_from_cube(
        self, product_id: int | str, coordinate: str, latest_n: int = 1
    ) -> StatCanSeriesResult: ...


class PlanningError(RuntimeError):
    """Claude did not produce a valid plan or a decline within the turn budget."""


@dataclass(frozen=True, slots=True)
class PlannerResult:
    plan: QueryPlan | None
    declined_reason: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0


SYSTEM_PROMPT: Final = """\
You plan answers to questions about Canadian official statistics (Statistics Canada and the
Bank of Canada). You do not answer the question. You decide which official series to load and
which deterministic calculation to run; other agents execute the plan and verify citations.

Rules:
- Only use vector IDs you have confirmed with lookup_series in this conversation. Find the table
  with search_statcan_tables, find member IDs with find_members, build the 10-part coordinate
  (member IDs in dimension order, 0 for unused positions), then call lookup_series.
- Bank of Canada series need no lookup when you know the Valet series name (V39079 is the
  target for the overnight rate).
- Fetch steps load one series into a data slot ("into"). Calculation steps read slots that an
  earlier fetch step filled. Each slot holds one series. Single-series calculations read
  "slot" (default series_table); to compare two series, load them into two slots (for example
  table_a and table_b) and run the calculation once per slot.
- Prefer a table that publishes the figure directly (an annual table for an annual figure) over
  computing it from a finer series.
- If official data cannot answer the question (the series is not published for that geography,
  period or breakdown), call decline with the reason instead of planning around it.
- Finish by calling submit_plan or decline exactly once. If submit_plan returns problems, fix
  them and call it again.

Plan tools (use these names in submit_plan steps; args_json is a JSON object):
{tool_catalog}
"""


class ClaudePlanner:
    """Plans with Claude through the Messages API, grounded by StatCan discovery calls."""

    def __init__(
        self,
        client: AsyncAnthropic,
        statcan: StatCanDiscovery,
        *,
        model: str = DEFAULT_MODEL,
        effort: str = "medium",
        max_turns: int = 12,
        max_tokens: int = 16000,
    ) -> None:
        self._client = client
        self._statcan = statcan
        self._model = model
        self._effort = effort
        self._max_turns = max_turns
        self._max_tokens = max_tokens
        self._system = SYSTEM_PROMPT.format(tool_catalog=_tool_catalog())
        self._system_blocks: list[BetaTextBlockParam] = [
            {
                "type": "text",
                "text": self._system,
                "cache_control": {"type": "ephemeral"},
            }
        ]
        self._tools: list[BetaToolParam] = [
            cast(BetaToolParam, {**tool, "cache_control": {"type": "ephemeral"}})
            if i == len(PLANNER_TOOLS) - 1
            else tool
            for i, tool in enumerate(PLANNER_TOOLS)
        ]

    async def plan(self, question: str) -> PlannerResult:
        messages: list[BetaMessageParam] = [{"role": "user", "content": question}]
        input_tokens = output_tokens = 0
        cache_creation_tokens = cache_read_tokens = 0
        confirmed: set[str] = set()  # vector IDs lookup_series returned in this conversation
        for _ in range(self._max_turns):
            response = await self._client.beta.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=self._system_blocks,
                tools=self._tools,
                messages=messages,
                output_config={"effort": self._effort},  # type: ignore[typeddict-item]
                betas=[FALLBACK_BETA, PROMPT_CACHING_BETA],
                fallbacks="default",
            )
            input_tokens += response.usage.input_tokens
            output_tokens += response.usage.output_tokens
            cache_creation_tokens += getattr(response.usage, "cache_creation_input_tokens", 0) or 0
            cache_read_tokens += getattr(response.usage, "cache_read_input_tokens", 0) or 0
            if response.stop_reason == "refusal":
                raise PlanningError("the model declined to plan this request")
            if response.stop_reason == "max_tokens":
                raise PlanningError("the planner hit max_tokens before finishing")

            # Append the assistant turn unchanged (thinking blocks included).
            messages.append({"role": "assistant", "content": response.content})
            calls = [b for b in response.content if isinstance(b, BetaToolUseBlock)]
            if not calls:
                messages.append(
                    {"role": "user", "content": "Finish by calling submit_plan or decline."}
                )
                continue

            results: list[dict[str, Any]] = []
            for call in calls:
                if call.name == "decline":
                    reason = str(call.input.get("reason", "")).strip() or "no reason given"
                    return PlannerResult(
                        None,
                        reason,
                        input_tokens,
                        output_tokens,
                        cache_creation_tokens,
                        cache_read_tokens,
                    )
                if call.name == "submit_plan":
                    try:
                        plan = validate_plan(
                            PlanDraft.model_validate(call.input), confirmed_vectors=confirmed
                        )
                    except PlanValidationError as error:
                        results.append(_tool_result(call.id, "\n".join(error.problems), True))
                        continue
                    except ValueError as error:  # malformed draft shape
                        results.append(_tool_result(call.id, str(error), True))
                        continue
                    return PlannerResult(
                        plan,
                        None,
                        input_tokens,
                        output_tokens,
                        cache_creation_tokens,
                        cache_read_tokens,
                    )
                try:
                    payload = await self._discover(call.name, call.input)
                    if call.name == "lookup_series":
                        confirmed.add(str(payload["vector_id"]))
                    results.append(_tool_result(call.id, json.dumps(payload), False))
                except Exception as error:  # discovery failures go back to the model
                    results.append(_tool_result(call.id, f"{type(error).__name__}: {error}", True))
            messages.append({"role": "user", "content": results})  # type: ignore[typeddict-item]

        raise PlanningError(f"no valid plan within {self._max_turns} turns")

    async def _discover(self, name: str, args: dict[str, object]) -> dict[str, Any]:
        if name == "search_statcan_tables":
            found = await self._statcan.search_cubes(str(args["query"]), limit=8)
            return {
                "total_matches": found.total_results,
                "tables": [
                    {
                        "table_id": c.table_id,
                        "title": c.title_en,
                        "frequency": c.frequency_name,
                        "start": c.start_date,
                        "end": c.end_date,
                    }
                    for c in found.cubes
                ],
            }
        if name == "find_members":
            meta = await self._statcan.get_cube_metadata(str(args["table_id"]))
            wanted = _fold(str(args.get("query", "")))
            dimension_filter = _fold(str(args.get("dimension", "")))
            dimensions: list[dict[str, Any]] = []
            for dim in meta.dimensions:
                if dimension_filter and dimension_filter not in _fold(dim.name_en):
                    continue
                matches = [m for m in dim.members if wanted in _fold(m.name_en)]
                dimensions.append(
                    {
                        "position": dim.position_id,
                        "dimension": dim.name_en,
                        "member_count": len(dim.members),
                        "matches": [
                            {"member_id": m.member_id, "name": m.name_en}
                            for m in matches[:MAX_MEMBERS]
                        ],
                        "more_matches": max(0, len(matches) - MAX_MEMBERS),
                    }
                )
            return {"table_id": str(args["table_id"]), "title": meta.title_en, "dims": dimensions}
        if name == "lookup_series":
            series = await self._statcan.get_data_from_cube(
                str(args["table_id"]), str(args["coordinate"]), latest_n=1
            )
            latest = series.observations[-1].ref_per if series.observations else None
            return {
                "vector_id": f"v{series.vector_id}",
                "coordinate": series.coordinate,
                "series_title": series.series_title_en,
                "unit": series.unit,
                "latest_reference_period": latest,
            }
        raise ValueError(f"unknown tool {name!r}")


def _tool_result(tool_use_id: str, content: str, is_error: bool) -> dict[str, Any]:
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": content,
        "is_error": is_error,
    }


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def _tool_catalog() -> str:
    lines: list[str] = []
    for spec in TOOLS.values():
        schema = spec.args.model_json_schema()
        props = ", ".join(sorted(schema.get("properties", {})))
        reads = f" Reads: {', '.join(spec.reads)}." if spec.reads else " Reads: its slot."
        lines.append(f"- {spec.name}({props}): {spec.description}{reads}")
    return "\n".join(lines)


def _strict(
    name: str, description: str, properties: dict[str, Any], required: Sequence[str]
) -> BetaToolParam:
    return {
        "name": name,
        "description": description,
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": list(required),
            "additionalProperties": False,
        },
    }


_STRING: Final[dict[str, Any]] = {"type": "string"}

PLANNER_TOOLS: Final[list[BetaToolParam]] = [
    _strict(
        "search_statcan_tables",
        "Search Statistics Canada tables by keywords (all words must match).",
        {"query": _STRING},
        ["query"],
    ),
    _strict(
        "find_members",
        "List a table's dimensions and the members whose name contains the query. "
        "Use an empty dimension to search every dimension.",
        {"table_id": _STRING, "dimension": _STRING, "query": _STRING},
        ["table_id", "dimension", "query"],
    ),
    _strict(
        "lookup_series",
        "Resolve a table and 10-part coordinate to its vector ID, series title and unit.",
        {"table_id": _STRING, "coordinate": _STRING},
        ["table_id", "coordinate"],
    ),
    _strict(
        "submit_plan",
        "Submit the plan. Each step names a plan tool and its arguments as a JSON object string.",
        {
            "objective": _STRING,
            "steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "tool": {"type": "string", "enum": sorted(TOOLS)},
                        "args_json": _STRING,
                        "description": _STRING,
                    },
                    "required": ["tool", "args_json", "description"],
                    "additionalProperties": False,
                },
            },
        },
        ["objective", "steps"],
    ),
    _strict(
        "decline",
        "Use when official data cannot answer the question. Say what is not published.",
        {"reason": _STRING},
        ["reason"],
    ),
]
