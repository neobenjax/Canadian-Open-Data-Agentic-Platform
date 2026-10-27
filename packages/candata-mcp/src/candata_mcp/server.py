"""FastMCP 2.0 Server for Canadian Open Data Agentic Platform (CanData-MCP).

Exposes official Statistics Canada and Bank of Canada datasets via FastMCP tools,
streaming upstream observations through an in-memory DuckDB Arrow engine to ensure
all outputs are strictly bounded (<3KB) and paired with Two-Tier Citation Envelopes.
"""

from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from candata_mcp.bilingual import Language, parse_language
from candata_mcp.connectors.boc_valet import ObservationSet, ValetClient
from candata_mcp.connectors.statcan_wds import (
    StatCanAmbiguousMemberError,
    StatCanClient,
    format_table_id,
)
from candata_mcp.engine import DuckDBSlicingEngine
from candata_mcp.lineage import SourceCall, build_lineage, statcan_call, valet_call

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
        engine: DuckDBSlicingEngine | None = None,
    ) -> None:
        self.statcan_client: StatCanClient = statcan_client or StatCanClient()
        self.valet_client: ValetClient = valet_client or ValetClient()
        self.engine: DuckDBSlicingEngine = engine or DuckDBSlicingEngine()

        self.mcp: MCPServer = MCPServer(
            name="candata-mcp",
            title="Canadian Open Data Agentic Platform MCP Server",
            version="0.1.0",
            description=(
                "Official StatCan WDS and BoC Valet open-data MCP server with in-memory "
                "DuckDB Arrow slicing engine and Two-Tier Citation Envelopes."
            ),
        )
        self._register_tools()

    async def aclose(self) -> None:
        """Close all active connector sessions and DuckDB engine connection."""
        await self.statcan_client.aclose()
        await self.valet_client.aclose()
        self.engine.close()

    def _register_tools(self) -> None:
        """Register all official Canadian data retrieval, catalog discovery and analytics tools."""

        @self.mcp.tool(
            name="search_statcan_cubes",
            description=(
                "Search official Statistics Canada data cubes/tables by keyword (e.g. 'cpi', "
                "'housing', 'rents', 'labour', 'gdp'). Returns a token-budgeted list of matching "
                "tables with product IDs, titles, release dates, and frequency."
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
            results = await self.statcan_client.search_cubes(q, limit=limit, offset=offset)
            return {
                "query": q,
                "total_results": len(results),
                "offset": offset,
                "limit": limit,
                "cubes": [asdict(c) for c in results],
            }

        @self.mcp.tool(
            name="get_cube_dimensions",
            description=(
                "Retrieve the dimensions and member hierarchies of a Statistics Canada data cube "
                "by product ID or table ID (e.g. '18100004' or '18-10-0004-01'). Members per "
                "dimension are bounded (default max 25) to prevent LLM context-window bloat."
            ),
            annotations=READ_ONLY_TOOL,
        )
        async def get_cube_dimensions(
            product_id: str,
            max_members_per_dim: int = 25,
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
            except Exception as exc:
                return {
                    "error": str(exc),
                    "isError": True,
                    "error_code": "NOT_FOUND",
                    "message": str(exc),
                }

            max_members = max(1, min(max_members_per_dim, 100))
            return {
                "product_id": meta.product_id,
                "table_id": format_table_id(meta.product_id),
                "cansim_id": meta.cansim_id,
                "title_en": meta.title_en,
                "title_fr": meta.title_fr,
                "frequency": meta.frequency_name,
                "release_time": meta.release_time,
                "dimensions": [
                    {
                        "position_id": dim.position_id,
                        "name_en": dim.name_en,
                        "name_fr": dim.name_fr,
                        "total_members": len(dim.members),
                        "has_more_members": len(dim.members) > max_members,
                        "members": [
                            {
                                "member_id": m.member_id,
                                "name_en": m.name_en,
                                "name_fr": m.name_fr,
                                "parent_member_id": m.parent_member_id,
                            }
                            for m in dim.members[:max_members]
                        ],
                    }
                    for dim in meta.dimensions
                ],
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
            name="execute_sql_analytics",
            description=(
                "Execute read-only SQL calculations over an official Canadian dataset. "
                "Fetches the series from StatCan or Valet, registers it as Arrow table 'series' "
                "in DuckDB, executes exact SQL math (mean, min, max, percentage changes), "
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
            else:
                return {
                    "error": f"Unsupported source '{source}'. Choose 'statcan' or 'valet'.",
                    "isError": True,
                    "error_code": "INVALID_SOURCE",
                    "message": f"Unsupported source '{source}'. Choose 'statcan' or 'valet'.",
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
    engine: DuckDBSlicingEngine | None = None,
) -> CanDataServer:
    """Factory creating an instance of CanDataServer."""
    return CanDataServer(
        statcan_client=statcan_client,
        valet_client=valet_client,
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
