# CAN-13: In-Memory DuckDB Slicing Engine & FastMCP 2.0 Server

**Linear Task:** `BEN-12` / `CAN-13`  
**Owner:** Benjamin Sanchez Zebadua (Solutions Architect & Lead)  
**Assigned Reviewer:** Samir Omer (`@samiromer2`)  
**Feature Branch:** `feat/CAN-13-fastmcp-duckdb-server`  
**Status:** 🟢 **IMPLEMENTATION & PRE-FLIGHT VERIFIED**

---

## 1. Architectural Overview & Design Philosophy

As Solutions Architect & Lead for CanData-MCP, CAN-13 delivers the operational server runtime and data slicing engine for the Canadian Open Data Agentic Platform.

Public open-data endpoints—specifically Statistics Canada WDS and Bank of Canada Valet—often return monolithic, multi-megabyte payloads (such as 50-year SDMX time cubes) that quickly saturate LLM context windows, explode token costs, and trigger reasoning hallucinations. CAN-13 bridges official connectors (`StatCanClient` and `ValetClient`) with frontier LLM agents via an in-memory DuckDB 1.2+ Arrow streaming engine and the 2026 FastMCP standard.

```
                           +----------------------------------+
                           |  LLM Host Agent (Claude, Cursor) |
                           +-----------------+----------------+
                                             | MCP Protocol
                                             v
                           +----------------------------------+
                           |    FastMCP 2.0 Server            |
                           |    (candata_mcp.server)          |
                           +-----------------+----------------+
                                             |
                     +-----------------------+-----------------------+
                     |                                               |
                     v                                               v
     +-------------------------------+               +-------------------------------+
     | StatCanClient (WDS API)       |               | ValetClient (BoC API)         |
     +---------------+---------------+               +---------------+---------------+
                     | Observation Stream                            | Observation Stream
                     +-----------------------+-----------------------+
                                             |
                                             v
                           +----------------------------------+
                           | In-Memory DuckDB Engine          |
                           | (candata_mcp.engine)             |
                           | - PyArrow Table / Stream         |
                           | - DuckDB 1.2+ :memory: SQL       |
                           | - Temporal Slicing & Projections |
                           | - Payload Budget Guard (<3KB)    |
                           +-----------------+----------------+
                                             |
                                             v
                           +----------------------------------+
                           | Sliced Result Payload (<3KB)     |
                           | + Two-Tier Citation Envelope     |
                           +----------------------------------+
```

---

## 2. FastMCP 2026 Tool Protocol Annotations

Under the 2026 Model Context Protocol specification, tools communicate behavioral expectations to host orchestrators through standardized machine-readable annotations (`ToolAnnotations`):

| Tool | `readOnlyHint` | `idempotentHint` | `openWorldHint` | Purpose |
|---|:---:|:---:|:---:|---|
| `query_statcan_vector` | `True` | `True` | `True` | Queries StatCan WDS by vector ID (e.g. `v41690973`), slices via DuckDB |
| `query_statcan_coordinate` | `True` | `True` | `True` | Queries StatCan WDS by cube ID and coordinate (e.g. `18-10-0004-01`, `2.1`) |
| `query_valet_series` | `True` | `True` | `True` | Queries BoC Valet by series name (e.g. `V39079`), slices via DuckDB |
| `query_valet_policy_rate` | `True` | `True` | `True` | Convenience tool for BoC target policy interest rate (`V39079`) |
| `query_valet_cpi` | `True` | `True` | `True` | Convenience tool for BoC CPI measures (`total`, `common`, `median`, `trim`) |
| `execute_sql_analytics` | `True` | `True` | `False` | Executes safe read-only SQL math over in-memory Arrow tables |

### Impact of Annotations:
- **`readOnlyHint=True`**: Authorizes host clients (Claude Desktop, Cursor, Antigravity) to execute data lookups autonomously without surfacing manual confirmation prompts to the user.
- **`idempotentHint=True`**: Informs the agent runtime that redundant calls with identical parameters produce deterministic, side-effect-free results.
- **`openWorldHint=True`**: Signals to host safety systems that network calls hit external Canadian open-data APIs, while `False` on `execute_sql_analytics` confirms execution is strictly local within the sandboxed in-memory DuckDB instance.

---

## 3. In-Memory DuckDB 1.2+ Arrow Streaming Engine

Located in `candata_mcp.engine`, the `DuckDBSlicingEngine` class provides:
1. **Zero-Copy Arrow Conversion:** Converts connector `Observation` tuples directly into PyArrow Tables (`pa.Table.from_pydict`) with strongly-typed schemas (`date: string`, `value: float64`, `release_time: string`, `decimals: int64`).
2. **Arrow Streaming SQL Execution:** Queries use DuckDB's native PyArrow streaming engine (`self._con.execute(query).arrow().read_all()`), eliminating redundant pandas allocations and native Python object overhead.
3. **Payload Budget Enforcement (<3KB):** Every payload is checked against `MAX_PAYLOAD_BYTES = 3072`. If a query exceeds the 3KB threshold, the engine systematically pops data rows while preserving summary statistics (`min_date`, `max_date`, `avg_value`, `min_value`, `max_value`) and the official Two-Tier Citation Envelope, flagging `"truncated": True`.
4. **SQL Security & Sandboxing:** `execute_analytics` enforces that queries start with `SELECT` or `WITH`, prohibits DDL/DML keywords (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `ATTACH`, `PRAGMA`), and enforces row limit clamping (`LIMIT 20`).

