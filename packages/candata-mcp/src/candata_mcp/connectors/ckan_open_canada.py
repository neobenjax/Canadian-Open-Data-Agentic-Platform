"""Async client for the Open Government Canada CKAN API (CAN-34).

Connects to open.canada.ca (CKAN v3 Action API) to provide bilingual dataset search,
package metadata inspection, and tabular CKAN DataStore query execution with
in-memory caching, rate-limiting resilience, and Two-Tier Citation Envelopes.
"""

# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false

from __future__ import annotations

import asyncio
import json
import random
import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from types import TracebackType
from typing import Any, Self

import httpx

from candata_mcp.citation import (
    BilingualTitle,
    CitationEnvelope,
    CoreVerificationTuple,
    MetadataEnrichment,
)

CKAN_BASE_URL = "https://open.canada.ca/data/api/3/action"
OPEN_CANADA_DATASET_URL = "https://open.canada.ca/data/en/dataset"
OPEN_CANADA_LICENCE_URL = "https://open.canada.ca/en/open-government-licence-canada"
PUBLISHER = "Open Government Canada"
# Relevance first, then recency. Recency alone ranks unrelated new tables above the match.
SEARCH_SORT = "score desc, metadata_modified desc"
# package_search page size when datastore_only must scan past non-DataStore datasets.
_SEARCH_PAGE_SIZE = 50
# Stop a datastore_only scan that matches nothing so it cannot walk the whole portal.
_SEARCH_SCAN_CAP = 1000
# datastore_search page size. Open Canada rejects larger pages on some resources.
DATASTORE_PAGE_SIZE = 100
# Full-table analytics refuse above this instead of aggregating a silent prefix.
DATASTORE_ANALYTICS_MAX_ROWS = 5000
DEFAULT_USER_AGENT = (
    "CanDataMCP/0.1.0 (CAN-34; +https://github.com/neobenjax/Canadian-Open-Data-Agentic-Platform)"
)

_ID_PATTERN = re.compile(r"^[A-Za-z0-9_\-\.]+$")
_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


class CKANError(Exception):
    """Base class for all errors raised by the CKAN client."""


class CKANRequestError(CKANError):
    """Network connection failure, timeout, or transport-level error."""


