"""Prompt-injection defense and output validation around the Claude planner (CAN-43).

The planner is the only LLM in the graph, and it never handles data values: every figure is
computed by a fixed SQL recipe from an official series and verified against the publisher.
So the primary defense is structural: the planner can only emit registry-validated plan
steps (``validate_plan``). This module adds the layers around it:

1. **Question screening** (``screen_question``): text addressed to the agent ("ignore your
   instructions", fake system tags, "call submit_plan") is declined before any model call.
   It is a narrow, secondary filter, not the main defense, so it aims for few false alarms.
2. **Output validators** (``PlannerText``): the planner's free text (objective, step
   descriptions, decline reason) is shown to users next to verified figures, so it must not
   carry figures, links, markup, template syntax or hidden characters. A model that writes
   "Toronto rent was $3,200" into a step description would otherwise put an unverified
   number on screen.
3. **Discovery argument validation**: the arguments the model passes to the StatCan discovery
   tools are checked before any request is made.
4. **Untrusted tool results** (``untrusted``): publisher text returned by discovery (table and
   member names) is cleaned and truncated before the model reads it, and the system prompt
   says it is data, never instructions.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Annotated, Any, Final

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

MAX_QUESTION: Final = 2000
MAX_UNTRUSTED_TEXT: Final = 300

# ---------------------------------------------------------------------------------------------
# Hidden characters
# ---------------------------------------------------------------------------------------------


def hidden_characters(text: str) -> list[str]:
    """Control and invisible format characters (zero-width, bidi overrides), as code points."""
    found = {
        f"U+{ord(c):04X}"
        for c in text
        if (unicodedata.category(c) == "Cc" and c not in "\n\t") or unicodedata.category(c) == "Cf"
    }
    return sorted(found)


def _strip_hidden(text: str) -> str:
    return "".join(
        c
        for c in text
        if not (
            (unicodedata.category(c) == "Cc" and c not in "\n\t") or unicodedata.category(c) == "Cf"
        )
    )


# ---------------------------------------------------------------------------------------------
# 1. Question screening
# ---------------------------------------------------------------------------------------------

_I: Final = re.IGNORECASE
INJECTION_PATTERNS: Final[Mapping[str, re.Pattern[str]]] = {
    # Adjacent words only, so "should I ignore the 2020 census rules?" is not caught.
    "instruction override": re.compile(
        r"\b(ignore|disregard|forget|override|bypass)\s+(all\s+|any\s+)?(of\s+)?"
        r"((your|the|my|these|those)\s+)?"
        r"((previous|prior|above|earlier|preceding|original|system|safety)\s+)?"
        r"(instructions?|prompts?|directives?|guardrails?|rules)\b"
        r"|\b(forget|ignore|disregard)\s+(everything|all)\s+(above|before|previously)\b",
        _I,
    ),
    "prompt extraction": re.compile(
        r"\b(reveal|print|show|repeat|output|leak)\b[^.?!\n]{0,30}"
        r"\b(system|developer|hidden|initial)\s+(prompt|message|instructions?)\b",
        _I,
    ),
    "role reassignment": re.compile(
        r"\byou\s+are\s+(now|no\s+longer)\b|\bdeveloper\s+mode\b|\bjailbr(ea|o)k|"
        r"\bpretend\s+(to\s+be|you\s+are)\b",
        _I,
    ),
    "fake conversation markup": re.compile(
        r"<\s*/?\s*(system|assistant|user|instructions?|tool_(use|result)|function_calls?)\b"
        r"|\[/?INST\]|<\|im_(start|end)\|>|^\s*(system|assistant)\s*:",
        _I | re.MULTILINE,
    ),
    "tool hijack": re.compile(
        r"\b(call|invoke|use|run|execute)\s+(the\s+)?"
        r"(submit_plan|decline|lookup_series|find_members|search_statcan_tables|custom_sql)\b",
        _I,
    ),
}


@dataclass(frozen=True, slots=True)
class Screening:
    allowed: bool
    reasons: tuple[str, ...] = ()

    @property
    def message(self) -> str:
        """What the user sees; names the categories, never echoes the matched text."""
        return (
            "the question contains text addressed to the agent rather than a data question "
            f"({', '.join(self.reasons)}). Ask the statistics question on its own."
        )


def screen_question(question: str) -> Screening:
    reasons: list[str] = []
    if len(question) > MAX_QUESTION:
        reasons.append(f"longer than {MAX_QUESTION} characters")
    if hidden_characters(question):
        reasons.append("hidden characters")
    folded = unicodedata.normalize("NFKC", question)
    reasons.extend(name for name, pattern in INJECTION_PATTERNS.items() if pattern.search(folded))
    return Screening(not reasons, tuple(reasons))


# ---------------------------------------------------------------------------------------------
# 2. Output validators for the planner's free text
# ---------------------------------------------------------------------------------------------

_FIGURE: Final = re.compile(
    r"[$€£¥]\s?\d"  # money
    r"|\d\s?(%|per\s?cent\b)"  # percentages
    r"|\d\.\d"  # decimals
    r"|\b\d{1,3}(,\d{3})+\b"  # thousands separators
    r"|\b\d+\s?(pp|bps?|basis points?|percentage points?)\b",
    _I,
)
_LINK: Final = re.compile(r"\b(https?|ftp|file|javascript|data):|\bwww\.", _I)
_MARKUP: Final = re.compile(r"[<>`]|\{\{|\}\}|%\{|\$\{|\]\(")


def check_planner_text(text: str, *, limit: int, allow_empty: bool = False) -> str:
    """Normalise the planner's free text, or raise ``ValueError`` saying what is wrong.

    Years, vector IDs (v41692889), table IDs (18-10-0004-01) and index bases (2002=100) are
    fine; amounts, percentages, decimals, links, markup and hidden characters are not.
    """
    hidden = hidden_characters(text)
    if hidden:
        raise ValueError(f"contains hidden characters ({', '.join(hidden)})")
    clean = " ".join(unicodedata.normalize("NFKC", text).split())
    if not clean:
        if allow_empty:
            return clean
        raise ValueError("is empty")
    if len(clean) > limit:
        raise ValueError(f"is longer than {limit} characters")
    problems: list[str] = []
    if _FIGURE.search(clean):
        problems.append(
            "states a figure (amount, percentage or decimal); plans name series, "
            "they never state values"
        )
    if _LINK.search(clean):
        problems.append("contains a link")
    if _MARKUP.search(clean):
        problems.append("contains markup or template syntax")
    if problems:
        raise ValueError("; ".join(problems))
    return clean


def _text(limit: int, *, allow_empty: bool = False) -> AfterValidator:
    return AfterValidator(
        lambda value: check_planner_text(value, limit=limit, allow_empty=allow_empty)
    )


Objective = Annotated[str, _text(200)]
StepDescription = Annotated[str, _text(120, allow_empty=True)]  # the UI falls back to the ID
DeclineReason = Annotated[str, _text(400)]


class DeclineArgs(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    reason: DeclineReason


# ---------------------------------------------------------------------------------------------
# 3. Discovery tool arguments
# ---------------------------------------------------------------------------------------------

TableId = Annotated[str, Field(pattern=r"^(\d{8}|\d{10}|\d{2}-\d{2}-\d{4}(-\d{2})?)$")]
Keywords = Annotated[str, Field(min_length=1, max_length=120, pattern=r"^[^<>{}`$%\\]*$")]


class _DiscoveryArgs(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)


class SearchTablesArgs(_DiscoveryArgs):
    query: Keywords


class FindMembersArgs(_DiscoveryArgs):
    table_id: TableId
    dimension: Annotated[str, Field(max_length=80, pattern=r"^[^<>{}`$%\\]*$")]
    query: Annotated[str, Field(max_length=80, pattern=r"^[^<>{}`$%\\]*$")]


class LookupSeriesArgs(_DiscoveryArgs):
    table_id: TableId
    # 1 to 10 numeric parts: the connector pads short coordinates with zeroes.
    coordinate: Annotated[str, Field(pattern=r"^\d{1,6}(\.\d{1,6}){0,9}$")]


class ClarifyArgs(_DiscoveryArgs):
    """``request_clarification``: the term, where it is ambiguous, and the members to offer."""

    term: Annotated[str, _text(60)]
    table_id: TableId
    dimension_position: Annotated[int, Field(ge=1, le=10)]
    member_ids: Annotated[list[int], Field(min_length=2, max_length=10)]
    question: Annotated[str, _text(200)]


DISCOVERY_ARGS: Final[Mapping[str, type[_DiscoveryArgs]]] = {
    "search_statcan_tables": SearchTablesArgs,
    "find_members": FindMembersArgs,
    "lookup_series": LookupSeriesArgs,
}


# ---------------------------------------------------------------------------------------------
# 4. Untrusted tool results
# ---------------------------------------------------------------------------------------------


def untrusted(value: Any, *, limit: int = MAX_UNTRUSTED_TEXT) -> Any:
    """Publisher text made safe to show the model: hidden characters gone, strings truncated.

    Recurses through dicts and lists; numbers, booleans and None pass through.
    """
    if isinstance(value, str):
        clean = _strip_hidden(unicodedata.normalize("NFKC", value))
        return clean if len(clean) <= limit else clean[: limit - 1] + "…"
    if isinstance(value, Mapping):
        return {str(k): untrusted(v, limit=limit) for k, v in value.items()}  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
    if isinstance(value, list | tuple):
        return [untrusted(v, limit=limit) for v in value]  # pyright: ignore[reportUnknownVariableType]
    return value