---

## 4. Two-Tier Citation Envelope Preservation

Every tool response pairs sliced observations with the standardized Two-Tier Citation Envelope:
- **Tier 1 (Core Verification Tuple):** `(table_id, vector_id, reference_period)`
- **Tier 2 (Metadata Enrichment):** `(coordinate, release_or_revision_date, bilingual_title, canonical_url)`

### Sample Tool Output (<1.5KB Payload):
```json
{
  "source": "Bank of Canada",
  "series_name": "V39079",
  "title": {
    "en": "Policy Interest Rate",
    "fr": "Taux cible du financement à un jour"
  },
  "total_available": 12,
  "returned_count": 3,
  "summary": {
    "filtered_count": 3,
    "min_date": "2024-10-01",
    "max_date": "2024-12-01",
    "avg_value": 4.0,
    "min_value": 3.75,
    "max_value": 4.25
  },
  "data": [
    {"date": "2024-12-01", "value": 3.75},
    {"date": "2024-11-01", "value": 4.0},
    {"date": "2024-10-01", "value": 4.25}
  ],
  "citation": {
    "publisher": "Bank of Canada",
    "core": {
      "table_id": "10-10-0139",
      "vector_id": "V39079",
      "reference_period": "2024-10-01/2024-12-01"
    },
    "enrichment": {
      "coordinate": null,
      "release_or_revision_date": "2024-12-01",
      "bilingual_title": {
        "en": "Policy Interest Rate",
        "fr": "Taux cible du financement à un jour"
      },
      "canonical_url": "https://www.bankofcanada.ca/valet/observations/V39079/json"
    }
  }
}
```

---

## 5. Verification & Pre-Flight Suite

```bash
# 1. Formatting & Linting (Clean)
uv run ruff check .

# 2. Strict Type Checking (0 errors)
uv run pyright

# 3. Complete Offline Test Suite (81 passed)
uv run pytest
```
- **Tests Added:**
  - `tests/test_duckdb_engine.py`: 6 tests (Arrow conversion, temporal slicing, summary statistics, payload budget clamping, date injection checks, SQL analytics sandboxing).
  - `tests/test_server.py`: 10 tests (Tool registration, FastMCP 2026 annotations, StatCan vector & coordinate queries, Valet series, policy rate & CPI convenience tools, SQL analytics execution, server lifecycle cleanup).

---

## 6. Anthropic MCP Inspector Verification & Showcase

The FastMCP server was thoroughly tested end-to-end via the official Anthropic MCP Inspector (`npx @modelcontextprotocol/inspector`):

1. **Tools Catalog & 2026 Annotations ([`01_mcp_inspector_tools_catalog.png`](assets/screenshots/01_mcp_inspector_tools_catalog.png)):**
   - Displays all 6 registered tools (`query_statcan_vector`, `query_statcan_coordinate`, `query_valet_series`, `query_valet_policy_rate`, `query_valet_cpi`, `execute_sql_analytics`).
   - Server identified as `candata-mcp` v0.1.0 over stdio transport.

2. **Bank of Canada Policy Rate Slicing ([`02_mcp_inspector_query_policy_rate.png`](assets/screenshots/02_mcp_inspector_query_policy_rate.png)):**
   - Invocation of `query_valet_policy_rate` with `limit = 3`.
   - Returns strictly bounded <3KB payload, temporal summary statistics (`min_date`, `max_date`, `avg_value`), and the Two-Tier Citation Envelope with official BoC deep-link.

3. **In-Memory DuckDB SQL Analytics ([`03_mcp_inspector_execute_sql_analytics.png`](assets/screenshots/03_mcp_inspector_execute_sql_analytics.png)):**
   - Invocation of `execute_sql_analytics` executing `SELECT count(*) AS total_obs, avg(value) AS avg_rate FROM series` over the streaming Arrow table.
   - Demonstrates deterministic analytical calculations executed in C++ by DuckDB, completely eliminating LLM mental math errors.

4. **Statistics Canada WDS Vector Query ([`04_mcp_inspector_query_statcan_vector.png`](assets/screenshots/04_mcp_inspector_query_statcan_vector.png)):**
   - Invocation of `query_statcan_vector` for CPI vector `v41690973`.
   - Returns sliced temporal observations and Two-Tier Citation Envelope linking back to StatCan Table 18-10-0004-01.

