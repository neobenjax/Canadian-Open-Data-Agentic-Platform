"""Async client for the Statistics Canada Web Data Service (WDS) API (CAN-11 / CAN-17 Hardening).

Provides metadata discovery, coordinate resolution, observation slicing, vector queries,
in-memory TTL metadata caching, catalog search, and Two-Tier Citation Envelope generation
matching the official Canadian Open Data Agentic Platform benchmark standards.
"""

from __future__ import annotations

import asyncio
import re
import time
import unicodedata
from collections.abc import Callable, Mapping, Sequence
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
from candata_mcp.connectors.statcan_codesets import (
    STATCAN_UOM_EN,
    STATCAN_UOM_FR,
)

STATCAN_WDS_BASE_URL = "https://www150.statcan.gc.ca/t1/wds/rest"
STATCAN_LICENCE_URL = "https://www.statcan.gc.ca/en/reference/licence"
PUBLISHER = "Statistics Canada"
DEFAULT_USER_AGENT = (
    "CanDataMCP/0.1 (CAN-11; +https://github.com/neobenjax/Canadian-Open-Data-Agentic-Platform)"
)


def _normalize_search_term(text: str) -> str:
    """Normalize unicode accents and lowercase for robust fuzzy search."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})

FREQUENCY_NAMES: Mapping[int, str] = {
    1: "daily",
    2: "weekly",
    4: "bi-weekly",
    6: "monthly",
    7: "quarterly",
    9: "semi-annual",
    12: "annual",
}


class StatCanError(Exception):
    """Base class for all errors raised by the Statistics Canada WDS client."""


class StatCanRequestError(StatCanError):
    """Transport error, network timeout, or connection failure."""


class StatCanHTTPError(StatCanError):
    """StatCan WDS returned an HTTP error status code."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(f"StatCan WDS returned HTTP {status_code}: {message}")
        self.status_code = status_code
        self.message = message


class StatCanNotFoundError(StatCanHTTPError):
    """The requested product, vector, or table does not exist (404)."""


class StatCanResponseError(StatCanError):
    """StatCan WDS returned 200 OK but the payload indicated failure or invalid JSON."""


class StatCanUnavailableError(StatCanError):
    """Statistics Canada WDS catalog service is temporarily unreachable or undergoing
    maintenance."""

    def __init__(self, message: str, retry_after: int = 30) -> None:
        super().__init__(message)
        self.message = message
        self.retry_after = retry_after


class StatCanMemberNotFoundError(StatCanError):
    """A dimension member name could not be resolved in the cube metadata."""


class StatCanAmbiguousMemberError(StatCanError):
    """A dimension member name matched multiple candidate members in the cube (Guardrail 6)."""

    def __init__(
        self,
        member_name: str,
        dimension_position: int,
        dimension_name: str,
        product_id: int,
        candidates: Sequence[DimensionMember],
    ) -> None:
        self.member_name: str = member_name
        self.dimension_position: int = dimension_position
        self.dimension_name: str = dimension_name
        self.product_id: int = product_id
        self.candidates: tuple[DimensionMember, ...] = tuple(candidates)
        self.candidate_ids: tuple[int, ...] = tuple(m.member_id for m in candidates)
        msg = (
            f"ambiguous member name {member_name!r}: multiple members match in dimension "
            f"{dimension_position} ({dimension_name!r}) of table {product_id}: "
            f"candidates={list(self.candidate_ids)}"
        )
        super().__init__(msg)


def format_table_id(product_id: int | str) -> str:
    """Format an 8-digit or 10-digit StatCan product ID as a standard hyphenated table ID.

    Example: 18100004 -> "18-10-0004-01"
    """
    s = str(product_id).strip()
    if len(s) == 8:
        return f"{s[0:2]}-{s[2:4]}-{s[4:8]}-01"
    if len(s) == 10:
        return f"{s[0:2]}-{s[2:4]}-{s[4:8]}-{s[8:10]}"
    return s


