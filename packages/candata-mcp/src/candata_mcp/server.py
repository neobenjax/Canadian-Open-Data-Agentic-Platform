"""FastMCP 2.0 Server for Canadian Open Data Agentic Platform (CanData-MCP).

Exposes official Statistics Canada, Bank of Canada, and Open Government Canada CKAN datasets
via FastMCP tools, streaming upstream observations through an in-memory DuckDB Arrow engine
to ensure all outputs are strictly bounded (<3KB) and paired with Two-Tier Citation Envelopes.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from candata_mcp.bilingual import Language, parse_language
from candata_mcp.connectors.boc_valet import ObservationSet, ValetClient
from candata_mcp.connectors.ckan_open_canada import (
    CKANClient,
    CKANNotFoundError,
)
from candata_mcp.connectors.statcan_wds import (
    StatCanAmbiguousMemberError,
    StatCanClient,
    StatCanNotFoundError,
    StatCanUnavailableError,
    format_table_id,
)
from candata_mcp.engine import DuckDBSlicingEngine
from candata_mcp.lineage import (
    SourceCall,
    build_lineage,
    ckan_call,
    statcan_call,
    valet_call,
)

# FastMCP 2026 Tool Annotation Presets
READ_ONLY_TOOL = ToolAnnotations(
    read_only_hint=True,
    idempotent_hint=True,
    open_world_hint=True,
)

LOCAL_ANALYTIC_TOOL = ToolAnnotations(
    read_only_hint=True,
    idempotent_hint=True,
    open_world_hint=False,
)

LANG_NOTE = (
    " Pass lang='fr' for the French title; when no official French title exists the "
    "English one is returned and flagged in 'display'."
)


def _valet_call(
    result: ObservationSet,
    *,
    start_date: str | None,
    end_date: str | None,
    recent: int | None,
) -> SourceCall:
    """The Valet request behind ``result``, with only the parameters that were sent."""
    return valet_call(
        f"observations/{result.series.name}/json",
        {"recent": recent, "start_date": start_date, "end_date": end_date},
    )


class CanDataServer:
    """Manages the FastMCP server, connectors, and DuckDB slicing engine."""

    def __init__(
        self,
        statcan_client: StatCanClient | None = None,
        valet_client: ValetClient | None = None,
        ckan_client: CKANClient | None = None,
        engine: DuckDBSlicingEngine | None = None,
    ) -> None:
        self.statcan_client: StatCanClient = statcan_client or StatCanClient()
        self.valet_client: ValetClient = valet_client or ValetClient()
        self.ckan_client: CKANClient = ckan_client or CKANClient()
        self.engine: DuckDBSlicingEngine = engine or DuckDBSlicingEngine()

        self.mcp: MCPServer = MCPServer(
            name="candata-mcp",
            title="Canadian Open Data Agentic Platform MCP Server",
            version="0.1.0",
            description=(
                "Official StatCan WDS, BoC Valet, and Open Government Canada CKAN open-data "
                "MCP server with in-memory DuckDB Arrow slicing engine and "
                "Two-Tier Citation Envelopes."
            ),
        )
        self._register_tools()

    async def aclose(self) -> None:
        """Close all active connector sessions and DuckDB engine connection."""
        await self.statcan_client.aclose()
        await self.valet_client.aclose()
        await self.ckan_client.aclose()
        self.engine.close()

    def _register_tools(self) -> None:
        """Register all official Canadian data retrieval, catalog discovery and analytics tools."""

        @self.mcp.tool(
            name="search_statcan_cubes",
            description=(
                "Search official Statistics Canada data cubes/tables by multi-word keyword "
                "(e.g. 'cpi', 'toronto rent', 'average rents', 'labour', 'gdp'). Returns a "
                "token-budgeted list of matching tables with product IDs and release dates."
            ),
            annotations=READ_ONLY_TOOL,
        )
        async def search_statcan_cubes(
            query: str,
            limit: int = 10,
            offset: int = 0,
        ) -> dict[str, Any]:
            q = query.strip()
            if not q:
                return {
                    "error": "Query string cannot be empty.",
                    "isError": True,
                    "error_code": "INVALID_ARGUMENT",
                    "message": "Query string cannot be empty.",
                }
            limit = max(1, min(limit, 50))
            offset = max(0, offset)
            try:
                search_res = await self.statcan_client.search_cubes(q, limit=limit, offset=offset)
                total_cnt = getattr(search_res, "total_results", len(search_res))
                cubes_seq = getattr(search_res, "cubes", search_res)
                return {
                    "query": q,
                    "total_results": total_cnt,
                    "offset": offset,
                    "limit": limit,
                    "cubes": [asdict(c) for c in cubes_seq],
                }
            except StatCanUnavailableError as exc:
                return {
                    "error": exc.message,
                    "isError": True,
                    "error_code": "STATCAN_UNAVAILABLE",
                    "message": exc.message,
                    "retry_after": exc.retry_after,
                    "suggested_action": (
                        "Query by product_id directly using get_cube_dimensions "
                        "if table ID is known."
                    ),
                }
            except Exception as exc:
                return {
                    "error": str(exc),
                    "isError": True,
                    "error_code": "INTERNAL_ERROR",
                    "message": str(exc),
                }

        @self.mcp.tool(
            name="get_cube_dimensions",
            description=(
                "Retrieve the dimensions and member hierarchies of a Statistics Canada data cube "
                "by product ID or table ID (e.g. '18100004' or '18-10-0004-01'). Members can be "
                "filtered by name using 'member_query' (e.g. 'Toronto') and paged using 'offset' "
                "and 'limit'."
            ),
            annotations=READ_ONLY_TOOL,
        )
        async def get_cube_dimensions(
            product_id: str,
            member_query: str | None = None,
            dimension_name: str | None = None,
            offset: int = 0,
            limit: int = 25,
            max_members_per_dim: int | None = None,
        ) -> dict[str, Any]:
            pid_str = product_id.strip()
            if not pid_str:
                return {
                    "error": "product_id cannot be empty.",
                    "isError": True,
                    "error_code": "INVALID_ARGUMENT",
                    "message": "product_id cannot be empty.",
                }
            try:
                meta = await self.statcan_client.get_cube_metadata(pid_str)
            except StatCanNotFoundError as exc:
                return {
                    "error": str(exc),
                    "isError": True,
                    "error_code": "NOT_FOUND",
                    "message": str(exc),
                    "suggested_action": "Search for available tables using search_statcan_cubes.",
                }
            except Exception as exc:
                return {
                    "error": str(exc),
                    "isError": True,
                    "error_code": "STATCAN_UNAVAILABLE",
                    "message": str(exc),
                    "suggested_action": (
                        "Retry the request or verify network connectivity to StatCan WDS."
                    ),
                }

            effective_limit = max_members_per_dim if max_members_per_dim is not None else limit
            effective_limit = max(1, min(effective_limit, 100))
            offset = max(0, offset)

            dim_filter = dimension_name.strip().lower() if dimension_name else None
            mem_filter = member_query.strip().lower() if member_query else None

            dims_out: list[dict[str, Any]] = []
            for dim in meta.dimensions:
                if dim_filter:
                    name_en_match = dim_filter in dim.name_en.lower()
                    name_fr_match = bool(dim.name_fr and dim_filter in dim.name_fr.lower())
                    if not (name_en_match or name_fr_match):
                        continue

                if mem_filter:
                    filtered_members = [
                        m
                        for m in dim.members
                        if mem_filter in m.name_en.lower()
                        or (m.name_fr and mem_filter in m.name_fr.lower())
                    ]
                else:
                    filtered_members = list(dim.members)

                matched_count = len(filtered_members)
                paged_members = filtered_members[offset : offset + effective_limit]

                dims_out.append(
                    {
                        "position_id": dim.position_id,
                        "name_en": dim.name_en,
                        "name_fr": dim.name_fr,
                        "total_members": len(dim.members),
                        "total_dimension_members": len(dim.members),
                        "matched_members_count": matched_count,
                        "offset": offset,
                        "limit": effective_limit,
                        "has_more_members": (offset + len(paged_members)) < matched_count,
                        "members": [
                            {
                                "member_id": m.member_id,
                                "name_en": m.name_en,
                                "name_fr": m.name_fr,
                                "parent_member_id": m.parent_member_id,
                            }
                            for m in paged_members
                        ],
                    }
                )

            return {
                "product_id": meta.product_id,
                "table_id": format_table_id(meta.product_id),
                "cansim_id": meta.cansim_id,
                "title_en": meta.title_en,
                "title_fr": meta.title_fr,
                "frequency": meta.frequency_name,
                "release_time": meta.release_time,
                "dimensions": dims_out,
            }

        @self.mcp.tool(
            name="query_statcan_vector",
            description=(
                "Query a Statistics Canada time series by vector ID (e.g. 'v41690973'). "
                "Retrieves official observations from Statistics Canada WDS, streams them "
                "through an in-memory DuckDB Arrow engine for temporal slicing, and returns "
                "a strictly <3KB payload complete with Two-Tier Citation Envelope and data lineage."
                + LANG_NOTE
            ),
            annotations=READ_ONLY_TOOL,
        )
        async def query_statcan_vector(
            vector_id: str,
            start_date: str | None = None,
            end_date: str | None = None,
            limit: int = 12,
            lang: str = "en",
        ) -> dict[str, Any]:
            try:
                language: Language = parse_language(lang)
            except ValueError as exc:
                return {
                    "error": str(exc),
                    "isError": True,
                    "error_code": "INVALID_LANGUAGE",
                    "message": str(exc),
                }
            clean_vid = re.sub(r"^v", "", vector_id.strip(), flags=re.IGNORECASE)
            fetch_n = max(limit * 4, 100) if (start_date or end_date) else max(limit, 12)
            try:
                results = await self.statcan_client.get_data_from_vectors(
                    [clean_vid], latest_n=fetch_n
                )
            except Exception as exc:
                return {
                    "error": str(exc),
                    "isError": True,
                    "error_code": "STATCAN_ERROR",
                    "message": str(exc),
                }
            if not results:
                return {
                    "error": f"No data found for vector ID {vector_id}",
                    "isError": True,
                    "error_code": "NOT_FOUND",
                    "message": f"No data found for vector ID {vector_id}",
                }
            return self.engine.slice_statcan(
                results[0],
                start_date=start_date,
                end_date=end_date,
                limit=limit,
                descending=True,
                lang=language,
                source_call=statcan_call(
                    "getDataFromVectorsAndLatestNPeriods",
                    {"vectorId": results[0].vector_id, "latestN": fetch_n},
                ),
            )

        @self.mcp.tool(
            name="query_statcan_coordinate",
            description=(
                "Query a Statistics Canada data cube by table ID and coordinate "
                "(e.g. table '18-10-0004-01', coordinate '2.1'). "
                "Retrieves official observations from Statistics Canada WDS, streams them "
                "through an in-memory DuckDB Arrow engine, and returns a strictly <3KB "
                "payload complete with Two-Tier Citation Envelope and data lineage." + LANG_NOTE
            ),
            annotations=READ_ONLY_TOOL,
        )
        async def query_statcan_coordinate(
            table_id: str,
            coordinate: str,
            start_date: str | None = None,
            end_date: str | None = None,
            limit: int = 12,
            lang: str = "en",
        ) -> dict[str, Any]:
            try:
                language: Language = parse_language(lang)
            except ValueError as exc:
                return {
                    "error": str(exc),
                    "isError": True,
                    "error_code": "INVALID_LANGUAGE",
                    "message": str(exc),
                }
            fetch_n = max(limit * 4, 100) if (start_date or end_date) else max(limit, 12)
            try:
                result = await self.statcan_client.get_data_from_cube(
                    product_id=table_id,
                    coordinate=coordinate,
                    latest_n=fetch_n,
                )
            except StatCanAmbiguousMemberError as exc:
                return {
                    "error": str(exc),
                    "isError": True,
                    "error_code": "AMBIGUOUS_MEMBER",
                    "message": str(exc),
                    "details": {
                        "member_name": exc.member_name,
                        "dimension_position": exc.dimension_position,
                        "dimension_name": exc.dimension_name,
                        "product_id": exc.product_id,
                        "candidate_ids": list(exc.candidate_ids),
                    },
                    "troubleshooting": (
                        "Multiple dimension members match the requested name. "
                        "Disambiguate by specifying the exact member ID or coordinate, "
                        "or escalate to Human-in-the-Loop review."
                    ),
                }
            except ValueError as exc:
                return {
                    "error": str(exc),
                    "isError": True,
                    "error_code": "INVALID_COORDINATE",
                    "message": str(exc),
                }
            except Exception as exc:
                return {
                    "error": str(exc),
                    "isError": True,
                    "error_code": "STATCAN_ERROR",
                    "message": str(exc),
                }

            return self.engine.slice_statcan(
                result,
                start_date=start_date,
                end_date=end_date,
                limit=limit,
                descending=True,
                lang=language,
                source_call=statcan_call(
                    "getDataFromCubePidCoordAndLatestNPeriods",
                    {
                        "productId": result.product_id,
                        "coordinate": result.coordinate,
                        "latestN": fetch_n,
                    },
                ),
            )

        @self.mcp.tool(
            name="query_valet_series",
            description=(
                "Query a Bank of Canada time series by series name (e.g. 'V39079'). "
                "Retrieves official observations from Bank of Canada Valet API, streams them "
                "through an in-memory DuckDB Arrow engine for temporal slicing, and returns "
                "a strictly <3KB payload complete with Two-Tier Citation Envelope and data lineage."
                + LANG_NOTE
            ),
            annotations=READ_ONLY_TOOL,
        )
        async def query_valet_series(
            series_name: str,
            start_date: str | None = None,
            end_date: str | None = None,
            limit: int = 12,
            lang: str = "en",
        ) -> dict[str, Any]:
            try:
                language: Language = parse_language(lang)
            except ValueError as exc:
                return {
                    "error": str(exc),
                    "isError": True,
                    "error_code": "INVALID_LANGUAGE",
                    "message": str(exc),
                }
            clean_name = series_name.strip()
            recent: int | None = None
            try:
                if start_date or end_date:
                    result = await self.valet_client.get_observations(
                        clean_name,
                        start_date=start_date,
                        end_date=end_date,
                    )
                else:
                    recent = max(limit * 2, 24)
                    result = await self.valet_client.get_observations(clean_name, recent=recent)
            except Exception as exc:
                return {
                    "error": str(exc),
                    "isError": True,
                    "error_code": "VALET_ERROR",
                    "message": str(exc),
                }

            return self.engine.slice_valet(
                result,
                start_date=start_date,
                end_date=end_date,
                limit=limit,
                descending=True,
                lang=language,
                source_call=_valet_call(
                    result, start_date=start_date, end_date=end_date, recent=recent
                ),
            )

        @self.mcp.tool(
            name="query_valet_policy_rate",
            description=(
                "Query the official Bank of Canada Policy Interest Rate target (Series V39079). "
                "Convenience tool returning recent policy rate decisions, sliced via in-memory "
                "DuckDB Arrow engine and paired with the Two-Tier Citation Envelope and data "
                "lineage." + LANG_NOTE
            ),
            annotations=READ_ONLY_TOOL,
        )
        async def query_valet_policy_rate(
            start_date: str | None = None,
            end_date: str | None = None,
            limit: int = 10,
            lang: str = "en",
        ) -> dict[str, Any]:
            try:
                language: Language = parse_language(lang)
            except ValueError as exc:
                return {
                    "error": str(exc),
                    "isError": True,
                    "error_code": "INVALID_LANGUAGE",
                    "message": str(exc),
                }
            recent: int | None = None
            try:
                if start_date or end_date:
                    result = await self.valet_client.get_policy_rate(
                        start_date=start_date,
                        end_date=end_date,
                    )
                else:
                    recent = max(limit * 2, 20)
                    result = await self.valet_client.get_policy_rate(recent=recent)
            except Exception as exc:
                return {
                    "error": str(exc),
                    "isError": True,
                    "error_code": "VALET_ERROR",
                    "message": str(exc),
                }

            return self.engine.slice_valet(
                result,
                start_date=start_date,
                end_date=end_date,
                limit=limit,
                descending=True,
                lang=language,
                source_call=_valet_call(
                    result, start_date=start_date, end_date=end_date, recent=recent
                ),
            )

        @self.mcp.tool(
            name="query_valet_cpi",
            description=(
                "Query Bank of Canada core inflation measures (e.g. 'total', 'common', "
                "'median', 'trim'). "
                "Retrieves official core CPI series from Valet API, sliced via DuckDB "
                "Arrow streaming, and paired with the Two-Tier Citation Envelope and data lineage."
                + LANG_NOTE
            ),
            annotations=READ_ONLY_TOOL,
        )
        async def query_valet_cpi(
            measure: str = "total",
            start_date: str | None = None,
            end_date: str | None = None,
            limit: int = 12,
            lang: str = "en",
        ) -> dict[str, Any]:
            try:
                language: Language = parse_language(lang)
            except ValueError as exc:
                return {
                    "error": str(exc),
                    "isError": True,
                    "error_code": "INVALID_LANGUAGE",
                    "message": str(exc),
                }
            recent: int | None = None
            try:
                if start_date or end_date:
                    result = await self.valet_client.get_cpi(
                        measure=measure,
                        start_date=start_date,
                        end_date=end_date,
                    )
                else:
                    recent = max(limit * 2, 24)
                    result = await self.valet_client.get_cpi(measure=measure, recent=recent)
            except Exception as exc:
                return {
                    "error": str(exc),
                    "isError": True,
                    "error_code": "VALET_ERROR",
                    "message": str(exc),
                }

            return self.engine.slice_valet(
                result,
                start_date=start_date,
                end_date=end_date,
                limit=limit,
                descending=True,
                lang=language,
                source_call=_valet_call(
                    result, start_date=start_date, end_date=end_date, recent=recent
                ),
            )

        @self.mcp.tool(
            name="search_open_canada_datasets",
            description=(
                "Search official Open Government Canada (open.canada.ca) CKAN catalog by keyword. "
                "Discovers federal datasets (CMHC, IRCC, Environment Canada), returning "
                "titles, organizations, metadata dates, and DataStore-active resource IDs."
            ),
            annotations=READ_ONLY_TOOL,
        )
        async def search_open_canada_datasets(
            query: str,
            organization: str | None = None,
            datastore_only: bool = False,
            limit: int = 10,
            offset: int = 0,
        ) -> dict[str, Any]:
            q = query.strip()
            if not q:
                return {
                    "error": "Query string cannot be empty.",
                    "isError": True,
                    "error_code": "INVALID_ARGUMENT",
                    "message": "Query string cannot be empty.",
                }
            limit = max(1, min(limit, 50))
            offset = max(0, offset)
            try:
                search_res = await self.ckan_client.search_datasets(
                    q,
                    organization=organization,
                    datastore_only=datastore_only,
                    limit=limit,
                    offset=offset,
                )
                return {
                    "query": q,
                    "total_results": search_res.total_results,
                    "offset": offset,
                    "limit": limit,
                    "datasets": [asdict(d) for d in search_res.datasets],
                }
            except Exception as exc:
                return {
                    "error": str(exc),
                    "isError": True,
                    "error_code": "CKAN_ERROR",
                    "message": str(exc),
                }

        @self.mcp.tool(
            name="get_open_canada_dataset",
            description=(
                "Retrieve detailed metadata and resource inventories for a specific dataset from "
                "Open Government Canada (open.canada.ca) by package ID or slug. Returns "
                "bilingual titles, descriptions, licensing, and available distributions."
            ),
            annotations=READ_ONLY_TOOL,
        )
        async def get_open_canada_dataset(
            package_id: str,
        ) -> dict[str, Any]:
            pid = package_id.strip()
            if not pid:
                return {
                    "error": "package_id cannot be empty.",
                    "isError": True,
                    "error_code": "INVALID_ARGUMENT",
                    "message": "package_id cannot be empty.",
                }
            try:
                detail = await self.ckan_client.get_dataset(pid)
                envelope = detail.citation()
                return {
                    "package_id": detail.package_id,
                    "name": detail.name,
                    "title": {"en": detail.title_en, "fr": detail.title_fr},
                    "notes": {"en": detail.notes_en, "fr": detail.notes_fr},
                    "organization": {"en": detail.organization_en, "fr": detail.organization_fr},
                    "metadata_modified": detail.metadata_modified,
                    "temporal_coverage": {
                        "start": detail.time_period_coverage_start,
                        "end": detail.time_period_coverage_end,
                    },
                    "license_title": detail.license_title,
                    "license_url": detail.license_url,
                    "resources": [asdict(r) for r in detail.resources],
                    "citation": asdict(envelope),
                }
            except CKANNotFoundError as exc:
                return {
                    "error": str(exc),
                    "isError": True,
                    "error_code": "NOT_FOUND",
                    "message": str(exc),
                    "suggested_action": (
                        "Search available datasets using search_open_canada_datasets."
                    ),
                }
            except Exception as exc:
                return {
                    "error": str(exc),
                    "isError": True,
                    "error_code": "CKAN_ERROR",
                    "message": str(exc),
                }

        @self.mcp.tool(
            name="query_open_canada_datastore",
            description=(
                "Query tabular records from an active Open Canada CKAN DataStore resource. "
                "Streams records through DuckDB Arrow engine, returning a strictly <3KB "
                "payload complete with Two-Tier Citation Envelope and data lineage." + LANG_NOTE
            ),
            annotations=READ_ONLY_TOOL,
        )
        async def query_open_canada_datastore(
            resource_id: str,
            package_id: str | None = None,
            q: str | None = None,
            filters: dict[str, Any] | str | None = None,
            fields: list[str] | str | None = None,
            sort: str | None = None,
            limit: int = 25,
            offset: int = 0,
            lang: str = "en",
        ) -> dict[str, Any]:
            try:
                language: Language = parse_language(lang)
            except ValueError as exc:
                return {
                    "error": str(exc),
                    "isError": True,
                    "error_code": "INVALID_LANGUAGE",
                    "message": str(exc),
                }
            rid = resource_id.strip()
            if not rid:
                return {
                    "error": "resource_id cannot be empty.",
                    "isError": True,
                    "error_code": "INVALID_ARGUMENT",
                    "message": "resource_id cannot be empty.",
                }

            # Parse string-serialized filter/field parameters gracefully
            parsed_filters: dict[str, Any] | None = None
            if isinstance(filters, str):
                s_filters = filters.strip()
                if s_filters:
                    try:
                        raw = json.loads(s_filters)
                        if isinstance(raw, dict):
                            parsed_filters = raw  # pyright: ignore[reportUnknownVariableType]
                    except Exception:
                        pass
            elif isinstance(filters, dict):
                parsed_filters = filters

            parsed_fields: list[str] | None = None
            if isinstance(fields, str):
                s_fields = fields.strip()
                if s_fields:
                    if s_fields.startswith("["):
                        try:
                            raw_f = json.loads(s_fields)
                            if isinstance(raw_f, list):
                                parsed_fields = [str(x) for x in raw_f]  # pyright: ignore[reportUnknownVariableType,reportUnknownArgumentType]
                        except Exception:
                            parsed_fields = [f.strip() for f in s_fields.split(",") if f.strip()]
                    else:
                        parsed_fields = [f.strip() for f in s_fields.split(",") if f.strip()]
            elif isinstance(fields, list):
                parsed_fields = [str(x) for x in fields]

            try:
                result = await self.ckan_client.query_datastore(
                    rid,
                    package_id=package_id,
                    q=q,
                    filters=parsed_filters,
                    fields=parsed_fields,
                    sort=sort,
                    limit=limit,
                    offset=offset,
                )
            except CKANNotFoundError as exc:
                return {
                    "error": str(exc),
                    "isError": True,
                    "error_code": "NOT_FOUND",
                    "message": str(exc),
                }
            except Exception as exc:
                return {
                    "error": str(exc),
                    "isError": True,
                    "error_code": "CKAN_ERROR",
                    "message": str(exc),
                }

            return self.engine.slice_ckan(
                result,
                limit=limit,
                lang=language,
                source_call=ckan_call(
                    "datastore_search",
                    {
                        "resource_id": rid,
                        "limit": limit,
                        "offset": offset,
                        "q": q,
                        "sort": sort,
                    },
                ),
            )

        @self.mcp.tool(
            name="execute_sql_analytics",
            description=(
                "Execute read-only SQL calculations over an official Canadian dataset. "
                "Fetches the series from StatCan, Valet, or CKAN DataStore, registers it as "
                "Arrow table 'series' in DuckDB, executes exact SQL math (mean, min, max), "
                "and returns deterministic results to prevent LLM mental math errors."
            ),
            annotations=LOCAL_ANALYTIC_TOOL,
        )
        async def execute_sql_analytics(
            source: str,
            series_id: str,
            sql_query: str,
        ) -> dict[str, Any]:
            src = source.strip().lower()
            if src in ("statcan", "statistics canada"):
                clean_vid = re.sub(r"^v", "", series_id.strip(), flags=re.IGNORECASE)
                results = await self.statcan_client.get_data_from_vectors([clean_vid], latest_n=100)
                if not results:
                    return {
                        "error": f"No data found for StatCan vector {series_id}",
                        "isError": True,
                        "error_code": "NOT_FOUND",
                        "message": f"No data found for StatCan vector {series_id}",
                    }
                target_result = results[0]
                table = self.engine.table_from_statcan(target_result)
                envelope = target_result.citation()
                citation = asdict(envelope)
                fetched_at = target_result.fetched_at
                source_call = statcan_call(
                    "getDataFromVectorsAndLatestNPeriods",
                    {"vectorId": target_result.vector_id, "latestN": 100},
                )
                fetched_count = len(target_result.observations)
            elif src in ("valet", "boc", "bank of canada"):
                clean_sid = series_id.strip()
                valet_result = await self.valet_client.get_observations(clean_sid, recent=100)
                table = self.engine.table_from_valet(valet_result)
                envelope = valet_result.citation()
                citation = asdict(envelope)
                fetched_at = valet_result.fetched_at
                source_call = _valet_call(valet_result, start_date=None, end_date=None, recent=100)
                fetched_count = len(valet_result.observations)
            elif src in ("ckan", "open_canada", "open canada", "open government"):
                res_id = series_id.strip()
                pack_id: str | None = None
                if ":" in res_id:
                    pack_id, res_id = res_id.split(":", 1)
                try:
                    datastore_res = await self.ckan_client.query_datastore(
                        res_id, package_id=pack_id, limit=100
                    )
                except Exception as exc:
                    return {
                        "error": str(exc),
                        "isError": True,
                        "error_code": "CKAN_ERROR",
                        "message": str(exc),
                    }
                if not datastore_res.records:
                    return {
                        "error": f"No records found for CKAN resource {series_id}",
                        "isError": True,
                        "error_code": "NOT_FOUND",
                        "message": f"No records found for CKAN resource {series_id}",
                    }
                table = self.engine.table_from_ckan(datastore_res)
                envelope = datastore_res.citation()
                citation = asdict(envelope)
                fetched_at = datastore_res.fetched_at
                source_call = ckan_call(
                    "datastore_search",
                    {"resource_id": res_id, "limit": 100},
                )
                fetched_count = len(datastore_res.records)
            else:
                return {
                    "error": f"Unsupported source '{source}'. Choose statcan, valet, or ckan.",
                    "isError": True,
                    "error_code": "INVALID_SOURCE",
                    "message": f"Unsupported source '{source}'. Choose statcan, valet, or ckan.",
                }

            try:
                results_list = self.engine.execute_analytics(table, sql_query)
            except Exception as e:
                return {
                    "error": f"SQL execution failed: {e}",
                    "isError": True,
                    "error_code": "SQL_ERROR",
                    "message": f"SQL execution failed: {e}",
                }

            payload: dict[str, Any] = {
                "source": source,
                "series_id": series_id,
                "sql_query": sql_query,
                "row_count": len(results_list),
                "data": results_list,
                "citation": citation,
                "lineage": build_lineage(
                    publisher=envelope.publisher,
                    fetched_at=fetched_at,
                    upstream_release=envelope.enrichment.release_or_revision_date,
                    source_call=source_call,
                    steps=(
                        f"fetched {fetched_count} observations",
                        f"computed in DuckDB with the read-only SQL shown; {len(results_list)} "
                        "rows returned",
                    ),
                ),
            }
            return self.engine.clamp_payload(payload)


def create_server(
    statcan_client: StatCanClient | None = None,
    valet_client: ValetClient | None = None,
    ckan_client: CKANClient | None = None,
    engine: DuckDBSlicingEngine | None = None,
) -> CanDataServer:
    """Factory creating an instance of CanDataServer."""
    return CanDataServer(
        statcan_client=statcan_client,
        valet_client=valet_client,
        ckan_client=ckan_client,
        engine=engine,
    )


# Default singleton server instance
default_server: CanDataServer = create_server()
mcp: MCPServer = default_server.mcp


def main() -> None:
    """CLI entrypoint for running the CanData-MCP stdio server."""
    default_server.mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
