# Task Tracking: CAN-13 In-Memory DuckDB Slicing Engine & FastMCP 2.0 Server

**Linear Task:** `BEN-12` / `CAN-13`  
**Owner:** Benjamin Sanchez Zebadua (Solutions Architect & Lead)  
**Branch:** `feat/CAN-13-fastmcp-duckdb-server` (branched from `feat/CAN-11-statcan-wds-client` / PR #16)  
**Reviewer:** Samir Omer (`@samiromer2`)  
**Status:** 🟢 **IMPLEMENTATION & VERIFICATION COMPLETE (Awaiting User Review)**

---

## 📋 Task Overview & Scope

Build the FastMCP 2.0 server (`packages/candata-mcp/src/candata_mcp/server.py`) with an in-memory DuckDB 1.2+ Arrow streaming engine that queries Statistics Canada WDS and Bank of Canada Valet APIs.
The engine slices large upstream datasets down to strictly <3KB payloads suited for LLM context windows, pairs every observation with the official Two-Tier Citation Envelope, and decorates every tool with explicit FastMCP 2026 annotations (`readOnlyHint=True`, `idempotentHint=True`).

---

## 🏗️ Work Breakdown & Checklist

### Phase 1: Environment & Dependency Foundation
- [x] 1.1 Commit/sync documentation status on `feat/CAN-11-statcan-wds-client` and create feature branch `feat/CAN-13-fastmcp-duckdb-server`.
- [x] 1.2 Add `duckdb>=1.2.0`, `mcp>=1.2.0`, and `pyarrow>=17.0.0` to `pyproject.toml` dependencies.
- [x] 1.3 Run `uv sync` to update virtual environment cleanly.
- [x] 1.4 Mark CAN-13 `IN PROGRESS` in Linear and `TASKS.md`.

### Phase 2: In-Memory DuckDB Slicing Engine (`engine.py`)
- [x] 2.1 Design `DuckDBSlicingEngine` class managing an in-memory DuckDB connection (`duckdb.connect(":memory:")`).
- [x] 2.2 Implement PyArrow Table / RecordBatch conversion from connector observation streams.
- [x] 2.3 Implement analytical and temporal slicing queries (date window filtering, ordering, pagination/limit, summary aggregation).
- [x] 2.4 Implement strict payload size enforcement (<3KB) with truncation guards, row capping, and metadata indicators.
- [x] 2.5 Ensure citation envelope preservation through streaming transforms.

### Phase 3: FastMCP 2.0 Server Architecture (`server.py`)
- [x] 3.1 Initialize FastMCP server instance (`CanDataServer` wrapping `MCPServer`) with clean session management.
- [x] 3.2 Define FastMCP 2026 tool annotations (`readOnlyHint=True`, `idempotentHint=True`, `openWorldHint=True/False`).
- [x] 3.3 Implement `query_statcan_vector`: fetch vector data via `StatCanClient`, stream through DuckDB engine, return <3KB payload + citation.
- [x] 3.4 Implement `query_statcan_coordinate`: fetch cube data via `StatCanClient`, stream through DuckDB engine, return <3KB payload + citation.
- [x] 3.5 Implement `query_valet_series`: fetch series via `ValetClient`, stream through DuckDB engine, return <3KB payload + citation.
- [x] 3.6 Implement `query_valet_policy_rate`: specialized convenience tool for policy interest rate (`V39079`).
- [x] 3.7 Implement `query_valet_cpi`: specialized convenience tool for CPI series.
- [x] 3.8 Implement `execute_sql_analytics`: execute safe, read-only DuckDB SQL math over registered series tables to prevent LLM mental math.
- [x] 3.9 Expose CLI entrypoint `candata-mcp` for stdio transport.

### Phase 4: Unit, Integration & Benchmark Test Suite
- [x] 4.1 Create test fixtures for Arrow streaming and DuckDB slicing.
- [x] 4.2 Write unit tests in `tests/test_duckdb_engine.py` (payload sizing <3KB, Arrow conversion, SQL execution, error handling).
- [x] 4.3 Write unit tests in `tests/test_server.py` verifying tool definitions, schemas, annotations, and execution with mocked connectors.
- [x] 4.4 Write integration tests verifying real/mocked two-tier citation envelopes on all tool outputs.
- [x] 4.5 Verify full offline test suite passing (81 passed, 0 failures).

### Phase 5: Verification & Walkthrough Deliverables
- [x] 5.1 Run full pre-flight verification: `uv run ruff check .`, `uv run pyright`, and `uv run pytest`.
- [x] 5.2 Create linked documentation deliverable `docs/CAN_13_FASTMCP_DUCKDB_SERVER.md`.
- [x] 5.3 Write detailed walkthrough guide with manual testing instructions for the developer.
- [x] 5.4 Present implementation to user for approval prior to commit/push.
- [x] 5.5 Commit with Linear formatting: `[CAN-13] feat: implement FastMCP 2.0 server with in-memory DuckDB Arrow engine`.
- [x] 5.6 Push feature branch: `git push -u origin feat/CAN-13-fastmcp-duckdb-server`.
- [x] 5.7 Mark task `IN REVIEW` in Linear and `TASKS.md`: `python scripts/sync_tasks.py --mark-in-review CAN-13`.
- [x] 5.8 Proactively offer automated PR creation with Samir Omer (`@samiromer2`) as reviewer.
