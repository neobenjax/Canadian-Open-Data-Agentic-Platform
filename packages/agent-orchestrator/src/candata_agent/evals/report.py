# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
"""Grade recorded runs with DeepEval and summarise them per tier and ``eval_type`` (CAN-41)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from typing import Any, Final

from candata_agent.evals.ground_truth import Benchmark
from candata_agent.evals.metrics import (
    CoreCitationMetric,
    EnrichmentMetric,
    RevisionFreshnessMetric,
    test_cases,
    two_tier_metrics,
)
from candata_agent.evals.run import AgentRun
from candata_agent.evals.scoring import score_enrichment, score_freshness

TIER_1: Final = CoreCitationMetric.title
ENRICHMENT: Final = EnrichmentMetric.title
FRESHNESS: Final = RevisionFreshnessMetric.title


@dataclass(frozen=True, slots=True)
class MetricResult:
    score: float
    passed: bool
    reason: str
    applicable: bool = True


@dataclass(frozen=True, slots=True)
class QuestionResult:
    question_id: str
    eval_type: str
    planner: str
    verified_by_agent: bool | None
    metrics: dict[str, MetricResult]

    @property
    def tier1_passed(self) -> bool:
        return self.metrics[TIER_1].passed


@dataclass(slots=True)
class Report:
    benchmark: str
    version: str
    questions_in_benchmark: int
    results: list[QuestionResult] = field(default_factory=list[QuestionResult])

    @property
    def graded(self) -> int:
        return len(self.results)

    @property
    def tier1_passed(self) -> int:
        return sum(r.tier1_passed for r in self.results)

    def tier1_by_type(self) -> dict[str, tuple[int, int]]:
        out: dict[str, tuple[int, int]] = {}
        for r in self.results:
            passed, total = out.get(r.eval_type, (0, 0))
            out[r.eval_type] = (passed + r.tier1_passed, total + 1)
        return out

    def mean(self, metric: str) -> float | None:
        """Mean score over the questions where the metric applies."""
        scores = [r.metrics[metric].score for r in self.results if r.metrics[metric].applicable]
        return sum(scores) / len(scores) if scores else None

    def to_json(self) -> dict[str, Any]:
        return {
            "benchmark": self.benchmark,
            "version": self.version,
            "questions_in_benchmark": self.questions_in_benchmark,
            "graded": self.graded,
            "tier1_passed": self.tier1_passed,
            "tier1_by_type": {
                k: {"passed": p, "total": t} for k, (p, t) in self.tier1_by_type().items()
            },
            "mean_enrichment": self.mean(ENRICHMENT),
            "mean_freshness": self.mean(FRESHNESS),
            "results": [asdict(r) for r in self.results],
        }


def grade(runs: Sequence[AgentRun], benchmark: Benchmark, *, show: bool = False) -> Report:
    """Score every run with the two-tier DeepEval metrics."""
    from deepeval import evaluate
    from deepeval.evaluate.configs import AsyncConfig, CacheConfig, DisplayConfig

    by_id = {q.id: q for q in benchmark.questions}
    unknown = sorted({r.question_id for r in runs} - by_id.keys())
    if unknown:
        raise KeyError(f"runs for questions not in {benchmark.name}: {', '.join(unknown)}")
    report = Report(benchmark.name, benchmark.version, len(benchmark.questions))
    if not runs:
        return report

    outcome = evaluate(
        test_cases(runs),
        two_tier_metrics(benchmark),
        async_config=AsyncConfig(run_async=False),
        cache_config=CacheConfig(write_cache=False),
        display_config=DisplayConfig(print_results=show, show_indicator=show),
    )
    graded = {t.name: t for t in outcome.test_results}
    for run in runs:
        truth = by_id[run.question_id]
        result = graded[run.question_id]
        applies = {
            TIER_1: True,
            ENRICHMENT: score_enrichment(truth, run).applicable,
            FRESHNESS: score_freshness(truth, run).applicable,
        }
        metrics = {
            m.name: MetricResult(
                score=float(m.score or 0.0),
                passed=bool(m.success),
                reason=m.reason or m.error or "",
                applicable=applies.get(m.name, True),
            )
            for m in result.metrics_data or ()
        }
        report.results.append(
            QuestionResult(run.question_id, truth.eval_type, run.planner, run.verified, metrics)
        )
    return report


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.0%}"


def render_markdown(report: Report, runs: Sequence[AgentRun]) -> str:
    planners = sorted({r.planner for r in runs}) or ["(none)"]
    started = sorted(r.started_at for r in runs if r.started_at)
    lines = [
        f"# CAN-41 two-tier evaluation: {report.benchmark} v{report.version}",
        "",
        f"- **Graded:** {report.graded} of {report.questions_in_benchmark} questions",
        f"- **Planner:** {', '.join(planners)}",
        f"- **Run:** {started[0] if started else 'n/a'} (UTC)",
        "",
        "| Score | Result |",
        "|---|---|",
        f"| Tier 1 · Core citations (strict) | **{report.tier1_passed}/{report.graded} passed** |",
        f"| Tier 2 · Metadata enrichment (mean) | {_pct(report.mean(ENRICHMENT))} |",
        f"| Tier 2 · Revision freshness (mean) | {_pct(report.mean(FRESHNESS))} |",
        "",
        "Tier 1 by `eval_type`: "
        + ", ".join(f"{k} {p}/{t}" for k, (p, t) in sorted(report.tier1_by_type().items())),
        "",
        "| Question | Type | Tier 1 | Enrichment | Freshness | Agent verified | Tier 1 reason |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in report.results:
        core, more, fresh = r.metrics[TIER_1], r.metrics[ENRICHMENT], r.metrics[FRESHNESS]
        verified = {True: "yes", False: "no", None: "n/a"}[r.verified_by_agent]
        lines.append(
            f"| {r.question_id} | {r.eval_type} | {'pass' if core.passed else 'FAIL'} "
            f"| {_cell(more)} | {_cell(fresh)} | {verified} | {core.reason.replace('|', '/')} |"
        )
    gaps = [
        f"- **{r.question_id}**, {name}: {r.metrics[name].reason}"
        for r in report.results
        for name in (ENRICHMENT, FRESHNESS)
        if r.metrics[name].applicable and r.metrics[name].score < 1.0
    ]
    lines += ["", "## Tier 2 detail", "", *(gaps or ["Every applicable Tier 2 score is 100%."])]
    return "\n".join(lines) + "\n"


def _cell(metric: MetricResult) -> str:
    return "n/a" if not metric.applicable else f"{metric.score:.0%}"
