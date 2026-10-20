"""Async client for the Bank of Canada Valet API (CAN-12).

Valet publishes series values, labels and units but no release or revision timestamp and no
French labels, so those citation fields are left empty rather than guessed. Every result
carries ``fetched_at`` (the server's HTTP ``Date``) so a figure can still be pinned to the
moment it was read.
"""

import asyncio
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime
from types import TracebackType
from typing import Any, Self
from urllib.parse import quote

import httpx

from candata_mcp.citation import (
    BilingualTitle,
    CitationEnvelope,
    CoreVerificationTuple,
    MetadataEnrichment,
)

VALET_BASE_URL = "https://www.bankofcanada.ca/valet"
PUBLISHER = "Bank of Canada"
TABLE_ID = "Valet"

POLICY_RATE_SERIES = "V39079"
CPI_SERIES: Mapping[str, str] = {
    "total": "V41690973",
    "total_sa": "V41690914",
    "yoy": "STATIC_TOTALCPICHANGE",
    "xfet": "STATIC_CPIXFET",
    "cpiw": "CPIW",
    "cpix": "ATOM_V41693242",
    "median": "CPI_MEDIAN",
    "trim": "CPI_TRIM",
    "common": "CPI_COMMON",
}

_NAME = re.compile(r"^[A-Za-z0-9_\-]+$")
_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


class ValetError(Exception):
    """Base class for every error raised by this client."""


class ValetRequestError(ValetError):
    """The request never produced a response (timeout, connection failure)."""


