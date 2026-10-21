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

from candata_mcp.connectors.boc_valet import ValetClient
from candata_mcp.connectors.statcan_wds import StatCanClient
from candata_mcp.engine import DuckDBSlicingEngine

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
        """Register all official Canadian data retrieval and analytics tools."""

        @self.mcp.tool(
            name="query_statcan_vector",
            description=(
                "Query a Statistics Canada time series by vector ID (e.g. 'v41690973'). "
                "Retrieves official observations from Statistics Canada WDS, streams them "
                "through an in-memory DuckDB Arrow engine for temporal slicing, and returns "
                "a strictly <3KB payload complete with Two-Tier Citation Envelope."
            ),
            annotations=READ_ONLY_TOOL,
        )
        async def query_statcan_vector(
            vector_id: str,
            start_date: str | None = None,
            end_date: str | None = None,
            limit: int = 12,
        ) -> dict[str, Any]:
            clean_vid = re.sub(r"^v", "", vector_id.strip(), flags=re.IGNORECASE)
            fetch_n = max(limit * 4, 100) if (start_date or end_date) else max(limit, 12)
            results = await self.statcan_client.get_data_from_vectors([clean_vid], latest_n=fetch_n)
            if not results:
                return {"error": f"No data found for vector ID {vector_id}"}
            return self.engine.slice_statcan(
                results[0],
                start_date=start_date,
                end_date=end_date,
                limit=limit,
                descending=True,
            )

        @self.mcp.tool(
            name="query_statcan_coordinate",
            description=(
                "Query a Statistics Canada data cube by table ID and coordinate "
                "(e.g. table '18-10-0004-01', coordinate '2.1'). "
                "Retrieves official observations from Statistics Canada WDS, streams them "
                "through an in-memory DuckDB Arrow engine, and returns a strictly <3KB "
                "payload complete with Two-Tier Citation Envelope."
            ),
            annotations=READ_ONLY_TOOL,
        )
        async def query_statcan_coordinate(
            table_id: str,
            coordinate: str,
            start_date: str | None = None,
            end_date: str | None = None,
            limit: int = 12,
        ) -> dict[str, Any]:
            fetch_n = max(limit * 4, 100) if (start_date or end_date) else max(limit, 12)
            result = await self.statcan_client.get_data_from_cube(
                product_id=table_id,
                coordinate=coordinate,
                latest_n=fetch_n,
            )
            return self.engine.slice_statcan(
                result,
                start_date=start_date,
                end_date=end_date,
                limit=limit,
                descending=True,
            )

        @self.mcp.tool(
            name="query_valet_series",
            description=(
                "Query a Bank of Canada time series by series name (e.g. 'V39079'). "
                "Retrieves official observations from Bank of Canada Valet API, streams them "
                "through an in-memory DuckDB Arrow engine for temporal slicing, and returns "
                "a strictly <3KB payload complete with Two-Tier Citation Envelope."
            ),
            annotations=READ_ONLY_TOOL,
        )
        async def query_valet_series(
            series_name: str,
            start_date: str | None = None,
            end_date: str | None = None,
            limit: int = 12,
        ) -> dict[str, Any]:
            clean_name = series_name.strip()
            if start_date or end_date:
                result = await self.valet_client.get_observations(
                    clean_name,
                    start_date=start_date,
                    end_date=end_date,
                )
            else:
                fetch_recent = max(limit * 2, 24)
                result = await self.valet_client.get_observations(
                    clean_name,
                    recent=fetch_recent,
                )

            return self.engine.slice_valet(
                result,
                start_date=start_date,
                end_date=end_date,
                limit=limit,
                descending=True,
            )

        @self.mcp.tool(
            name="query_valet_policy_rate",
            description=(
                "Query the official Bank of Canada Policy Interest Rate target (Series V39079). "
                "Convenience tool returning recent policy rate decisions, sliced via in-memory "
                "DuckDB Arrow engine and paired with the Two-Tier Citation Envelope."
            ),
            annotations=READ_ONLY_TOOL,
        )
        async def query_valet_policy_rate(
            start_date: str | None = None,
            end_date: str | None = None,
            limit: int = 10,
        ) -> dict[str, Any]:
            if start_date or end_date:
                result = await self.valet_client.get_policy_rate(
                    start_date=start_date,
                    end_date=end_date,
                )
            else:
                result = await self.valet_client.get_policy_rate(recent=max(limit * 2, 20))

            return self.engine.slice_valet(
                result,
                start_date=start_date,
                end_date=end_date,
                limit=limit,
                descending=True,
            )

        @self.mcp.tool(
            name="query_valet_cpi",
            description=(
                "Query Bank of Canada core inflation measures (e.g. 'total', 'common', "
                "'median', 'trim'). "
                "Retrieves official core CPI series from Valet API, sliced via DuckDB "
                "Arrow streaming, and paired with the Two-Tier Citation Envelope."
            ),
            annotations=READ_ONLY_TOOL,
        )
        async def query_valet_cpi(
            measure: str = "total",
            start_date: str | None = None,
            end_date: str | None = None,
            limit: int = 12,
        ) -> dict[str, Any]:
            if start_date or end_date:
                result = await self.valet_client.get_cpi(
                    measure=measure,
                    start_date=start_date,
                    end_date=end_date,
                )
            else:
                result = await self.valet_client.get_cpi(
                    measure=measure,
                    recent=max(limit * 2, 24),
                )

            return self.engine.slice_valet(
                result,
                start_date=start_date,
                end_date=end_date,
                limit=limit,
                descending=True,
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
                    return {"error": f"No data found for StatCan vector {series_id}"}
                target_result = results[0]
                table = self.engine.table_from_statcan(target_result)
                citation = asdict(target_result.citation())
            elif src in ("valet", "boc", "bank of canada"):
                clean_sid = series_id.strip()
                valet_result = await self.valet_client.get_observations(clean_sid, recent=100)
                table = self.engine.table_from_valet(valet_result)
                citation = asdict(valet_result.citation())
            else:
                return {"error": f"Unsupported source '{source}'. Choose 'statcan' or 'valet'."}

            try:
                results_list = self.engine.execute_analytics(table, sql_query)
            except Exception as e:
                return {"error": f"SQL execution failed: {e}"}

            payload: dict[str, Any] = {
                "source": source,
                "series_id": series_id,
                "sql_query": sql_query,
                "row_count": len(results_list),
                "data": results_list,
                "citation": citation,
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
