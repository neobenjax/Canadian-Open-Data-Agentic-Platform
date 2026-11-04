"""Two-tier scoring of one agent run against its ground-truth question (CAN-41).

Pure functions, no DeepEval: ``metrics.py`` wraps them as DeepEval metrics.

- **Tier 1, core citations (strict pass/fail).** Every ground-truth Core Verification Tuple
  must be covered by an agent citation with the same table and vector whose reference period
  contains the expected one, and the agent must cite nothing outside the ground truth. On a
  ``refusal`` question the agent must produce no figures at all.
- **Tier 2, enrichment (scored).** For each covered tuple: publisher, coordinate, English
  and French titles and canonical URL, compared field by field.
- **Tier 2, revision freshness (scored).** For each covered tuple with a known release date:
  the agent's release or revision date is the same or later.

Reference periods are compared as half-open date intervals (guardrail 8), so ``2025-08``
is inside ``2025-08/2026-08`` and ``2025`` is inside ``2025-01-01/2025-12-31``. A cited daily
range may start or end up to ``DAILY_SLACK`` inside an expected daily range, because business-day
series have no observation on weekends and holidays (Valet has none on 1 January).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Final

from candata_agent.evals.ground_truth import GroundTruthQuestion
from candata_agent.evals.run import AgentRun
from candata_mcp.citation import CitationEnvelope, CoreVerificationTuple


@dataclass(frozen=True, slots=True)
class Score:
    score: float
    reason: str
    applicable: bool = True


# ---------------------------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------------------------

_PERIOD = re.compile(r"^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?$")
_DAY: Final = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DAILY_SLACK: Final = timedelta(days=7)


def period_interval(period: str) -> tuple[date, date]:
    """``[start, end)`` for ``YYYY``, ``YYYY-MM``, ``YYYY-MM-DD`` or ``start/end``.

    Raises ``ValueError`` for anything else, rather than guessing.
    """
    if "/" in period:
        first, last = (p.strip() for p in period.split("/", 1))
        return _interval(first)[0], _interval(last)[1]
    return _interval(period.strip())


def _interval(text: str) -> tuple[date, date]:
    match = _PERIOD.match(text)
    if match is None:
        raise ValueError(f"not a reference period: {text!r}")
    year, month, day = (int(g) if g else None for g in match.groups())
    assert year is not None
    if month is None:
        return date(year, 1, 1), date(year + 1, 1, 1)
    if day is None:
        start = date(year, month, 1)
        return start, date(year + month // 12, month % 12 + 1, 1)
    start = date(year, month, day)
    return start, date.fromordinal(start.toordinal() + 1)


def _table(table_id: str) -> str:
    return table_id.replace("-", "").strip().casefold()


def same_series(a: CoreVerificationTuple, b: CoreVerificationTuple) -> bool:
    return _table(a.table_id) == _table(b.table_id) and (
        a.vector_id.strip().casefold() == b.vector_id.strip().casefold()
    )


def covers(cited: CoreVerificationTuple, expected: CoreVerificationTuple) -> bool:
    """The cited series is the expected one and its period contains the expected period."""
    if not same_series(cited, expected):
        return False
    if expected.reference_period is None:
        return True
    if cited.reference_period is None:
        return False
    try:
        got, want = (
            period_interval(cited.reference_period),
            period_interval(expected.reference_period),
        )
    except ValueError:
        return False
    slack = DAILY_SLACK if _is_daily_range(expected.reference_period) else timedelta(0)
    return got[0] <= want[0] + slack and want[1] - slack <= got[1]


def _is_daily_range(period: str) -> bool:
    parts = [p.strip() for p in period.split("/")]
    return len(parts) == 2 and all(_DAY.match(p) for p in parts)


def matches(
    truth: GroundTruthQuestion, run: AgentRun
) -> list[tuple[CitationEnvelope, CitationEnvelope | None]]:
    """Each ground-truth citation with the agent citation covering it, or None."""
    return [
        (want, next((c for c in run.citations if covers(c.core, want.core)), None))
        for want in truth.citations
    ]


def _label(core: CoreVerificationTuple) -> str:
    return f"{core.table_id} {core.vector_id} {core.reference_period or '(no period)'}"


# ---------------------------------------------------------------------------------------------
# Tier 1
# ---------------------------------------------------------------------------------------------


def score_core(truth: GroundTruthQuestion, run: AgentRun) -> Score:
    extra = [
        c for c in run.citations if not any(same_series(c.core, t.core) for t in truth.citations)
    ]
    if truth.eval_type == "refusal":
        if run.produced_figures:
            return Score(0.0, "gave figures on a question whose data does not exist")
        if extra:
            return Score(0.0, f"cited series outside the ground truth: {_labels(extra)}")
        return Score(1.0, "produced no figures" + _why(run))

    if run.error:
        return Score(0.0, f"run failed: {run.error}")
    missing = [want.core for want, got in matches(truth, run) if got is None]
    problems: list[str] = []
    if missing:
        problems.append("missing " + "; ".join(_label(m) for m in missing))
    if extra:
        problems.append(f"cited outside the ground truth: {_labels(extra)}")
    if not problems:
        return Score(1.0, f"all {len(truth.citations)} core tuples cited, nothing extra")
    return Score(0.0, ". ".join(problems) + _why(run))


def _labels(citations: list[CitationEnvelope]) -> str:
    return "; ".join(_label(c.core) for c in citations)


def _why(run: AgentRun) -> str:
    detail = run.declined or run.failed_step
    return f" ({detail})" if detail else ""


# ---------------------------------------------------------------------------------------------
# Tier 2
# ---------------------------------------------------------------------------------------------

_SPACE = re.compile(r"\s+")


def _same_text(a: str | None, b: str | None) -> bool:
    if a is None or b is None:
        return False
    return _SPACE.sub(" ", a).strip().casefold() == _SPACE.sub(" ", b).strip().casefold()


def _same_url(a: str | None, b: str | None) -> bool:
    if a is None or b is None:
        return False
    return a.strip().rstrip("/").casefold() == b.strip().rstrip("/").casefold()


def score_enrichment(truth: GroundTruthQuestion, run: AgentRun) -> Score:
    if truth.eval_type == "refusal":
        return Score(1.0, "not scored on refusal questions", applicable=False)
    pairs = [(want, got) for want, got in matches(truth, run) if got is not None]
    if not pairs:
        return Score(0.0, "no ground-truth tuple was cited, so there is nothing to enrich")
    hits = total = 0
    short: dict[str, int] = {}
    for want, got in pairs:
        w, g = want.enrichment, got.enrichment
        fields = {
            "publisher": (want.publisher, got.publisher, _same_text),
            "coordinate": (w.coordinate, g.coordinate, _same_text),
            "English title": (w.bilingual_title.en, g.bilingual_title.en, _same_text),
            "French title": (w.bilingual_title.fr, g.bilingual_title.fr, _same_text),
            "canonical URL": (w.canonical_url, g.canonical_url, _same_url),
        }
        for name, (expected, actual, same) in fields.items():
            if expected is None:
                continue  # the publisher has no such field for this series
            total += 1
            if same(expected, actual):
                hits += 1
            else:
                short[name] = short.get(name, 0) + 1
    score = hits / total if total else 1.0
    if not short:
        return Score(score, f"all {total} enrichment fields match")
    gaps = ", ".join(f"{name} ({n})" for name, n in short.items())
    return Score(score, f"{hits}/{total} enrichment fields match; differs or missing: {gaps}")


def _release(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.strip())
    except ValueError:
        return None


def score_freshness(truth: GroundTruthQuestion, run: AgentRun) -> Score:
    if truth.eval_type == "refusal":
        return Score(1.0, "not scored on refusal questions", applicable=False)
    checks = [
        (want, got)
        for want, got in matches(truth, run)
        if got is not None and _release(want.enrichment.release_or_revision_date) is not None
    ]
    if not checks:
        covered = any(got is not None for _, got in matches(truth, run))
        if covered:
            return Score(1.0, "the publisher gives no release dates here", applicable=False)
        return Score(0.0, "no ground-truth tuple was cited, so freshness cannot be shown")
    stale: list[str] = []
    for want, got in checks:
        expected = _release(want.enrichment.release_or_revision_date)
        actual = _release(got.enrichment.release_or_revision_date)
        assert expected is not None
        if actual is None:
            stale.append(f"{_label(want.core)}: no release date")
        elif actual < expected:
            stale.append(
                f"{_label(want.core)}: released {actual:%Y-%m-%d}, "
                f"expected {expected:%Y-%m-%d} or later"
            )
    fresh = len(checks) - len(stale)
    score = fresh / len(checks)
    if not stale:
        return Score(score, f"all {len(checks)} release dates are current")
    return Score(score, f"{fresh}/{len(checks)} current; stale: " + "; ".join(stale))
