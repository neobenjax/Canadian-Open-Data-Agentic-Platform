# Task Tracking: CAN-13 In-Memory DuckDB Slicing Engine & FastMCP 2.0 Server

**Linear Task:** `BEN-12` / `CAN-13`  
**Owner:** Benjamin Sanchez Zebadua (Solutions Architect & Lead)  
**Branch:** `feat/CAN-13-fastmcp-duckdb-server`  
**Reviewer:** Samir Omer (`@samiromer2`)  
**Assignee:** Benjamin Sanchez Zebadua (`@neobenjax`)  
**Status:** 🟢 **REMEDIATION & VERIFICATION COMPLETE (Awaiting User Review)**

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
- [x] 2.1 Design `DuckDBSlicingEngine` class managing an in-memory DuckDB connection.
- [x] 2.2 Implement PyArrow Table / RecordBatch conversion from connector observation streams.
- [x] 2.3 Implement analytical and temporal slicing queries.
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
- [x] 4.2 Write unit tests in `tests/test_duckdb_engine.py`.
- [x] 4.3 Write unit tests in `tests/test_server.py`.
- [x] 4.4 Write integration tests verifying real/mocked two-tier citation envelopes on all tool outputs.
- [x] 4.5 Verify full offline test suite passing (81 passed, 0 failures).

### Phase 5: Verification & Initial PR Submission
- [x] 5.1 Run full pre-flight verification: `uv run ruff check .`, `uv run pyright`, and `uv run pytest`.
- [x] 5.2 Create linked documentation deliverable `docs/CAN_13_FASTMCP_DUCKDB_SERVER.md`.
- [x] 5.3 Write detailed walkthrough guide with manual testing instructions for the developer.
- [x] 5.4 Submit PR #17 to GitHub and assign reviewer `@samiromer2`.

### Phase 6: PR #17 Review Remediation & Engine Hardening
- [x] 6.1 **Housekeeping:** Assign author `@neobenjax` to PR #17 (and assign authors to PR #18 and #19).
- [x] 6.2 **Git Rebase:** Rebase `feat/CAN-13-fastmcp-duckdb-server` onto latest `origin/main` (integrating merged PR #16).
- [x] 6.3 **Security Sandbox Hardening:** Configure DuckDB connection with `enable_external_access=False` and `lock_configuration=True`. Add negative unit tests probing `read_text`, `read_csv`, `glob`, and `SET enable_external_access`.
- [x] 6.4 **Temporal Boundary Normalization:** Implement `normalize_date_bound` so `end_date="2024"` includes full 2024 calendar year. Add unit test.
- [x] 6.5 **Temporal Window Diagnostics:** Return diagnostic note when requested range is older than fetched observation window.
- [x] 6.6 **Deterministic Payload Clamping:** Make `clamp_payload` immutable and guarantee strict <3KB payload under large metadata scenarios.
- [x] 6.7 **Formatting & Lint Hygiene:** Ensure 100% compliance with `ruff format` and `ruff check`.
- [x] 6.8 **Codify Agent Guardrails:** Update `AGENTS.md` and `scripts/sync_tasks.py` with mandatory engine sandboxing, date boundary rules, and automatic PR author assignment.
- [x] 6.9 **Pre-Flight Verification & Walkthrough:** Verify `pytest` (89 passing), `pyright` (0 errors), `ruff` (all checks passed), and provide testing walkthrough for user review.
