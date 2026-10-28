"""Citation Verifier node (CAN-24): check every stated figure against its official source.

Before an answer leaves the graph, each claim (a value plus its two-tier Citation Envelope)
is cross-examined against Statistics Canada WDS or Bank of Canada Valet:

1. Tier 1 is well formed: table ID, vector ID and reference period in the official formats.
2. The vector belongs to the cited table (and coordinate, when given).
3. The official value exists for the cited period and is not suppressed.
4. The stated value matches the official value to the published precision.
5. The cited release date is the latest one, so a revised series is never quoted stale.

A claim with ``value=None`` checks the citation only (steps 1, 2, 3 and 5), which is how a
range citation such as ``2024-01/2025-12`` behind a computed total is verified.

The verifier talks to sources through two small protocols, so tests and the LangGraph node
can pass the real connectors or fakes.
"""

from __future__ import annotations

import math
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from enum import StrEnum
from typing import Any, Protocol, cast

from candata_mcp.citation import CitationEnvelope
from candata_mcp.connectors.boc_valet import TABLE_ID as VALET_TABLE_ID
from candata_mcp.connectors.boc_valet import ObservationSet, ValetError, ValetNotFoundError
from candata_mcp.connectors.statcan_wds import (
    StatCanError,
    StatCanNotFoundError,
    StatCanResponseError,
    StatCanSeriesResult,
    format_table_id,
)

_STATCAN_TABLE = re.compile(r"^\d{2}-\d{2}-\d{4}-\d{2}$")
_STATCAN_VECTOR = re.compile(r"^v\d+$")
_VALET_SERIES = re.compile(r"^[A-Za-z0-9_.-]+$")
_PERIOD = r"\d{4}(?:-\d{2}(?:-\d{2})?)?"
_PERIOD_FORMAT = re.compile(rf"^({_PERIOD})(?:/({_PERIOD}))?$")


class StatCanSource(Protocol):
    async def get_data_by_reference_period(
        self, vector_id: int | str, start: str, end: str | None = None
    ) -> StatCanSeriesResult: ...