class CKANHTTPError(CKANError):
    """CKAN returned an HTTP error status code."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(f"CKAN returned HTTP {status_code}: {message}")
        self.status_code = status_code
        self.message = message


class CKANNotFoundError(CKANHTTPError):
    """The requested dataset, resource, or datastore table does not exist."""


class CKANResponseError(CKANError):
    """CKAN returned 200 OK or an unexpected body that indicates failure or non-JSON."""


class CKANResultTooLargeError(CKANError):
    """The DataStore table is larger than the analytics cap, so no aggregate was computed."""

    def __init__(self, resource_id: str, total: int, cap: int) -> None:
        super().__init__(
            f"CKAN DataStore resource {resource_id} has {total} rows, which exceeds the "
            f"analytics cap of {cap}. Aggregates were not computed over a partial table. "
            "Narrow the resource, or query a subset with query_open_canada_datastore."
        )
        self.resource_id = resource_id
        self.total = total
        self.cap = cap


def validate_identifier(identifier: str, field_name: str = "identifier") -> str:
    """Validate that an ID or name contains only safe URL-safe alphanumeric characters.

    Rejects empty strings, path traversals, or characters that could inject parameters.
    """
    clean = identifier.strip()
    if not clean or ".." in clean or not _ID_PATTERN.fullmatch(clean):
        raise ValueError(
            f"Invalid {field_name} {identifier!r}; must be a non-empty string of alphanumeric "
            "characters, hyphens, underscores, or periods without path traversal ('..')."
        )
    return clean


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


def _fetched_at(response: httpx.Response) -> tuple[str, str]:
    """Extract retrieval timestamp from HTTP Date header, falling back to UTC local clock."""
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


def _get_translated(
    data: Mapping[str, Any], key: str, fallback_key: str | None = None
) -> tuple[str, str | None]:
    """Extract bilingual (en, fr) values from CKAN fields (e.g. title_translated or title)."""
    translated = data.get(f"{key}_translated")
    if isinstance(translated, dict):
        en_val = translated.get("en") or ""
        fr_val = translated.get("fr") or None
        if en_val or fr_val:
            return (str(en_val), str(fr_val) if fr_val else None)

    direct = data.get(key)
    if isinstance(direct, dict):
        en_val = direct.get("en") or ""
        fr_val = direct.get("fr") or None
        return (str(en_val), str(fr_val) if fr_val else None)
    if isinstance(direct, str) and direct.strip():
        return (direct.strip(), None)

    if fallback_key:
        fb = data.get(fallback_key)
        if isinstance(fb, str) and fb.strip():
            return (fb.strip(), None)

    return ("", None)


def _coverage_period(start: object, end: object) -> tuple[str | None, str]:
    """Reference period from the catalogue's time_period_coverage fields only.

    Returns ``(period, source)``. ``source`` is ``time_period_coverage`` when either
    bound is present, and ``unknown`` when the publisher did not supply coverage.
    """
    start_text = start.strip() if isinstance(start, str) else ""
    end_text = end.strip() if isinstance(end, str) else ""
    if start_text and end_text:
        return f"{start_text}/{end_text}", "time_period_coverage"
    if start_text:
        return start_text, "time_period_coverage"
    if end_text:
        return end_text, "time_period_coverage"
    return None, "unknown"


def _dataset_summaries(raw_packages: object) -> list[CKANDatasetSummary]:
    """Build dataset summaries, recording resource ids that have DataStore active."""
    if not isinstance(raw_packages, list):
        return []
    summaries: list[CKANDatasetSummary] = []
    for pkg in raw_packages:
        if not isinstance(pkg, dict):
            continue
        pkg_id = str(pkg.get("id") or pkg.get("name") or "")
        if not pkg_id:
            continue
        title_en, title_fr = _get_translated(pkg, "title", "name")
        org_raw = pkg.get("organization")
        org: Mapping[str, Any] = org_raw if isinstance(org_raw, dict) else {}
        org_en, org_fr = _get_translated(org, "title", "name")
        raw_resources = pkg.get("resources", [])
        datastore_ids: list[str] = []
        if isinstance(raw_resources, list):
            for res in raw_resources:
                if isinstance(res, dict) and res.get("datastore_active") is True:
                    rid = str(res.get("id", ""))
                    if rid:
                        datastore_ids.append(rid)
        resource_count = raw_resources if isinstance(raw_resources, list) else []
        summaries.append(
            CKANDatasetSummary(
                package_id=pkg_id,
                name=str(pkg.get("name", pkg_id)),
                title_en=title_en,
                title_fr=title_fr,
                organization_en=org_en or None,
                organization_fr=org_fr or None,
                metadata_modified=(
                    pkg.get("metadata_modified")
                    if isinstance(pkg.get("metadata_modified"), str)
                    else None
                ),
                num_resources=int(pkg.get("num_resources", len(resource_count))),
                datastore_resource_ids=tuple(datastore_ids),
            )
        )
    return summaries


@dataclass(frozen=True, slots=True)
class CKANResourceSummary:
    """Summary of a single resource/distribution within a CKAN dataset."""

    resource_id: str
    name_en: str
    name_fr: str | None
    format: str
    datastore_active: bool
    url: str
    last_modified: str | None
    size: int | None


@dataclass(frozen=True, slots=True)
class CKANDatasetSummary:
    """Brief dataset descriptor returned in search results."""

    package_id: str
    name: str
    title_en: str
    title_fr: str | None
    organization_en: str | None
    organization_fr: str | None
    metadata_modified: str | None
    num_resources: int
    datastore_resource_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CKANDatasetDetail:
    """Detailed dataset metadata including resource inventory and license information."""

    package_id: str
    name: str
    title_en: str
    title_fr: str | None
    notes_en: str | None
    notes_fr: str | None
    organization_en: str | None
    organization_fr: str | None
    metadata_modified: str | None
    time_period_coverage_start: str | None
    time_period_coverage_end: str | None
    license_title: str | None
    license_url: str
    resources: tuple[CKANResourceSummary, ...]
    fetched_at: str = ""
    fetched_at_source: str = "server_date"

    def citation(self) -> CitationEnvelope:
        """Produce the Two-Tier Citation Envelope for the dataset."""
        publisher_name = (
            f"Open Government Canada / {self.organization_en}"
            if self.organization_en
            else PUBLISHER
        )
        period, period_source = _coverage_period(
            self.time_period_coverage_start, self.time_period_coverage_end
        )

        return CitationEnvelope(
            publisher=publisher_name,
            core=CoreVerificationTuple(
                table_id=self.package_id,
                vector_id=self.package_id,
                reference_period=period,
            ),
            enrichment=MetadataEnrichment(
                coordinate=None,
                release_or_revision_date=self.metadata_modified,
                bilingual_title=BilingualTitle(en=self.title_en, fr=self.title_fr),
                canonical_url=f"{OPEN_CANADA_DATASET_URL}/{self.package_id}",
                license_url=self.license_url,
                reference_period_source=period_source,
            ),
        )


@dataclass(frozen=True, slots=True)
class CKANSearchResult:
    """Catalog search response containing matching datasets and pagination metadata."""

    query: str
    total_results: int
    datasets: tuple[CKANDatasetSummary, ...]
    fetched_at: str
    fetched_at_source: str = "server_date"
    # False when datastore_only stopped after filling the page, so total_results
    # is only the number of matches seen so far.
    total_is_exact: bool = True


@dataclass(frozen=True, slots=True)
class CKANFieldSchema:
    """Schema descriptor for a single column in a CKAN DataStore resource."""

    field_id: str
    field_type: str


@dataclass(frozen=True, slots=True)
class CKANDataStoreResult:
    """Tabular records and schema retrieved from an active CKAN DataStore resource."""

    resource_id: str
    package_id: str | None
    title_en: str
    title_fr: str | None
    publisher_en: str
    fields: tuple[CKANFieldSchema, ...]
    records: tuple[dict[str, Any], ...]
    total_records: int
    release_or_revision_date: str | None
    fetched_at: str
    fetched_at_source: str = "server_date"
    license_url: str = OPEN_CANADA_LICENCE_URL
    time_period_coverage_start: str | None = None
    time_period_coverage_end: str | None = None

    def citation(self) -> CitationEnvelope:
        """Produce the Two-Tier Citation Envelope for the DataStore query.

        The reference period comes only from the dataset's ``time_period_coverage``
        fields. Column values, catalogue edit dates, and the literal ``current`` are
        not used.
        """
        if not self.package_id:
            raise CKANResponseError(
                f"DataStore resource {self.resource_id} has no package_id; "
                "refusing to cite it as table_id 'CKAN'."
            )
        period, period_source = _coverage_period(
            self.time_period_coverage_start, self.time_period_coverage_end
        )
        return CitationEnvelope(
            publisher=self.publisher_en,
            core=CoreVerificationTuple(
                table_id=self.package_id,
                vector_id=self.resource_id,
                reference_period=period,
            ),
            enrichment=MetadataEnrichment(
                coordinate=f"DataStore ({len(self.records)} rows)",
                release_or_revision_date=self.release_or_revision_date,
                bilingual_title=BilingualTitle(en=self.title_en, fr=self.title_fr),
                canonical_url=f"{OPEN_CANADA_DATASET_URL}/{self.package_id}",
                license_url=self.license_url,
                reference_period_source=period_source,
            ),
        )


class CKANClient:
    """Async read-only client for the Open Government Canada CKAN v3 Action API."""

    def __init__(
        self,
        *,
        base_url: str = CKAN_BASE_URL,
        timeout: float = 30.0,
        retries: int = 2,
        backoff: float = 0.5,
        max_concurrency: int = 5,
        cache_ttl_seconds: float = 60.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        parsed_base = base_url.rstrip("/").lower()
        if not parsed_base.startswith("https://"):
            allowed_local = ("http://localhost", "http://127.0.0.1", "http://testserver")
            if not any(parsed_base.startswith(p) for p in allowed_local):
                raise ValueError(f"CKAN base_url must use HTTPS in production (got {base_url!r})")

        self._base_url = base_url.rstrip("/")
        self._retries = retries
        self._backoff = backoff
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._cache_ttl = cache_ttl_seconds
        self._cache: dict[str, tuple[dict[str, Any], str, str, float]] = {}
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=timeout,
            headers={
                "Accept": "application/json",
                "User-Agent": DEFAULT_USER_AGENT,
            },
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
        """Close the underlying HTTP client session."""
        if self._owns_client:
            await self._client.aclose()

    def clear_cache(self) -> None:
        """Clear the in-memory response cache."""
        self._cache.clear()

    async def _post_action(
        self,
        action: str,
        payload: Mapping[str, Any],
        *,
        use_cache: bool = False,
    ) -> tuple[dict[str, Any], str, str]:
        """Execute a read-only POST request against a CKAN action endpoint with retry & backoff."""
        cache_key = f"{action}:{json.dumps(payload, sort_keys=True)}"
        now = time.monotonic()
        if use_cache and cache_key in self._cache:
            data, fetched_at, source, expire_at = self._cache[cache_key]
            if now < expire_at:
                return data, fetched_at, source

        url = f"{self._base_url}/{action}"
        last_exc: Exception | None = None

        for attempt in range(self._retries + 1):
            try:
                async with self._semaphore:
                    resp = await self._client.post(url, json=dict(payload))
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_exc = CKANRequestError(f"CKAN request to {action} failed: {exc}")
                if attempt < self._retries:
                    wait_sec = self._backoff * (2**attempt) + random.uniform(0.05, 0.2)
                    await asyncio.sleep(wait_sec)
                    continue
                raise last_exc from exc

            # Verify Content-Type to guard against HTML outage pages
            content_type = resp.headers.get("content-type", "").lower()
            if "application/json" not in content_type:
                if resp.status_code in _RETRY_STATUSES and attempt < self._retries:
                    retry_header = _parse_retry_after(resp.headers.get("retry-after"))
                    wait_sec = (
                        retry_header if retry_header is not None else (self._backoff * (2**attempt))
                    )
                    await asyncio.sleep(wait_sec)
                    continue
                raise CKANResponseError(
                    f"CKAN returned non-JSON content-type {content_type!r} "
                    f"(HTTP {resp.status_code})"
                )

            if resp.status_code == 404:
                raise CKANNotFoundError(404, f"CKAN endpoint or entity {action!r} not found.")

            if resp.status_code in _RETRY_STATUSES:
                if attempt < self._retries:
                    retry_header = _parse_retry_after(resp.headers.get("retry-after"))
                    wait_sec = (
                        retry_header
                        if retry_header is not None
                        else (self._backoff * (2**attempt) + random.uniform(0.05, 0.2))
                    )
                    await asyncio.sleep(wait_sec)
                    continue
                raise CKANHTTPError(resp.status_code, resp.text)

            if resp.is_error:
                raise CKANHTTPError(resp.status_code, resp.text)

            try:
                body: Any = resp.json()
            except ValueError as exc:
                raise CKANResponseError(f"Failed to parse CKAN JSON response: {exc}") from exc

            if not isinstance(body, dict):
                raise CKANResponseError(f"CKAN response body is not a JSON object: {type(body)}")

            if not body.get("success", False):
                err_info = body.get("error", "Unknown CKAN error")
                err_msg = json.dumps(err_info) if isinstance(err_info, dict) else str(err_info)
                if isinstance(err_info, dict) and err_info.get("__type") == "Not Found Error":
                    raise CKANNotFoundError(404, err_msg)
                raise CKANResponseError(f"CKAN API error in {action}: {err_msg}")

            result_data = body.get("result")
            if not isinstance(result_data, dict):
                raise CKANResponseError(f"CKAN 'result' is missing or not a dict in {action}")

            fetched_at_str, fetched_source = _fetched_at(resp)
            if use_cache:
                self._cache[cache_key] = (
                    result_data,
                    fetched_at_str,
                    fetched_source,
                    now + self._cache_ttl,
                )
            return result_data, fetched_at_str, fetched_source

        if last_exc:
            raise last_exc
        raise CKANRequestError(
            f"Failed to execute CKAN action {action} after {self._retries} retries"
        )

    async def search_datasets(
        self,
        query: str,
        *,
        organization: str | None = None,
        datastore_only: bool = False,
        limit: int = 10,
        offset: int = 0,
    ) -> CKANSearchResult:
        """Search the Open Government Canada catalog for datasets by keyword."""
        q = query.strip()
        if not q:
            raise ValueError("Search query cannot be empty.")

        limit = max(1, min(limit, 50))
        offset = max(0, offset)

        fq_parts: list[str] = []
        if organization:
            clean_org = validate_identifier(organization, "organization")
            fq_parts.append(f'organization:"{clean_org}"')
        # datastore_active is a resource property on this portal, not an indexed
        # package field, so it is filtered after the search returns.

        if not datastore_only:
            result, fetched_at, source = await self._post_action(
                "package_search",
                self._search_payload(q, rows=limit, start=offset, fq_parts=fq_parts),
            )
            summaries = _dataset_summaries(result.get("results", []))
            return CKANSearchResult(
                query=q,
                total_results=int(result.get("count", 0)),
                datasets=tuple(summaries),
                fetched_at=fetched_at,
                fetched_at_source=source,
            )

        needed = offset + limit
        matched: list[CKANDatasetSummary] = []
        start = 0
        fetched_at = ""
        source = "server_date"
        upstream_count = 0
        exhausted = False
        while len(matched) < needed and start < _SEARCH_SCAN_CAP:
            result, fetched_at, source = await self._post_action(
                "package_search",
                self._search_payload(q, rows=_SEARCH_PAGE_SIZE, start=start, fq_parts=fq_parts),
            )
            upstream_count = int(result.get("count", 0))
            raw_packages = result.get("results", [])
            page = raw_packages if isinstance(raw_packages, list) else []
            if not page:
                exhausted = True
                break
            for summary in _dataset_summaries(page):
                if summary.datastore_resource_ids:
                    matched.append(summary)
            start += len(page)
            if start >= upstream_count:
                exhausted = True
                break

        if not exhausted and not matched and start >= _SEARCH_SCAN_CAP:
            raise CKANResponseError(
                f"datastore_only scan stopped after {_SEARCH_SCAN_CAP} packages for {q!r} "
                "without finding a DataStore resource. Narrow the query."
            )

        return CKANSearchResult(
            query=q,
            total_results=len(matched),
            datasets=tuple(matched[offset : offset + limit]),
            fetched_at=fetched_at,
            fetched_at_source=source,
            total_is_exact=exhausted,
        )

    @staticmethod
    def _search_payload(
        query: str,
        *,
        rows: int,
        start: int,
        fq_parts: Sequence[str],
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "q": query,
            "rows": rows,
            "start": start,
            "sort": SEARCH_SORT,
        }
        if fq_parts:
            payload["fq"] = " AND ".join(fq_parts)
        return payload

    async def get_dataset(self, package_id: str) -> CKANDatasetDetail:
        """Fetch complete metadata and resource inventory for a specific dataset."""
        clean_id = validate_identifier(package_id, "package_id")
        result, fetched_at, source = await self._post_action(
            "package_show", {"id": clean_id}, use_cache=True
        )

        title_en, title_fr = _get_translated(result, "title", "name")
        notes_en, notes_fr = _get_translated(result, "notes")
        org_raw = result.get("organization")
        org: Mapping[str, Any] = org_raw if isinstance(org_raw, dict) else {}
        org_en, org_fr = _get_translated(org, "title", "name")

        raw_resources = result.get("resources", [])
        resources: list[CKANResourceSummary] = []
        if isinstance(raw_resources, list):
            for res in raw_resources:
                if not isinstance(res, dict):
                    continue
                r_id = str(res.get("id", ""))
                if not r_id:
                    continue
                r_name_en, r_name_fr = _get_translated(res, "name")
                resources.append(
                    CKANResourceSummary(
                        resource_id=r_id,
                        name_en=r_name_en or r_id,
                        name_fr=r_name_fr,
                        format=str(res.get("format", "")).upper(),
                        datastore_active=bool(res.get("datastore_active", False)),
                        url=str(res.get("url", "")),
                        last_modified=res.get("last_modified"),
                        size=int(res["size"]) if res.get("size") is not None else None,
                    )
                )

        lic_url = str(result.get("license_url") or OPEN_CANADA_LICENCE_URL)

        return CKANDatasetDetail(
            package_id=str(result.get("id", clean_id)),
            name=str(result.get("name", clean_id)),
            title_en=title_en,
            title_fr=title_fr,
            notes_en=notes_en or None,
            notes_fr=notes_fr or None,
            organization_en=org_en or None,
            organization_fr=org_fr or None,
            metadata_modified=result.get("metadata_modified"),
            time_period_coverage_start=result.get("time_period_coverage_start"),
            time_period_coverage_end=result.get("time_period_coverage_end"),
            license_title=result.get("license_title"),
            license_url=lic_url,
            resources=tuple(resources),
            fetched_at=fetched_at,
            fetched_at_source=source,
        )

    async def get_resource(self, resource_id: str) -> dict[str, Any]:
        """Fetch metadata for a single resource/distribution, discovering parent package ID."""
        clean_id = validate_identifier(resource_id, "resource_id")
        result, _, _ = await self._post_action("resource_show", {"id": clean_id}, use_cache=True)
        return result

    async def query_datastore(
        self,
        resource_id: str,
        *,
        package_id: str | None = None,
        q: str | None = None,
        filters: Mapping[str, Any] | None = None,
        fields: Sequence[str] | None = None,
        sort: str | None = None,
        limit: int = 25,
        offset: int = 0,
    ) -> CKANDataStoreResult:
        """Query one page of tabular records from an active CKAN DataStore resource."""
        clean_resource_id = validate_identifier(resource_id, "resource_id")
        limit = max(1, min(limit, DATASTORE_PAGE_SIZE))
        offset = max(0, offset)
        fields_schema, records, total, fetched_at, source = await self._datastore_page(
            clean_resource_id,
            q=q,
            filters=filters,
            fields=fields,
            sort=sort,
            limit=limit,
            offset=offset,
        )
        detail = await self._require_dataset(clean_resource_id, package_id)
        return self._datastore_result(
            clean_resource_id,
            detail,
            fields=fields_schema,
            records=records,
            total=total,
            fetched_at=fetched_at,
            source=source,
        )

    async def query_datastore_complete(
        self,
        resource_id: str,
        *,
        package_id: str | None = None,
        max_rows: int = DATASTORE_ANALYTICS_MAX_ROWS,
    ) -> CKANDataStoreResult:
        """Fetch every DataStore row, or refuse when the table exceeds ``max_rows``.

        Aggregates must not run on a silent prefix. The first page reports ``total``;
        a total above the cap raises :class:`CKANResultTooLargeError` before further
        pages are requested.
        """
        clean_resource_id = validate_identifier(resource_id, "resource_id")
        cap = max(1, max_rows)
        fields_schema, records, total, fetched_at, source = await self._datastore_page(
            clean_resource_id,
            limit=DATASTORE_PAGE_SIZE,
            offset=0,
        )
        if total > cap:
            raise CKANResultTooLargeError(clean_resource_id, total, cap)

        collected = list(records)
        offset = len(records)
        while offset < total:
            _, page_records, page_total, fetched_at, source = await self._datastore_page(
                clean_resource_id,
                limit=DATASTORE_PAGE_SIZE,
                offset=offset,
            )
            if not page_records:
                raise CKANResponseError(
                    f"datastore_search for {clean_resource_id} stopped at offset {offset} "
                    f"before the reported total of {total} rows."
                )
            if page_total != total:
                raise CKANResponseError(
                    f"datastore_search for {clean_resource_id} changed total from {total} "
                    f"to {page_total} while paging."
                )
            collected.extend(page_records)
            offset += len(page_records)
            if len(collected) > cap:
                raise CKANResultTooLargeError(clean_resource_id, len(collected), cap)

        if len(collected) != total:
            raise CKANResponseError(
                f"datastore_search for {clean_resource_id} returned {len(collected)} rows, "
                f"not the reported total of {total}."
            )

        detail = await self._require_dataset(clean_resource_id, package_id)
        return self._datastore_result(
            clean_resource_id,
            detail,
            fields=fields_schema,
            records=collected,
            total=total,
            fetched_at=fetched_at,
            source=source,
        )

    async def _datastore_page(
        self,
        resource_id: str,
        *,
        q: str | None = None,
        filters: Mapping[str, Any] | None = None,
        fields: Sequence[str] | None = None,
        sort: str | None = None,
        limit: int,
        offset: int,
    ) -> tuple[tuple[CKANFieldSchema, ...], list[dict[str, Any]], int, str, str]:
        payload: dict[str, Any] = {
            "resource_id": resource_id,
            "limit": limit,
            "offset": offset,
        }
        if q:
            payload["q"] = q.strip()
        if filters:
            payload["filters"] = dict(filters)
        if fields:
            payload["fields"] = list(fields)
        if sort:
            payload["sort"] = sort.strip()

        result, fetched_at, source = await self._post_action("datastore_search", payload)
        raw_fields = result.get("fields", [])
        field_schemas: list[CKANFieldSchema] = []
        if isinstance(raw_fields, list):
            for field in raw_fields:
                if isinstance(field, dict) and "id" in field:
                    field_schemas.append(
                        CKANFieldSchema(
                            field_id=str(field["id"]),
                            field_type=str(field.get("type", "text")),
                        )
                    )
        raw_records = result.get("records", [])
        records: list[dict[str, Any]] = []
        if isinstance(raw_records, list):
            for record in raw_records:
                if isinstance(record, dict):
                    records.append(dict(record))
        total = int(result.get("total", len(records)))
        return tuple(field_schemas), records, total, fetched_at, source

    async def _require_dataset(self, resource_id: str, package_id: str | None) -> CKANDatasetDetail:
        """Resolve the parent dataset. Lookup failures propagate; they are not swallowed."""
        clean_package_id = validate_identifier(package_id, "package_id") if package_id else None
        if clean_package_id is None:
            res_meta = await self.get_resource(resource_id)
            parent_id = res_meta.get("package_id")
            if not isinstance(parent_id, str) or not parent_id.strip():
                raise CKANResponseError(
                    f"resource_show for {resource_id!r} did not include a package_id; "
                    "refusing to cite the table without its dataset."
                )
            clean_package_id = validate_identifier(parent_id, "package_id")
        return await self.get_dataset(clean_package_id)

    @staticmethod
    def _datastore_result(
        resource_id: str,
        detail: CKANDatasetDetail,
        *,
        fields: tuple[CKANFieldSchema, ...],
        records: list[dict[str, Any]],
        total: int,
        fetched_at: str,
        source: str,
    ) -> CKANDataStoreResult:
        publisher = (
            f"Open Government Canada / {detail.organization_en}"
            if detail.organization_en
            else PUBLISHER
        )
        return CKANDataStoreResult(
            resource_id=resource_id,
            package_id=detail.package_id,
            title_en=detail.title_en or detail.name,
            title_fr=detail.title_fr,
            publisher_en=publisher,
            fields=fields,
            records=tuple(records),
            total_records=total,
            release_or_revision_date=detail.metadata_modified,
            fetched_at=fetched_at,
            fetched_at_source=source,
            license_url=detail.license_url,
            time_period_coverage_start=detail.time_period_coverage_start,
            time_period_coverage_end=detail.time_period_coverage_end,
        )
