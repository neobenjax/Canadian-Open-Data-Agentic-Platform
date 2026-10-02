# CanData-MCP (FastMCP 2.0 Server)
**Package:** `candata-mcp`  
**Description:** High-performance Model Context Protocol (MCP) server connecting LLMs to official Canadian Open Data (Statistics Canada, Bank of Canada, Open Government Canada).

## Core Capabilities
- **Official Canadian REST Adapters:** Direct async client for StatCan WDS API, Bank of Canada Valet API, and Open Government CKAN API.
- **Server-Side DuckDB 1.2+ Slicing:** In-memory Apache Arrow zero-copy memory buffers reducing 200MB payloads to <3KB.
- **MCP 2026 Specification:** Tool annotations (`readOnly`, `idempotent`), sampling support, and progress notifications.