def normalize_vector_id(vector_id: int | str) -> int:
    """Normalize a vector ID (e.g. 'v41690973' or 41690973) to integer 41690973."""
    if isinstance(vector_id, int):
        if vector_id <= 0:
            raise ValueError(f"invalid vector ID {vector_id!r}; must be positive")
        return vector_id
    cleaned = vector_id.strip().lstrip("vV")
    if not cleaned.isdigit() or int(cleaned) <= 0:
        raise ValueError(
            f"invalid vector ID {vector_id!r}; must be positive numeric or 'v'-prefixed"
        )
    return int(cleaned)


def normalize_product_id(product_id: int | str) -> int:
    """Normalize a product ID (e.g. '1810000401' or 18100004) to an 8-digit integer."""
    s = str(product_id).strip().replace("-", "")
    if len(s) == 10 and s.endswith("01"):
        s = s[:8]
    if not s.isdigit() or int(s) <= 0:
        raise ValueError(f"invalid product ID {product_id!r}; must be positive")
    return int(s)


def normalize_coordinate(coordinate: str) -> str:
    """Normalize a StatCan coordinate string to standard 10-part format.

    Pads short coordinates with zeroes (e.g. '23' -> '23.0.0.0.0.0.0.0.0.0')
    to prevent WDS HTTP 406 invalid coordinate errors.
    """
    cleaned = coordinate.strip()
    if not cleaned:
        raise ValueError("coordinate cannot be empty")
    parts = cleaned.split(".")
    for p in parts:
        if not p.isdigit():
            raise ValueError(f"invalid coordinate segment {p!r} in {coordinate!r}; must be numeric")
    if len(parts) > 10:
        raise ValueError(f"coordinate {coordinate!r} has {len(parts)} parts; maximum is 10")
    padded = parts + ["0"] * (10 - len(parts))
    return ".".join(padded)


@dataclass(frozen=True, slots=True)
class DimensionMember:
    member_id: int
    parent_member_id: int | None
    name_en: str
    name_fr: str | None
    member_uom_code: int | None


@dataclass(frozen=True, slots=True)
class Dimension:
    position_id: int
    name_en: str
    name_fr: str | None
    has_uom: bool
    members: tuple[DimensionMember, ...]


@dataclass(frozen=True, slots=True)
class CubeMetadata:
    product_id: int
    cansim_id: str | None
    title_en: str
    title_fr: str | None
    start_date: str | None
    end_date: str | None
    release_time: str | None
    frequency_code: int
    frequency_name: str
    dimensions: tuple[Dimension, ...]


@dataclass(frozen=True, slots=True)
class CubeSummary:
    """Token-budgeted summary representation of a Statistics Canada data cube."""

    product_id: int
    table_id: str
    cansim_id: str | None
    title_en: str
    title_fr: str | None
    start_date: str | None
    end_date: str | None
    release_time: str | None
    frequency_code: int
    frequency_name: str


@dataclass(frozen=True, slots=True)
class CubeSearchResult:
    """Token-budgeted search result with unpaginated match count."""

    total_results: int
    cubes: tuple[CubeSummary, ...]

    def __iter__(self):
        return iter(self.cubes)

    def __len__(self) -> int:
        return len(self.cubes)

    def __getitem__(self, index: int) -> CubeSummary:
        return self.cubes[index]


@dataclass(frozen=True, slots=True)
class Observation:
    ref_per: str
    value: float | None
    decimals: int | None
    release_time: str | None
    scalar_factor_code: int | None
    frequency_code: int | None
    status_code: int | None = None
    symbol_code: int | None = None


@dataclass(frozen=True, slots=True)
class StatCanSeriesResult:
    """Result for one series/coordinate slice, chronologically ordered (oldest first)."""

    product_id: int
    coordinate: str
    vector_id: int
    title_en: str
    title_fr: str | None
    frequency_code: int
    unit: str | None
    observations: tuple[Observation, ...]
    fetched_at: str
    series_title_en: str | None = None
    series_title_fr: str | None = None
    unit_code: int | None = None

    def citation(self) -> CitationEnvelope:
        if not self.observations:
            raise ValueError(f"no observations to cite for vector v{self.vector_id}")
        first, last = self.observations[0], self.observations[-1]
        first_per = self._period(first.ref_per, self.frequency_code)
        last_per = self._period(last.ref_per, self.frequency_code)
        period = first_per if first_per == last_per else f"{first_per}/{last_per}"

        # StatCan requires release_or_revision_date to be populated
        release_date = last.release_time or first.release_time

        return CitationEnvelope(
            publisher=PUBLISHER,
            core=CoreVerificationTuple(
                table_id=format_table_id(self.product_id),
                vector_id=f"v{self.vector_id}",
                reference_period=period,
            ),
            enrichment=MetadataEnrichment(
                coordinate=self.coordinate,
                release_or_revision_date=release_date,
                bilingual_title=BilingualTitle(en=self.title_en, fr=self.title_fr),
                canonical_url=(
                    f"https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid={self.product_id}01"
                ),
                license_url=STATCAN_LICENCE_URL,
            ),
        )

    @staticmethod
    def _period(ref_per: str, frequency_code: int) -> str:
        if frequency_code == 12:  # annual
            return ref_per[:4]
        if frequency_code == 6:  # monthly
            return ref_per[:7]
        if frequency_code == 1:  # daily
            return ref_per[:10]
        return ref_per[:7] if len(ref_per) >= 7 else ref_per


