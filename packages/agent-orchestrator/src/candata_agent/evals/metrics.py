# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportIncompatibleMethodOverride=false, reportIncompatibleVariableOverride=false
"""The CAN-41 two-tier scores as DeepEval metrics.

All three are deterministic: no LLM judge, no API key and no network. Each test case carries
its ``AgentRun`` as JSON in ``metadata["run"]`` and is named by its question ID, so a test
case is self-contained and can be built from a recorded run file.
"""

from __future__ import annotations

import os

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")

from collections.abc import Callable, Iterable  # noqa: E402
from typing import Any, ClassVar, cast  # noqa: E402

from deepeval.metrics import BaseMetric  # noqa: E402
from deepeval.test_case import LLMTestCase  # noqa: E402

from candata_agent.evals.ground_truth import Benchmark, GroundTruthQuestion  # noqa: E402
from candata_agent.evals.run import AgentRun  # noqa: E402
from candata_agent.evals.scoring import (  # noqa: E402
    Score,
    score_core,
    score_enrichment,
    score_freshness,
)

Scorer = Callable[[GroundTruthQuestion, AgentRun], Score]


def test_case(run: AgentRun) -> LLMTestCase:
    return LLMTestCase(
        input=run.question,
        actual_output=run.answer or "(no answer)",
        name=run.question_id,
        metadata={"run": run.to_json()},
    )


def test_cases(runs: Iterable[AgentRun]) -> list[LLMTestCase]:
    return [test_case(r) for r in runs]


class _TwoTierMetric(BaseMetric):
    """Shared plumbing: look up the question, rebuild the run, score, record the result."""

    title: ClassVar[str]
    tier: ClassVar[int]
    scorer: ClassVar[Scorer]

    def __init__(self, benchmark: Benchmark, threshold: float) -> None:
        self.benchmark = benchmark
        self.threshold = threshold
        self._pass_at = threshold
        self.async_mode = False
        self.include_reason = True
        self.verbose_mode = False
        self.strict_mode = type(self).tier == 1
        self.applicable = True

    def measure(self, test_case: LLMTestCase, *args: Any, **kwargs: Any) -> float:
        truth, run = self._inputs(test_case)
        result = type(self).scorer(truth, run)
        self.score, self.reason, self.applicable = result.score, result.reason, result.applicable
        self.success = result.score >= self._pass_at
        return result.score

    async def a_measure(self, test_case: LLMTestCase, *args: Any, **kwargs: Any) -> float:
        return self.measure(test_case)

    def is_successful(self) -> bool:
        return bool(self.success)

    def _inputs(self, test_case: LLMTestCase) -> tuple[GroundTruthQuestion, AgentRun]:
        metadata = cast(dict[str, Any], test_case.metadata or {})
        if "run" not in metadata:
            raise ValueError(f"test case {test_case.name!r} has no recorded run")
        run = AgentRun.from_json(cast(dict[str, Any], metadata["run"]))
        truth = next((q for q in self.benchmark.questions if q.id == run.question_id), None)
        if truth is None:
            raise KeyError(f"{run.question_id} is not in {self.benchmark.name}")
        return truth, run

    @property
    def __name__(self) -> str:
        return self.title


class CoreCitationMetric(_TwoTierMetric):
    """Tier 1: strict pass/fail on the Core Verification Tuples."""

    title = "Tier 1 · Core citations"
    tier = 1
    scorer = staticmethod(score_core)

    def __init__(self, benchmark: Benchmark) -> None:
        super().__init__(benchmark, threshold=1.0)


class EnrichmentMetric(_TwoTierMetric):
    """Tier 2: share of metadata enrichment fields that match the ground truth."""

    title = "Tier 2 · Metadata enrichment"
    tier = 2
    scorer = staticmethod(score_enrichment)

    def __init__(self, benchmark: Benchmark, threshold: float = 0.7) -> None:
        super().__init__(benchmark, threshold)


class RevisionFreshnessMetric(_TwoTierMetric):
    """Tier 2: share of cited tuples whose release or revision date is current."""

    title = "Tier 2 · Revision freshness"
    tier = 2
    scorer = staticmethod(score_freshness)

    def __init__(self, benchmark: Benchmark, threshold: float = 1.0) -> None:
        super().__init__(benchmark, threshold)


def two_tier_metrics(benchmark: Benchmark) -> list[BaseMetric]:
    return [
        CoreCitationMetric(benchmark),
        EnrichmentMetric(benchmark),
        RevisionFreshnessMetric(benchmark),
    ]
