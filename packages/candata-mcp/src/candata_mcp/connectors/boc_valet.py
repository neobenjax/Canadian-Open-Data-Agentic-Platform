"""Async client for the Bank of Canada Valet API (CAN-12 / CAN-17 Hardening).

Valet publishes series values, labels and units but no release or revision timestamp and no
French labels, so ``release_or_revision_date`` is left empty rather than guessed and French
titles come only from the sourced ``FRENCH_TITLES`` table. Every result carries
``fetched_at`` (the server's HTTP ``Date``) paired with ``fetched_at_source`` ("server_date"
or "local_clock") so a figure can still be pinned to the moment and provenance of retrieval.
"""

from __future__ import annotations

import asyncio
import random
import re
import time
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
VALET_TERMS_URL = "https://www.bankofcanada.ca/terms/"
PUBLISHER = "Bank of Canada"
TABLE_ID = "Valet"
DEFAULT_USER_AGENT = (
    "CanDataMCP/0.1.0 (+https://github.com/neobenjax/Canadian-Open-Data-Agentic-Platform)"
)

POLICY_RATE_SERIES = "V39079"

# The inflation target is a monetary policy framework agreement, not a Valet series, so it is
# exposed as constants instead of being fetched. Source:
# https://www.bankofcanada.ca/core-functions/monetary-policy/inflation/
# The current agreement runs to the end of 2026; re-verify when the renewal is announced.
INFLATION_TARGET_PCT: float = 2.0
INFLATION_TARGET_RANGE: tuple[float, float] = (1.0, 3.0)

# Valet has no ``?lang=fr``, so French titles are the Bank's own published terms, by series.
FRENCH_TITLES: Mapping[str, str] = {
    POLICY_RATE_SERIES: "Taux cible du financement à un jour",
}

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
    """Observations for one series, oldest first, with the moment and source of retrieval."""

    series: SeriesDetail
    observations: tuple[Observation, ...]
    fetched_at: str
    fetched_at_source: str = "server_date"
    license_url: str = VALET_TERMS_URL

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
                bilingual_title=BilingualTitle(
                    en=self.series.label, fr=FRENCH_TITLES.get(self.series.name)
                ),
                canonical_url=f"{VALET_BASE_URL}/observations/{self.series.name}",
                license_url=self.license_url,
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
        max_concurrency: int = 5,
        cache_ttl_seconds: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        parsed_base = base_url.rstrip("/").lower()
        if not parsed_base.startswith("https://"):
            allowed_local = (
                "http://localhost",
                "http://127.0.0.1",
                "http://testserver",
            )
            if not any(parsed_base.startswith(prefix) for prefix in allowed_local):
                raise ValueError(f"Valet base_url must use HTTPS in production (got {base_url!r})")

        self._base_url = base_url.rstrip("/")
        self._retries = retries
        self._backoff = backoff
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._cache_ttl = cache_ttl_seconds
        self._cache: dict[str, tuple[dict[str, Any], str, str, float]] = {}
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=timeout,
            headers={"Accept": "application/json", "User-Agent": DEFAULT_USER_AGENT},
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

    def clear_cache(self) -> None:
        """Clear the in-memory response cache."""
        self._cache.clear()

    async def get_series(self, series_id: str) -> SeriesDetail:
        body, _, _ = await self._get_json(f"series/{_name(series_id)}/json")
        return _series_detail(_dict(body, "seriesDetails"), series_id)

    async def get_group(self, group: str) -> GroupDetail:
        body, _, _ = await self._get_json(f"groups/{_name(group)}/json")
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
        body, _, _ = await self._get_json("lists/groups/json")
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
        elif start_date is None and end_date is None:
            # Default to recent=10 to bound history and avoid unbounded data dumps (V-F3)
            params["recent"] = "10"

        if start_date is not None:
            params["start_date"] = _iso_date(start_date, "start_date")
        if end_date is not None:
            params["end_date"] = _iso_date(end_date, "end_date")

        body, fetched_at, fetched_at_source = await self._get_json(
            f"observations/{name}/json", params
        )
        series = _series_detail(_dict(_dict(body, "seriesDetail"), name), name)
        rows = body.get("observations")
        if not isinstance(rows, list):
            raise ValetResponseError("response has no 'observations' list")
        observations = sorted(
            (_observation(row, name) for row in rows),  # pyright: ignore[reportUnknownVariableType]
            key=lambda o: o.date,
        )
        return ObservationSet(
            series, tuple(observations), fetched_at, fetched_at_source, VALET_TERMS_URL
        )

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
    ) -> tuple[dict[str, Any], str, str]:
        url = f"{self._base_url}/{path}"
        cache_key = f"{url}?{sorted(params.items()) if params else ''}"
        now_mono = time.monotonic()
        if cache_key in self._cache:
            body, fetched_at, source, cached_time = self._cache[cache_key]
            if now_mono - cached_time < self._cache_ttl:
                return body, fetched_at, source

        response: httpx.Response | None = None
        for attempt in range(self._retries + 1):
            last_attempt = attempt == self._retries
            try:
                async with self._semaphore:
                    response = await self._client.get(url, params=params)
            except httpx.TransportError as exc:
                if last_attempt:
                    raise ValetRequestError(f"request to {url} failed: {exc!r}") from exc
            else:
                if response.status_code not in _RETRY_STATUSES or last_attempt:
                    break

            sleep_time: float
            if response is not None and response.status_code in (429, 503):
                retry_header = response.headers.get("retry-after")
                parsed_wait = _parse_retry_after(retry_header)
                if parsed_wait is not None:
                    sleep_time = min(parsed_wait, 60.0) + (
                        0.0 if self._backoff == 0 else random.uniform(0.01, 0.05)
                    )
                else:
                    sleep_time = self._backoff * (2**attempt)
            else:
                sleep_time = self._backoff * (2**attempt)

            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

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

        fetched_at, fetched_at_source = _fetched_at(response)
        self._cache[cache_key] = (body, fetched_at, fetched_at_source, now_mono)
        return body, fetched_at, fetched_at_source  # pyright: ignore[reportUnknownVariableType]


def _name(value: str) -> str:
    if not _NAME.fullmatch(value):
        raise ValueError(f"invalid Valet name {value!r}")
    return quote(value)


def _iso_date(value: date | str, field: str) -> str:
    if isinstance(value, date):
        return value.isoformat()
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO date (YYYY-MM-DD), got {value!r}") from exc


def _parse_retry_after(header_val: str | None) -> float | None:
    """Parse RFC 7231 Retry-After header (delta-seconds or IMF-fixdate HTTP-date)."""
    if not header_val:
        return None
    val = header_val.strip()
    if val.isdigit():
        return float(val)
    try:
        dt = parsedate_to_datetime(val)
        delta = (dt - datetime.now(UTC)).total_seconds()
        return max(0.0, delta)
    except (TypeError, ValueError):
        return None


def _error_message(response: httpx.Response) -> str:
    try:
        body: Any = response.json()
    except ValueError:
        return response.reason_phrase
    if isinstance(body, dict) and isinstance(body.get("message"), str):  # pyright: ignore[reportUnknownMemberType]
        return body["message"]  # pyright: ignore[reportUnknownVariableType]
    return response.reason_phrase


def _fetched_at(response: httpx.Response) -> tuple[str, str]:
    header = response.headers.get("date")
    if header:
        try:
            return (
                parsedate_to_datetime(header).astimezone(UTC).isoformat(timespec="seconds"),
                "server_date",
            )
        except (TypeError, ValueError):
            pass
    return (datetime.now(UTC).isoformat(timespec="seconds"), "local_clock")


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