class ValetSource(Protocol):
    async def get_observations(
        self,
        series_id: str,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> ObservationSet: ...


class VerdictCode(StrEnum):
    """Outcome of checking one claim. Only ``VERIFIED`` lets an answer through."""

    VERIFIED = "verified"
    MALFORMED_CITATION = "malformed_citation"
    NOT_FOUND = "not_found"
    TABLE_MISMATCH = "table_mismatch"
    PERIOD_NOT_FOUND = "period_not_found"
    SUPPRESSED = "suppressed"
    VALUE_MISMATCH = "value_mismatch"
    STALE_RELEASE = "stale_release"
    RELEASE_MISMATCH = "release_mismatch"
    SOURCE_UNAVAILABLE = "source_unavailable"


@dataclass(frozen=True, slots=True)
class Claim:
    """One figure the agent intends to state, with the citation it will give for it."""

    citation: CitationEnvelope
    value: float | None = None
    label: str = ""


@dataclass(frozen=True, slots=True)
class ClaimVerdict:
    claim: Claim
    code: VerdictCode
    message: str
    official_value: float | None = None
    official_release: str | None = None
    # StatCan quality flags on the official point, passed through so the answer can say
    # "use with caution" without failing it (guardrail 6).
    status_code: int | None = None
    symbol_code: int | None = None

    @property
    def passed(self) -> bool:
        return self.code is VerdictCode.VERIFIED


@dataclass(frozen=True, slots=True)
class VerificationReport:
    verdicts: tuple[ClaimVerdict, ...] = field(default_factory=tuple)

    @property
    def passed(self) -> bool:
        return all(v.passed for v in self.verdicts)

    @property
    def failures(self) -> tuple[ClaimVerdict, ...]:
        return tuple(v for v in self.verdicts if not v.passed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "verdicts": [
                {**asdict(v), "code": v.code.value, "passed": v.passed} for v in self.verdicts
            ],
        }


class CitationVerifier:
    """Checks claims against official sources. Network errors never pass a claim."""

    def __init__(self, statcan: StatCanSource, valet: ValetSource) -> None:
        self._statcan = statcan
        self._valet = valet

    async def verify(self, claims: Sequence[Claim]) -> VerificationReport:
        return VerificationReport(tuple([await self.verify_claim(c) for c in claims]))

    async def verify_claim(self, claim: Claim) -> ClaimVerdict:
        problem = _format_problem(claim)
        if problem:
            return ClaimVerdict(claim, VerdictCode.MALFORMED_CITATION, problem)
        if claim.citation.core.table_id == VALET_TABLE_ID:
            return await self._verify_valet(claim)
        return await self._verify_statcan(claim)

    async def _verify_statcan(self, claim: Claim) -> ClaimVerdict:
        core, enrichment = claim.citation.core, claim.citation.enrichment
        start, end = _period_bounds(core.reference_period)
        try:
            series = await self._statcan.get_data_by_reference_period(
                core.vector_id, _wds_date(start), _wds_date(end)
            )
        except StatCanNotFoundError as exc:
            return ClaimVerdict(claim, VerdictCode.NOT_FOUND, f"{core.vector_id}: {exc}")
        except StatCanResponseError as exc:
            # WDS answers an unknown vector with status FAILED inside a 200 response.
            if "WDS call failed" in str(exc):
                return ClaimVerdict(claim, VerdictCode.NOT_FOUND, f"{core.vector_id}: {exc}")
            return _unavailable(claim, exc)
        except StatCanError as exc:
            return _unavailable(claim, exc)

        actual_table = format_table_id(series.product_id)
        if actual_table != core.table_id:
            return ClaimVerdict(
                claim,
                VerdictCode.TABLE_MISMATCH,
                f"{core.vector_id} belongs to table {actual_table}, not {core.table_id}",
            )
        if (
            enrichment.coordinate
            and series.coordinate
            and _coord(enrichment.coordinate) != _coord(series.coordinate)
        ):
            return ClaimVerdict(
                claim,
                VerdictCode.TABLE_MISMATCH,
                f"{core.vector_id} has coordinate {series.coordinate}, not {enrichment.coordinate}",
            )
        if not series.observations:
            return ClaimVerdict(
                claim,
                VerdictCode.PERIOD_NOT_FOUND,
                f"no observation for {core.vector_id} in {core.reference_period}",
            )

        latest = max(series.observations, key=lambda o: o.release_time or "")
        flags = {"status_code": latest.status_code, "symbol_code": latest.symbol_code}
        missing = [o.ref_per for o in series.observations if o.value is None]
        if missing:
            return ClaimVerdict(
                claim,
                VerdictCode.SUPPRESSED,
                f"no published value for {core.vector_id} at {', '.join(missing)} "
                "(suppressed or not available)",
                official_release=latest.release_time,
                **flags,
            )

        official_value: float | None = None
        if claim.value is not None:
            if len(series.observations) != 1:
                return ClaimVerdict(
                    claim,
                    VerdictCode.MALFORMED_CITATION,
                    "a value claim needs a single reference period; cite the inputs of a "
                    "computed figure instead",
                )
            point = series.observations[0]
            official_value = point.value
            assert official_value is not None
            tolerance = 0.5 * 10 ** -(point.decimals if point.decimals is not None else 0)
            if not math.isclose(claim.value, official_value, abs_tol=tolerance + 1e-9):
                return ClaimVerdict(
                    claim,
                    VerdictCode.VALUE_MISMATCH,
                    f"stated {claim.value:g}, official {official_value:g} for "
                    f"{core.vector_id} at {core.reference_period}",
                    official_value=official_value,
                    official_release=point.release_time,
                    **flags,
                )

        release = latest.release_time
        cited = enrichment.release_or_revision_date
        if release and cited != release:
            stale = cited is not None and cited < release
            return ClaimVerdict(
                claim,
                VerdictCode.STALE_RELEASE if stale else VerdictCode.RELEASE_MISMATCH,
                f"cited release {cited}, official release {release} for {core.vector_id} "
                f"at {core.reference_period}"
                + ("; the series was revised or re-released since" if stale else ""),
                official_value=official_value,
                official_release=release,
                **flags,
            )
        return ClaimVerdict(
            claim,
            VerdictCode.VERIFIED,
            f"{core.vector_id} at {core.reference_period} matches the official release",
            official_value=official_value,
            official_release=release,
            **flags,
        )

    async def _verify_valet(self, claim: Claim) -> ClaimVerdict:
        core = claim.citation.core
        start, end = _period_bounds(core.reference_period)
        try:
            obs = await self._valet.get_observations(
                core.vector_id, start_date=_first_day(start), end_date=_last_day(end)
            )
        except ValetNotFoundError as exc:
            return ClaimVerdict(claim, VerdictCode.NOT_FOUND, f"{core.vector_id}: {exc}")
        except ValetError as exc:
            return _unavailable(claim, exc)

        if not obs.observations:
            return ClaimVerdict(
                claim,
                VerdictCode.PERIOD_NOT_FOUND,
                f"no observation for {core.vector_id} in {core.reference_period}",
            )
        missing = [o.date for o in obs.observations if o.value is None]
        if missing:
            return ClaimVerdict(
                claim,
                VerdictCode.SUPPRESSED,
                f"no published value for {core.vector_id} at {', '.join(missing)}",
            )

        official_value: float | None = None
        if claim.value is not None:
            if len(obs.observations) != 1:
                return ClaimVerdict(
                    claim,
                    VerdictCode.MALFORMED_CITATION,
                    "a value claim needs a single observation date; cite the inputs of a "
                    "computed figure instead",
                )
            official_value = obs.observations[0].value
            assert official_value is not None
            tolerance = 0.5 * 10 ** -_decimals(official_value)
            if not math.isclose(claim.value, official_value, abs_tol=tolerance + 1e-9):
                return ClaimVerdict(
                    claim,
                    VerdictCode.VALUE_MISMATCH,
                    f"stated {claim.value:g}, official {official_value:g} for "
                    f"{core.vector_id} at {core.reference_period}",
                    official_value=official_value,
                )
        # Valet publishes no release or revision date, so there is nothing to compare.
        return ClaimVerdict(
            claim,
            VerdictCode.VERIFIED,
            f"{core.vector_id} at {core.reference_period} matches Bank of Canada Valet",
            official_value=official_value,
        )


def make_citation_verifier_node(
    verifier: CitationVerifier,
) -> Callable[[Any], Awaitable[dict[str, Any]]]:
    """LangGraph node: reads ``claims`` from the state and writes ``verification``.

    Works with a dict state or an attribute-style (Pydantic) state, so it can be wired
    before the CAN-21 ``AgentState`` settles. Downstream, a failed report should route back
    to the Data Analyst or to a HITL interrupt, never to the final answer.
    """

    async def citation_verifier(state: object) -> dict[str, Any]:
        raw: object = (
            cast(Mapping[str, object], state).get("claims", ())
            if isinstance(state, Mapping)
            else getattr(state, "claims", ())
        )
        items: Sequence[object] = cast(Sequence[object], raw) if isinstance(raw, Sequence) else ()
        claims = [c for c in items if isinstance(c, Claim)]
        report = await verifier.verify(claims)
        return {"verification": report}

    return citation_verifier


def _format_problem(claim: Claim) -> str | None:
    core = claim.citation.core
    match = _PERIOD_FORMAT.match(core.reference_period)
    if not match:
        return f"reference_period {core.reference_period!r} is not YYYY, YYYY-MM or YYYY-MM-DD"
    if core.table_id == VALET_TABLE_ID:
        if not _VALET_SERIES.match(core.vector_id):
            return f"Valet series {core.vector_id!r} is not a valid series name"
        return None
    if not _STATCAN_TABLE.match(core.table_id):
        return f"table_id {core.table_id!r} is not in NN-NN-NNNN-NN form"
    if not _STATCAN_VECTOR.match(core.vector_id):
        return f"vector_id {core.vector_id!r} is not in vNNN form"
    if not claim.citation.enrichment.release_or_revision_date:
        return "Statistics Canada citations need release_or_revision_date"
    return None


def _period_bounds(reference_period: str) -> tuple[str, str]:
    start, _, end = reference_period.partition("/")
    return start, end or start


def _wds_date(period: str) -> str:
    """WDS keys annual points on January 1 and monthly points on the first of the month."""
    return {4: f"{period}-01-01", 7: f"{period}-01"}.get(len(period), period)


def _first_day(period: str) -> str:
    return _wds_date(period)


def _last_day(period: str) -> str:
    if len(period) == 4:
        return f"{period}-12-31"
    if len(period) == 7:
        year, month = int(period[:4]), int(period[5:7])
        first_of_next = date(year + month // 12, month % 12 + 1, 1)
        return (first_of_next - timedelta(days=1)).isoformat()
    return period


def _coord(coordinate: str) -> tuple[str, ...]:
    """Compare coordinates without trailing zero members: 125.3.3 == 125.3.3.0.0.0.0.0.0.0."""
    parts = coordinate.split(".")
    while parts and parts[-1] == "0":
        parts.pop()
    return tuple(parts)


def _decimals(value: float) -> int:
    text = repr(value)
    return len(text.split(".")[1]) if "." in text and "e" not in text else 0


def _unavailable(claim: Claim, exc: Exception) -> ClaimVerdict:
    return ClaimVerdict(
        claim,
        VerdictCode.SOURCE_UNAVAILABLE,
        f"could not reach the official source, so the claim is unverified: {exc}",
    )
