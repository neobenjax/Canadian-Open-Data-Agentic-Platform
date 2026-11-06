"""Clarification requests and answers for ambiguous dimension members (CAN-33).

The planner asks for a clarification when a question's term matches more than one member of
a table dimension, for example a municipality and a census metropolitan area with the same
name. The Supervisor turns the request into a LangGraph ``interrupt()``. The user's choice
comes back as a ``Resolution`` that the planner must use when it plans again.

Candidates are always members that the planner's ``find_members`` calls returned, so the user
is never offered an option the model made up.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any, Final, cast

MAX_CLARIFICATIONS: Final = 3  # per question; after that the Supervisor declines


def table_key(table_id: str) -> str:
    """``34-10-0154-01``, ``3410015401`` and ``34100154`` all name table ``34100154``."""
    return re.sub(r"\D", "", table_id)[:8]


@dataclass(frozen=True, slots=True)
class Candidate:
    member_id: int
    name: str


@dataclass(frozen=True, slots=True)
class Clarification:
    """The planner's question to the user, with the members to choose from."""

    term: str
    table_id: str
    dimension_position: int
    dimension: str
    question: str
    candidates: tuple[Candidate, ...]

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, raw: Mapping[str, Any]) -> Clarification:
        return cls(
            term=str(raw["term"]),
            table_id=str(raw["table_id"]),
            dimension_position=int(raw["dimension_position"]),
            dimension=str(raw["dimension"]),
            question=str(raw["question"]),
            candidates=tuple(
                Candidate(int(c["member_id"]), str(c["name"])) for c in raw["candidates"]
            ),
        )

    def choose(self, answer: object) -> Candidate | None:
        """The candidate the answer names: its member ID (int or text) or its exact name."""
        if isinstance(answer, Mapping):
            picked = cast(Mapping[str, object], answer)
            answer = picked.get("member_id", picked.get("name"))
        if isinstance(answer, bool) or answer is None:
            return None
        if isinstance(answer, int):
            return next((c for c in self.candidates if c.member_id == answer), None)
        text = " ".join(str(answer).split()).casefold()
        for candidate in self.candidates:
            if text in (str(candidate.member_id), candidate.name.casefold()):
                return candidate
        return None


@dataclass(frozen=True, slots=True)
class Resolution:
    """The member the user chose for a term."""

    term: str
    table_id: str
    dimension_position: int
    member_id: int
    name: str

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, raw: Mapping[str, Any]) -> Resolution:
        return cls(
            term=str(raw["term"]),
            table_id=str(raw["table_id"]),
            dimension_position=int(raw["dimension_position"]),
            member_id=int(raw["member_id"]),
            name=str(raw["name"]),
        )

    @property
    def key(self) -> tuple[str, int, int]:
        return table_key(self.table_id), self.dimension_position, self.member_id

    def as_instruction(self) -> str:
        return (
            f'By "{self.term}" the user means {self.name} (member {self.member_id} in '
            f"dimension {self.dimension_position} of table {self.table_id}). Use that member."
        )


def resolutions_from_json(raw: Sequence[Mapping[str, Any]]) -> tuple[Resolution, ...]:
    return tuple(Resolution.from_json(r) for r in raw)
