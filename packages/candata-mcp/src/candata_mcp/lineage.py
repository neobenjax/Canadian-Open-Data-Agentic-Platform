"""Data lineage returned alongside every figure (CAN-26).

The Citation Envelope says *which* official figure an answer rests on. Lineage says *how it got
here*: the upstream request, when it was fetched, the release it came from, and each
transformation applied before the model saw it. It is separate from the envelope on purpose,
so the Tier 1 and Tier 2 schema stays as defined in PR #8.

Nothing is guessed: ``source_call`` is ``None`` when the caller did not say what it fetched, and
``upstream_release`` is ``None`` when the publisher gives no release timestamp (Valet).
"""

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

from candata_mcp.connectors.boc_valet import VALET_BASE_URL
from candata_mcp.connectors.statcan_wds import STATCAN_WDS_BASE_URL


@dataclass(frozen=True, slots=True)
class SourceCall:
    """The upstream request behind a result, as the server made it."""

    endpoint: str
    request: Mapping[str, str | int]


@dataclass(frozen=True, slots=True)
class LineageRecord:
    publisher: str
    source_call: SourceCall | None
    fetched_at: str | None
    upstream_release: str | None
    title_source: str | None
    steps: tuple[str, ...]


def statcan_call(method: str, request: Mapping[str, str | int]) -> SourceCall:
    return SourceCall(endpoint=f"{STATCAN_WDS_BASE_URL}/{method}", request=dict(request))


def valet_call(path: str, params: Mapping[str, str | int | None]) -> SourceCall:
    request = {k: v for k, v in params.items() if v is not None}
    return SourceCall(endpoint=f"{VALET_BASE_URL}/{path}", request=request)


def build_lineage(
    *,
    publisher: str,
    fetched_at: str | None,
    upstream_release: str | None,
    steps: tuple[str, ...],
    source_call: SourceCall | None = None,
    title_source: str | None = None,
) -> dict[str, Any]:
    """Return the lineage block as plain JSON-ready data."""
    record = LineageRecord(
        publisher=publisher,
        source_call=source_call,
        fetched_at=fetched_at,
        upstream_release=upstream_release,
        title_source=title_source,
        steps=steps,
    )
    return asdict(record)