class ValetHTTPError(ValetError):
    """Valet answered with an error status."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(f"Valet returned HTTP {status_code}: {message}")
        self.status_code = status_code
        self.message = message


class ValetNotFoundError(ValetHTTPError):
    """The series or group does not exist."""


class ValetResponseError(ValetError):
    """Valet answered 200 but the body was not the expected JSON shape."""


@dataclass(frozen=True, slots=True)
class SeriesDetail:
    name: str
    label: str
    description: str
    frequency: str | None
    unit: str | None
    date_format: str | None
    url: str


@dataclass(frozen=True, slots=True)
class Observation:
    date: str
    value: float | None


@dataclass(frozen=True, slots=True)
class SeriesSummary:
    name: str
    label: str
    url: str


@dataclass(frozen=True, slots=True)
class GroupSummary:
    name: str
    label: str
    description: str
    url: str


@dataclass(frozen=True, slots=True)
class GroupDetail:
    name: str
    label: str
    description: str
    url: str
    frequency: str | None
    series: tuple[SeriesSummary, ...]


@dataclass(frozen=True, slots=True)
class ObservationSet:
    """Observations for one series, oldest first, with the moment they were fetched."""

    series: SeriesDetail
    observations: tuple[Observation, ...]
    fetched_at: str

    def citation(self) -> CitationEnvelope:
        if not self.observations:
            raise ValueError(f"no observations to cite for {self.series.name}")
        first, last = self.observations[0].date, self.observations[-1].date
        period = self._period(first)
        if first != last:
            period = f"{period}/{self._period(last)}"
        return CitationEnvelope(
            publisher=PUBLISHER,
            core=CoreVerificationTuple(TABLE_ID, self.series.name, period),
            enrichment=MetadataEnrichment(
                coordinate=None,
                release_or_revision_date=None,
                bilingual_title=BilingualTitle(en=self.series.label, fr=None),
                canonical_url=f"{VALET_BASE_URL}/observations/{self.series.name}",
            ),
        )

    def _period(self, observation_date: str) -> str:
        if self.series.date_format == "monthly":
            return observation_date[:7]
        if self.series.date_format == "annual":
            return observation_date[:4]
        return observation_date


class ValetClient:
    """Read-only client for series, groups and observations."""

    def __init__(
        self,
        *,
        base_url: str = VALET_BASE_URL,
        timeout: float = 30.0,
        retries: int = 2,
        backoff: float = 0.5,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._retries = retries
        self._backoff = backoff
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=timeout,
            headers={"Accept": "application/json", "User-Agent": "candata-mcp"},
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def get_series(self, series_id: str) -> SeriesDetail:
        body, _ = await self._get_json(f"series/{_name(series_id)}/json")
        return _series_detail(_dict(body, "seriesDetails"), series_id)

    async def get_group(self, group: str) -> GroupDetail:
        body, _ = await self._get_json(f"groups/{_name(group)}/json")
        detail = _dict(body, "groupDetail")
        series = _dict(detail, "groupSeries")
        return GroupDetail(
            name=_text(detail, "name", group),
            label=_text(detail, "label", ""),
            description=_text(detail, "description", ""),
            url=_text(detail, "link", f"{self._base_url}/groups/{group}"),
            frequency=_optional_text(_metadata(detail), "frequency"),
            series=tuple(
                SeriesSummary(
                    name=name,
                    label=_text(_dict(series, name), "label", ""),
                    url=_text(_dict(series, name), "link", f"{self._base_url}/series/{name}"),
                )
                for name in series
            ),
        )

    async def list_groups(self) -> tuple[GroupSummary, ...]:
        body, _ = await self._get_json("lists/groups/json")
        groups = _dict(body, "groups")
        return tuple(
            GroupSummary(
                name=name,
                label=_text(_dict(groups, name), "label", ""),
                description=_text(_dict(groups, name), "description", "").strip(),
                url=_text(_dict(groups, name), "link", f"{self._base_url}/groups/{name}"),
            )
            for name in groups
        )

    async def get_observations(
        self,
        series_id: str,
        *,
        start_date: date | str | None = None,
        end_date: date | str | None = None,
        recent: int | None = None,
    ) -> ObservationSet:
        name = _name(series_id)
        params: dict[str, str] = {}
        if recent is not None:
            if start_date is not None or end_date is not None:
                raise ValueError("recent cannot be combined with start_date or end_date")
            if recent < 1:
                raise ValueError("recent must be a positive integer")
            params["recent"] = str(recent)
        if start_date is not None:
            params["start_date"] = _iso_date(start_date, "start_date")
        if end_date is not None:
            params["end_date"] = _iso_date(end_date, "end_date")

        body, fetched_at = await self._get_json(f"observations/{name}/json", params)
        series = _series_detail(_dict(_dict(body, "seriesDetail"), name), name)
        rows = body.get("observations")
        if not isinstance(rows, list):
            raise ValetResponseError("response has no 'observations' list")
        observations = sorted(
            (_observation(row, name) for row in rows),  # pyright: ignore[reportUnknownVariableType]
            key=lambda o: o.date,
        )
        return ObservationSet(series, tuple(observations), fetched_at)

    async def get_policy_rate(
        self,
        *,
        start_date: date | str | None = None,
        end_date: date | str | None = None,
        recent: int | None = None,
    ) -> ObservationSet:
        return await self.get_observations(
            POLICY_RATE_SERIES, start_date=start_date, end_date=end_date, recent=recent
        )

    async def get_cpi(
        self,
        measure: str = "total",
        *,
        start_date: date | str | None = None,
        end_date: date | str | None = None,
        recent: int | None = None,
    ) -> ObservationSet:
        series_id = CPI_SERIES.get(measure)
        if series_id is None:
            raise ValueError(f"unknown CPI measure {measure!r}; choose from {sorted(CPI_SERIES)}")
        return await self.get_observations(
            series_id, start_date=start_date, end_date=end_date, recent=recent
        )

    async def _get_json(
        self, path: str, params: Mapping[str, str] | None = None
    ) -> tuple[dict[str, Any], str]:
        url = f"{self._base_url}/{path}"
        response: httpx.Response | None = None
        for attempt in range(self._retries + 1):
            last_attempt = attempt == self._retries
            try:
                response = await self._client.get(url, params=params)
            except httpx.TransportError as exc:
                if last_attempt:
                    raise ValetRequestError(f"request to {url} failed: {exc!r}") from exc
            else:
                if response.status_code not in _RETRY_STATUSES or last_attempt:
                    break
            await asyncio.sleep(self._backoff * 2**attempt)
        assert response is not None

        if response.status_code >= 400:
            message = _error_message(response)
            error = ValetNotFoundError if response.status_code == 404 else ValetHTTPError
            raise error(response.status_code, message)
        try:
            body: Any = response.json()
        except ValueError as exc:
            raise ValetResponseError(f"response from {url} is not valid JSON") from exc
        if not isinstance(body, dict):
            raise ValetResponseError(f"response from {url} is not a JSON object")
        return body, _fetched_at(response)  # pyright: ignore[reportUnknownVariableType]


def _name(value: str) -> str:
    if not _NAME.match(value):
        raise ValueError(f"invalid Valet name {value!r}")
    return quote(value)


def _iso_date(value: date | str, field: str) -> str:
    if isinstance(value, date):
        return value.isoformat()
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO date (YYYY-MM-DD), got {value!r}") from exc


def _error_message(response: httpx.Response) -> str:
    try:
        body: Any = response.json()
    except ValueError:
        return response.reason_phrase
    if isinstance(body, dict) and isinstance(body.get("message"), str):  # pyright: ignore[reportUnknownMemberType]
        return body["message"]  # pyright: ignore[reportUnknownVariableType]
    return response.reason_phrase


def _fetched_at(response: httpx.Response) -> str:
    header = response.headers.get("date")
    if header:
        try:
            return parsedate_to_datetime(header).astimezone(UTC).isoformat(timespec="seconds")
        except (TypeError, ValueError):
            pass
    return datetime.now(UTC).isoformat(timespec="seconds")


def _dict(source: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = source.get(key)
    if not isinstance(value, dict):
        raise ValetResponseError(f"response has no {key!r} object")
    return value  # pyright: ignore[reportUnknownVariableType]


def _text(source: Mapping[str, Any], key: str, default: str) -> str:
    value = source.get(key)
    return value if isinstance(value, str) else default


def _optional_text(source: Mapping[str, Any], key: str) -> str | None:
    value = source.get(key)
    return value if isinstance(value, str) else None


def _metadata(source: Mapping[str, Any]) -> Mapping[str, Any]:
    value = source.get("metadata")
    return value if isinstance(value, dict) else {}  # pyright: ignore[reportUnknownVariableType]


def _series_detail(raw: Mapping[str, Any], fallback_name: str) -> SeriesDetail:
    name = _text(raw, "name", fallback_name)
    metadata = _metadata(raw)
    return SeriesDetail(
        name=name,
        label=_text(raw, "label", name),
        description=_text(raw, "description", ""),
        frequency=_optional_text(metadata, "frequency"),
        unit=_optional_text(metadata, "unit"),
        date_format=_optional_text(raw, "dateFormat"),
        url=f"{VALET_BASE_URL}/series/{name}",
    )


def _observation(row: Any, series_id: str) -> Observation:
    if not isinstance(row, dict):
        raise ValetResponseError("observation row is not an object")
    when = row.get("d")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    cell = row.get(series_id)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    if not isinstance(when, str) or not isinstance(cell, dict):
        raise ValetResponseError(f"observation row is missing 'd' or {series_id!r}")
    raw = cell.get("v")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    if raw is None or raw == "":
        return Observation(when, None)
    try:
        return Observation(when, float(raw))  # pyright: ignore[reportUnknownArgumentType]
    except (TypeError, ValueError) as exc:
        raise ValetResponseError(f"non-numeric value {raw!r} on {when}") from exc