@dataclass(frozen=True, slots=True)
class SeriesInfo:
    vector_id: int
    product_id: int
    coordinate: str
    frequency_code: int
    scalar_factor_code: int | None
    decimals: int | None
    title_en: str
    title_fr: str | None
    member_uom_code: int | None
    unit: str | None = None


class StatCanClient:
    """Async client for Statistics Canada Web Data Service (WDS) API."""

    @classmethod
    def _resolve_series_details_from_coord(
        cls,
        meta: CubeMetadata,
        coord: str,
        uom_resolver: Callable[[int | None], str | None] | None = None,
    ) -> tuple[str | None, str | None, str | None, int | None]:
        """Resolve series titles (en, fr) and unit of measure name/code from coordinate."""
        if not coord:
            return None, None, None, None
        parts = coord.split(".")
        titles_en: list[str] = []
        titles_fr: list[str] = []
        uom_name: str | None = None
        uom_code: int | None = None

        for dim in meta.dimensions:
            idx = dim.position_id - 1
            if 0 <= idx < len(parts):
                part_val = parts[idx]
                if part_val.isdigit():
                    m_id = int(part_val)
                    if m_id > 0:
                        member = next((m for m in dim.members if m.member_id == m_id), None)
                        if member:
                            if member.name_en:
                                titles_en.append(member.name_en)
                            if member.name_fr:
                                titles_fr.append(member.name_fr)
                            if member.member_uom_code and uom_code is None:
                                uom_code = member.member_uom_code
                                if uom_resolver is not None:
                                    uom_name = uom_resolver(uom_code)
                                else:
                                    uom_name = STATCAN_UOM_EN.get(uom_code)

        s_title_en = "; ".join(titles_en) if titles_en else None
        s_title_fr = "; ".join(titles_fr) if titles_fr else None
        return s_title_en, s_title_fr, uom_name, uom_code

    def __init__(
        self,
        *,
        base_url: str = STATCAN_WDS_BASE_URL,
        timeout: float = 30.0,
        retries: int = 2,
        backoff: float = 0.5,
        metadata_ttl_seconds: float = 3600.0,
        cubes_list_ttl_seconds: float = 86400.0,
        codesets_ttl_seconds: float = 86400.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._retries = retries
        self._backoff = backoff
        self._metadata_ttl = metadata_ttl_seconds
        self._cubes_list_ttl = cubes_list_ttl_seconds
        self._codesets_ttl = codesets_ttl_seconds
        self._metadata_cache: dict[int, tuple[CubeMetadata, float]] = {}
        self._cubes_list_cache: tuple[list[dict[str, Any]], float] | None = None
        self._uom_cache: dict[str, tuple[dict[int, str], float]] = {}
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
        """Clear in-memory metadata, catalog, and codesets caches."""
        self._metadata_cache.clear()
        self._cubes_list_cache = None
        self._uom_cache.clear()

    async def get_uom_codes(
        self, *, lang: str = "en", bypass_cache: bool = False
    ) -> Mapping[int, str]:
        """Fetch official UOM codes from WDS getCodeSets with TTL caching and snapshot fallback."""
        now = time.monotonic()
        if not bypass_cache and lang in self._uom_cache:
            cached_data, cached_time = self._uom_cache[lang]
            if now - cached_time < self._codesets_ttl:
                return cached_data

        url = f"{self._base_url}/getCodeSets"
        try:
            response = await self._client.get(url)
            if response.status_code == 200:
                raw = response.json()
                root = _dict(raw)
                if root.get("status") == "SUCCESS":
                    obj = _dict(root.get("object"))
                    uom_list = _optional_dict_list(obj.get("uom"))
                    en_map: dict[int, str] = {}
                    fr_map: dict[int, str] = {}
                    for u in uom_list:
                        c = _optional_int(u, "memberUomCode")
                        if c is not None and c > 0:
                            en_val = _optional_text(u, "memberUomEn")
                            fr_val = _optional_text(u, "memberUomFr")
                            if en_val:
                                en_map[c] = en_val
                            if fr_val:
                                fr_map[c] = fr_val
                    if en_map:
                        self._uom_cache["en"] = (en_map, now)
                    if fr_map:
                        self._uom_cache["fr"] = (fr_map, now)
                    if lang == "fr" and fr_map:
                        return fr_map
                    if en_map:
                        return en_map
        except Exception:
            pass

        snapshot = STATCAN_UOM_FR if lang == "fr" else STATCAN_UOM_EN
        self._uom_cache[lang] = (dict(snapshot), now)
        return snapshot

    def get_uom_name(self, uom_code: int | None, *, lang: str = "en") -> str | None:
        """Resolve a UOM code to its official name (en/fr).

        Returns None if uom_code is None, 0, or unmapped, strictly avoiding synthetic labels.
        """
        if uom_code is None or uom_code <= 0:
            return None
        if lang in self._uom_cache:
            codes, _ = self._uom_cache[lang]
            if uom_code in codes:
                return codes[uom_code]
        snapshot = STATCAN_UOM_FR if lang == "fr" else STATCAN_UOM_EN
        return snapshot.get(uom_code)

    async def get_cube_metadata(
        self, product_id: int | str, *, bypass_cache: bool = False
    ) -> CubeMetadata:
        """Fetch cube metadata, dimensions, members, and publication dates with TTL caching."""
        pid = normalize_product_id(product_id)
        now = time.monotonic()

        if not bypass_cache and pid in self._metadata_cache:
            meta, cached_time = self._metadata_cache[pid]
            if now - cached_time < self._metadata_ttl:
                return meta

        body = [{"productId": pid}]
        response_data, _ = await self._post_json("getCubeMetadata", body)
        cube_obj = self._extract_first_success_object(response_data, f"product {pid}")

        meta = self._parse_cube_metadata(cube_obj, pid)
        self._metadata_cache[pid] = (meta, now)
        return meta

    async def get_all_cubes_list_lite(self, *, bypass_cache: bool = False) -> list[dict[str, Any]]:
        """Fetch all cubes lite summary list from WDS with in-memory caching.

        Fails loud with StatCanUnavailableError when the WDS catalog service is unreachable
        or undergoing maintenance, preventing fabricated offline provenance citations (Guardrail 6).
        """
        now = time.monotonic()
        if not bypass_cache and self._cubes_list_cache is not None:
            cached_data, cached_time = self._cubes_list_cache
            if now - cached_time < self._cubes_list_ttl:
                return cached_data

        url = f"{self._base_url}/getAllCubesListLite"
        try:
            response = await self._client.get(url)
        except Exception as exc:
            raise StatCanUnavailableError(
                f"Statistics Canada WDS catalog service is temporarily unreachable: {exc}. "
                "Please retry shortly or query by product_id directly using get_cube_dimensions.",
                retry_after=30,
            ) from exc

        if response.status_code == 200:
            try:
                raw = response.json()
            except Exception as exc:
                raise StatCanUnavailableError(
                    f"StatCan WDS returned invalid JSON for catalog: {exc}",
                    retry_after=30,
                ) from exc
            if isinstance(raw, list) and raw:
                cubes = [c for c in _dict_list(raw) if "productId" in c]
                self._cubes_list_cache = (cubes, now)
                return cubes

        if response.status_code == 409:
            raise StatCanUnavailableError(
                "Statistics Canada WDS is currently in its daily scheduled maintenance "
                "window (00:00-08:30 ET).",
                retry_after=300,
            )

        raise StatCanUnavailableError(
            f"StatCan WDS catalog request failed with HTTP {response.status_code}. "
            "Please retry shortly or query by product_id directly using get_cube_dimensions.",
            retry_after=30,
        )

    async def search_cubes(
        self,
        query: str,
        *,
        limit: int = 10,
        offset: int = 0,
        bypass_cache: bool = False,
    ) -> CubeSearchResult:
        """Search Statistics Canada data cubes by keyword with token-budgeted pagination.

        Tokenizes queries on whitespace and matches all terms on word boundaries
        (e.g. 'toronto rent' matches 34-10-0133-01, while 'rent' does not match 'current').
        Returns true total match count alongside paginated results.
        """
        cubes = await self.get_all_cubes_list_lite(bypass_cache=bypass_cache)
        tokens = [_normalize_search_term(t) for t in query.strip().split() if t]
        if not tokens:
            return CubeSearchResult(total_results=0, cubes=())

        token_patterns = [re.compile(rf"\b{re.escape(t)}", re.IGNORECASE) for t in tokens]

        matches: list[CubeSummary] = []
        for c in cubes:
            pid = normalize_product_id(str(c.get("productId", 0)))
            title_en = str(c.get("cubeTitleEn", ""))
            title_fr = c.get("cubeTitleFr")
            cansim = c.get("cansimId")
            searchable = _normalize_search_term(f"{pid} {title_en} {title_fr or ''} {cansim or ''}")

            if all(p.search(searchable) for p in token_patterns):
                freq_code = _required_int(c, "frequencyCode")
                matches.append(
                    CubeSummary(
                        product_id=pid,
                        table_id=format_table_id(pid),
                        cansim_id=str(cansim) if cansim else None,
                        title_en=title_en,
                        title_fr=str(title_fr) if title_fr else None,
                        start_date=_optional_text(c, "cubeStartDate"),
                        end_date=_optional_text(c, "cubeEndDate"),
                        release_time=_optional_text(c, "releaseTime"),
                        frequency_code=freq_code,
                        frequency_name=FREQUENCY_NAMES.get(freq_code, f"code_{freq_code}"),
                    )
                )

        total_results = len(matches)
        paged_cubes = tuple(matches[offset : offset + limit])
        return CubeSearchResult(total_results=total_results, cubes=paged_cubes)

    async def resolve_coordinate(self, product_id: int | str, member_names: Sequence[str]) -> str:
        """Resolve human-readable dimension member names into a StatCan 10-part coordinate string.

        Fails loud with StatCanAmbiguousMemberError if multiple candidate members share the
        same name within a dimension (e.g. duplicate municipality/CMA names, Guardrail 6).

        Example: resolve_coordinate(18100004, ["Canada", "All-items"]) -> "2.2.0.0.0.0.0.0.0.0"
        """
        meta = await self.get_cube_metadata(product_id)
        member_ids: list[int] = []

        for pos, name in enumerate(member_names, start=1):
            dim = next((d for d in meta.dimensions if d.position_id == pos), None)
            if dim is None:
                raise StatCanMemberNotFoundError(
                    f"dimension position {pos} does not exist in table {meta.product_id}"
                )
            name_norm = name.strip().lower()
            matches = [
                m
                for m in dim.members
                if m.name_en.strip().lower() == name_norm
                or (m.name_fr and m.name_fr.strip().lower() == name_norm)
            ]
            if not matches:
                raise StatCanMemberNotFoundError(
                    f"member {name!r} not found in dimension {pos} "
                    f"({dim.name_en!r}) of table {meta.product_id}"
                )
            if len(matches) > 1:
                raise StatCanAmbiguousMemberError(
                    member_name=name,
                    dimension_position=pos,
                    dimension_name=dim.name_en,
                    product_id=meta.product_id,
                    candidates=matches,
                )
            member_ids.append(matches[0].member_id)

        padded = member_ids + [0] * (10 - len(member_ids))
        return ".".join(str(i) for i in padded)

    async def get_data_from_cube(
        self,
        product_id: int | str,
        coordinate: str,
        latest_n: int = 1,
    ) -> StatCanSeriesResult:
        """Fetch observations by product ID and 10-part coordinate for the latest N periods."""
        pid = normalize_product_id(product_id)
        coord = normalize_coordinate(coordinate)
        body = [{"productId": pid, "coordinate": coord, "latestN": latest_n}]

        response_data, fetched_at = await self._post_json(
            "getDataFromCubePidCoordAndLatestNPeriods", body
        )
        data_obj = self._extract_first_success_object(response_data, f"cube {pid} coord {coord}")

        meta = await self.get_cube_metadata(pid)
        s_title_en, s_title_fr, uom_name, uom_code = self._resolve_series_details_from_coord(
            meta, coord, uom_resolver=self.get_uom_name
        )

        vector_id_raw = _required_int(data_obj, "vectorId")
        observations = self._parse_observations(data_obj.get("vectorDataPoint"))

        return StatCanSeriesResult(
            product_id=pid,
            coordinate=coord,
            vector_id=vector_id_raw,
            title_en=meta.title_en,
            title_fr=meta.title_fr,
            frequency_code=meta.frequency_code,
            unit=uom_name,
            observations=observations,
            fetched_at=fetched_at,
            series_title_en=s_title_en,
            series_title_fr=s_title_fr,
            unit_code=uom_code,
        )

    async def get_data_from_vectors(
        self,
        vector_ids: Sequence[int | str],
        latest_n: int = 1,
    ) -> tuple[StatCanSeriesResult, ...]:
        """Fetch observations for one or more vector IDs for the latest N periods."""
        normalized_ids = [normalize_vector_id(vid) for vid in vector_ids]
        body = [{"vectorId": vid, "latestN": latest_n} for vid in normalized_ids]

        response_data, fetched_at = await self._post_json(
            "getDataFromVectorsAndLatestNPeriods", body
        )
        raw_items = _dict_list(response_data)

        results: list[StatCanSeriesResult] = []
        for item_dict in raw_items:
            if item_dict.get("status") != "SUCCESS":
                msg = str(item_dict.get("object") or item_dict.get("status"))
                raise StatCanResponseError(f"StatCan WDS vector query failed: {msg}")

            obj_dict = _dict(item_dict.get("object"))

            vid = _required_int(obj_dict, "vectorId")
            pid_raw = obj_dict.get("productId")
            if pid_raw is None:
                raise StatCanResponseError(f"invalid vector result payload: {obj_dict}")
            pid = normalize_product_id(str(pid_raw))
            coord = _text(obj_dict, "coordinate", "")

            meta = await self.get_cube_metadata(pid)
            s_title_en, s_title_fr, uom_name, uom_code = self._resolve_series_details_from_coord(
                meta, coord, uom_resolver=self.get_uom_name
            )
            observations = self._parse_observations(obj_dict.get("vectorDataPoint"))

            results.append(
                StatCanSeriesResult(
                    product_id=pid,
                    coordinate=coord,
                    vector_id=vid,
                    title_en=meta.title_en,
                    title_fr=meta.title_fr,
                    frequency_code=meta.frequency_code,
                    unit=uom_name,
                    observations=observations,
                    fetched_at=fetched_at,
                    series_title_en=s_title_en,
                    series_title_fr=s_title_fr,
                    unit_code=uom_code,
                )
            )

        return tuple(results)

    async def get_data_by_reference_period(
        self,
        vector_id: int | str,
        start: str,
        end: str | None = None,
    ) -> StatCanSeriesResult:
        """Fetch one vector's observations between two reference periods, inclusive.

        ``start`` and ``end`` are ISO dates as WDS stores them (``2025-01-01`` for the annual
        2025 point, ``2025-08-01`` for August 2025). ``end`` defaults to ``start``.
        """
        vid = normalize_vector_id(vector_id)
        params = {
            "vectorIds": f'"{vid}"',
            "startRefPeriod": start,
            "endReferencePeriod": end or start,
        }
        response_data, fetched_at = await self._request_json(
            "GET", "getDataFromVectorByReferencePeriodRange", params=params
        )
        obj_dict = self._extract_first_success_object(response_data, f"vector v{vid}")
        pid_raw = obj_dict.get("productId")
        if pid_raw is None:
            raise StatCanResponseError(f"invalid vector result payload: {obj_dict}")
        pid = normalize_product_id(str(pid_raw))
        meta = await self.get_cube_metadata(pid)
        return StatCanSeriesResult(
            product_id=pid,
            coordinate=_text(obj_dict, "coordinate", ""),
            vector_id=_required_int(obj_dict, "vectorId"),
            title_en=meta.title_en,
            title_fr=meta.title_fr,
            frequency_code=meta.frequency_code,
            unit=None,
            observations=self._parse_observations(obj_dict.get("vectorDataPoint")),
            fetched_at=fetched_at,
        )

    async def get_series_info(self, vector_id: int | str) -> SeriesInfo:
        """Fetch series metadata, unit of measure code, and coordinate for a given vector ID."""
        vid = normalize_vector_id(vector_id)
        body = [{"vectorId": vid}]
        response_data, _ = await self._post_json("getSeriesInfoFromVector", body)
        info_obj = self._extract_first_success_object(response_data, f"vector v{vid}")

        pid_raw = info_obj.get("productId")
        if pid_raw is None:
            raise StatCanResponseError(f"getSeriesInfoFromVector missing 'productId': {info_obj}")
        pid = normalize_product_id(str(pid_raw))

        uom_code = _optional_int(info_obj, "memberUomCode")
        uom_name = self.get_uom_name(uom_code)
        return SeriesInfo(
            vector_id=vid,
            product_id=pid,
            coordinate=_text(info_obj, "coordinate", ""),
            frequency_code=_required_int(info_obj, "frequencyCode"),
            scalar_factor_code=_optional_int(info_obj, "scalarFactorCode"),
            decimals=_optional_int(info_obj, "decimals"),
            title_en=_text(info_obj, "SeriesTitleEn", ""),
            title_fr=_optional_text(info_obj, "SeriesTitleFr"),
            member_uom_code=uom_code,
            unit=uom_name,
        )

    async def _post_json(self, endpoint: str, body: list[dict[str, Any]]) -> tuple[Any, str]:
        return await self._request_json("POST", endpoint, body=body)

    async def _request_json(
        self,
        method: str,
        endpoint: str,
        *,
        body: list[dict[str, Any]] | None = None,
        params: Mapping[str, str] | None = None,
    ) -> tuple[Any, str]:
        url = f"{self._base_url}/{endpoint}"
        response: httpx.Response | None = None

        for attempt in range(self._retries + 1):
            last_attempt = attempt == self._retries
            try:
                response = await self._client.request(method, url, json=body, params=params)
            except httpx.TransportError as exc:
                if last_attempt:
                    raise StatCanRequestError(f"request to {url} failed: {exc!r}") from exc
            else:
                if response.status_code not in _RETRY_STATUSES or last_attempt:
                    break
            await asyncio.sleep(self._backoff * (2**attempt))

        assert response is not None

        if response.status_code >= 400:
            if response.status_code == 404:
                raise StatCanNotFoundError(404, response.text)
            if response.status_code == 409:
                raise StatCanHTTPError(
                    409,
                    f"StatCan WDS maintenance window (00:00-08:30 ET) or conflict: {response.text}",
                )
            raise StatCanHTTPError(response.status_code, response.text)

        try:
            data: Any = response.json()
        except ValueError as exc:
            raise StatCanResponseError(f"response from {url} is not valid JSON") from exc

        return data, _fetched_at(response)

    @staticmethod
    def _extract_first_success_object(response_data: Any, context: str) -> dict[str, Any]:
        raw_items = _dict_list(response_data)
        if not raw_items:
            raise StatCanResponseError(f"expected non-empty list for {context}")
        item_dict = raw_items[0]
        status = item_dict.get("status")
        if status != "SUCCESS":
            msg = str(item_dict.get("object") or status)
            raise StatCanResponseError(f"WDS call failed for {context}: {msg}")
        return _dict(item_dict.get("object"))

    @staticmethod
    def _parse_cube_metadata(obj: dict[str, Any], pid: int) -> CubeMetadata:
        freq_code = _required_int(obj, "frequencyCode")
        freq_name = FREQUENCY_NAMES.get(freq_code, f"code_{freq_code}")

        dimensions: list[Dimension] = []
        dim_list = _optional_dict_list(obj.get("dimension"))
        for d_dict in dim_list:
            pos_id = _required_int(d_dict, "dimensionPositionId")
            d_name_en = _text(d_dict, "dimensionNameEn", "")
            d_name_fr = _optional_text(d_dict, "dimensionNameFr")
            has_uom = bool(d_dict.get("hasUom", False))

            members: list[DimensionMember] = []
            m_list = _optional_dict_list(d_dict.get("member"))
            for m_dict in m_list:
                members.append(
                    DimensionMember(
                        member_id=_required_int(m_dict, "memberId"),
                        parent_member_id=_optional_int(m_dict, "parentMemberId"),
                        name_en=_text(m_dict, "memberNameEn", ""),
                        name_fr=_optional_text(m_dict, "memberNameFr"),
                        member_uom_code=_optional_int(m_dict, "memberUomCode"),
                    )
                )
            dimensions.append(
                Dimension(
                    position_id=pos_id,
                    name_en=d_name_en,
                    name_fr=d_name_fr,
                    has_uom=has_uom,
                    members=tuple(members),
                )
            )

        return CubeMetadata(
            product_id=pid,
            cansim_id=_optional_text(obj, "cansimId"),
            title_en=_text(obj, "cubeTitleEn", ""),
            title_fr=_optional_text(obj, "cubeTitleFr"),
            start_date=_optional_text(obj, "cubeStartDate"),
            end_date=_optional_text(obj, "cubeEndDate"),
            release_time=_optional_text(obj, "releaseTime"),
            frequency_code=freq_code,
            frequency_name=freq_name,
            dimensions=tuple(dimensions),
        )

    @staticmethod
    def _parse_observations(points: Any) -> tuple[Observation, ...]:
        obs_list: list[Observation] = []
        raw_points = _optional_dict_list(points)
        for p_dict in raw_points:
            ref_per = _text(p_dict, "refPer", "")
            raw_val = p_dict.get("value")
            val: float | None = None
            if raw_val is not None and raw_val != "":
                try:
                    val = float(str(raw_val))
                except (ValueError, TypeError):
                    val = None

            obs_list.append(
                Observation(
                    ref_per=ref_per,
                    value=val,
                    decimals=_optional_int(p_dict, "decimals"),
                    release_time=_optional_text(p_dict, "releaseTime"),
                    scalar_factor_code=_optional_int(p_dict, "scalarFactorCode"),
                    frequency_code=_optional_int(p_dict, "frequencyCode"),
                    status_code=_optional_int(p_dict, "statusCode"),
                    symbol_code=_optional_int(p_dict, "symbolCode"),
                )
            )

        obs_list.sort(key=lambda o: o.ref_per)
        return tuple(obs_list)


def _dict(source: Any) -> dict[str, Any]:
    if not isinstance(source, dict):
        raise StatCanResponseError(f"expected JSON object, got {type(source).__name__}")
    return source  # pyright: ignore[reportUnknownVariableType]


def _dict_list(source: Any) -> list[dict[str, Any]]:
    if not isinstance(source, list):
        raise StatCanResponseError(f"expected JSON list, got {type(source).__name__}")
    return [x for x in source if isinstance(x, dict)]  # pyright: ignore[reportUnknownVariableType]


def _optional_dict_list(source: Any) -> list[dict[str, Any]]:
    if not isinstance(source, list):
        return []
    return [x for x in source if isinstance(x, dict)]  # pyright: ignore[reportUnknownVariableType]


def _text(source: Mapping[str, Any], key: str, default: str) -> str:
    value = source.get(key)
    return str(value) if isinstance(value, str) else default


def _optional_text(source: Mapping[str, Any], key: str) -> str | None:
    value = source.get(key)
    return str(value) if isinstance(value, str) else None


def _optional_int(source: Mapping[str, Any], key: str) -> int | None:
    value = source.get(key)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _required_int(source: Mapping[str, Any], key: str) -> int:
    val = _optional_int(source, key)
    if val is None or val <= 0:
        raise StatCanResponseError(
            f"expected positive integer for {key!r}, got {source.get(key)!r}"
        )
    return val


def _fetched_at(response: httpx.Response) -> str:
    header = response.headers.get("date")
    if header:
        try:
            return parsedate_to_datetime(header).astimezone(UTC).isoformat(timespec="seconds")
        except (TypeError, ValueError):
            pass
    return datetime.now(UTC).isoformat(timespec="seconds")
