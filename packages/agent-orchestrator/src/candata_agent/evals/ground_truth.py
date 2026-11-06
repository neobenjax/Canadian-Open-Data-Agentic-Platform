"""The GTA ground-truth benchmark (CAN-14) as typed questions with citation envelopes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal, cast

from candata_mcp.citation import (
    BilingualTitle,
    CitationEnvelope,
    CoreVerificationTuple,
    MetadataEnrichment,
)

EvalType = Literal["numeric", "comparison", "refusal", "flag"]
EVAL_TYPES: Final = ("numeric", "comparison", "refusal", "flag")

# packages/agent-orchestrator/src/candata_agent/evals/ -> repository root
REPO_ROOT: Final = Path(__file__).resolve().parents[5]
DEFAULT_GROUND_TRUTH: Final = (
    REPO_ROOT / "collaboration" / "benchmarks" / "gta_ground_truth_v1.json"
)


@dataclass(frozen=True, slots=True)
class GroundTruthQuestion:
    id: str
    eval_type: EvalType
    question: str
    citations: tuple[CitationEnvelope, ...]
    expected: dict[str, Any]


@dataclass(frozen=True, slots=True)
class Benchmark:
    name: str
    version: str
    built_on: str
    questions: tuple[GroundTruthQuestion, ...]

    def select(self, ids: list[str] | None) -> tuple[GroundTruthQuestion, ...]:
        """The questions with these IDs, in benchmark order; all of them when ``ids`` is None."""
        if not ids:
            return self.questions
        known = {q.id for q in self.questions}
        unknown = sorted(set(ids) - known)
        if unknown:
            raise KeyError(f"not in the benchmark: {', '.join(unknown)}")
        return tuple(q for q in self.questions if q.id in ids)


def load_benchmark(path: Path = DEFAULT_GROUND_TRUTH) -> Benchmark:
    raw = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    questions = tuple(_question(q) for q in cast(list[dict[str, Any]], raw["questions"]))
    if not questions:
        raise ValueError(f"{path} holds no questions")
    return Benchmark(
        name=str(raw["benchmark"]),
        version=str(raw["version"]),
        built_on=str(raw["built_on"]),
        questions=questions,
    )


def _question(raw: dict[str, Any]) -> GroundTruthQuestion:
    eval_type = str(raw["eval_type"])
    if eval_type not in EVAL_TYPES:
        raise ValueError(f"{raw['id']}: unknown eval_type {eval_type!r}")
    citations = tuple(envelope_from_dict(c) for c in cast(list[dict[str, Any]], raw["citations"]))
    if not citations:
        raise ValueError(f"{raw['id']}: no ground-truth citations")
    return GroundTruthQuestion(
        id=str(raw["id"]),
        eval_type=eval_type,
        question=str(raw["question"]),
        citations=citations,
        expected=cast(dict[str, Any], raw.get("expected", {})),
    )


def envelope_from_dict(raw: dict[str, Any]) -> CitationEnvelope:
    """Rebuild a ``CitationEnvelope`` from its JSON form (ground truth or a recorded run)."""
    core = cast(dict[str, Any], raw["core"])
    more = cast(dict[str, Any], raw["enrichment"])
    title = cast(dict[str, Any], more["bilingual_title"])
    table_id, vector_id = str(core["table_id"]).strip(), str(core["vector_id"]).strip()
    if not table_id or not vector_id:
        raise ValueError(f"citation without a table or vector ID: {core}")
    return CitationEnvelope(
        publisher=str(raw["publisher"]),
        core=CoreVerificationTuple(table_id, vector_id, core.get("reference_period")),
        enrichment=MetadataEnrichment(
            coordinate=more.get("coordinate"),
            release_or_revision_date=more.get("release_or_revision_date"),
            bilingual_title=BilingualTitle(en=str(title["en"]), fr=title.get("fr")),
            canonical_url=str(more["canonical_url"]),
            license_url=more.get("license_url"),
            reference_period_source=more.get("reference_period_source"),
        ),
    )
