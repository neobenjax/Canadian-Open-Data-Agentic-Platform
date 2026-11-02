# CAN-17 (BEN-45): Connector & FastMCP Server Hardening — Task Activities

**Owner:** Benjamin Sanchez Zebadua (Solutions Architect & Lead)  
**Milestone:** Milestone 2: LangGraph Multi-Agent Orchestration & Observability (Sprint 2)  
**Linear Task:** `BEN-45` (`CAN-17`)  
**Branch:** `feat/CAN-17-connector-fastmcp-hardening`

---

## 🎯 Objective
Harden official Canadian REST connectors (Bank of Canada Valet & Statistics Canada WDS) against audit findings V-F1 through V-F8, enforce statutory and data quality reliability envelopes, fail loudly on ambiguous dimension member queries, and expose token-budgeted catalog discovery tools (`search_statcan_cubes`, `get_cube_dimensions`) for upcoming multi-agent planning nodes.

---

## 📋 Activities Breakdown

### Phase 1: Valet Connector Hardening (`boc_valet.py` & `citation.py`)
- [x] **Activity 1.1:** Add `license_url` to `MetadataEnrichment` dataclass in `candata_mcp.citation` (backward-compatible default `None`).
- [x] **Activity 1.2:** Update `ObservationSet` in `boc_valet.py` with `fetched_at_source: str = "server_date"` (or `"local_clock"`) and carry `terms.url` in `citation()`.
- [x] **Activity 1.3:** Enforce strict series name checking via `re.fullmatch(r"^[A-Za-z0-9_\-]+$", value)` (V-F4).
- [x] **Activity 1.4:** Enforce HTTPS-only `base_url` failing closed against non-localhost HTTP (V-F5).
- [x] **Activity 1.5:** Implement dual-format RFC 7231 `Retry-After` parsing (delta-seconds + IMF-fixdate HTTP-date) with exponential backoff and jitter on 429/503 (V-F1).
- [x] **Activity 1.6:** Implement client-side concurrency cap (`asyncio.Semaphore`) and lightweight 30s TTL in-memory response cache (V-F2).
- [x] **Activity 1.7:** Enforce bounded default history (`recent=10` or date interval requirement) (V-F3).
- [x] **Activity 1.8:** Update default User-Agent to descriptive `CanDataMCP/0.1.0 (+https://github.com/neobenjax/Canadian-Open-Data-Agentic-Platform)` (V-F6).

### Phase 2: StatCan Connector Enhancements (`statcan_wds.py`)
- [x] **Activity 2.1:** Ensure `Observation` carries `status_code` (confidentiality suppression) and `symbol_code` (quality grades A through F).
- [x] **Activity 2.2:** Verify and enhance `StatCanAmbiguousMemberError` payload with structured candidate IDs, dimension name, and position (Guardrail 6).
- [x] **Activity 2.3:** Add `get_all_cubes_list_lite()` helper with 24h in-memory TTL caching and offline fallback for discovery tools.

### Phase 3: FastMCP Server Discovery Tools & Error Envelopes (`server.py`)
- [x] **Activity 3.1:** Implement `search_statcan_cubes(query: str, limit: int = 10, offset: int = 0)` with token-budgeted compact summaries.
- [x] **Activity 3.2:** Implement `get_cube_dimensions(product_id: int | str, max_members_per_dim: int = 25)` with pruned member lists and truncation hints.
- [x] **Activity 3.3:** Standardize machine-readable error envelopes (`isError: True`, error codes, troubleshooting suggestions) across tools.

### Phase 4: Unit Testing & Verification
- [x] **Activity 4.1:** Add test cases in `tests/connectors/test_boc_valet.py` covering V-F1 (Retry-After), V-F2 (concurrency & cache), V-F3 (bounded history), V-F4 (`re.fullmatch`), V-F5 (HTTPS fail-closed), V-F6 (User-Agent), V-F7 (`terms.url`), and V-F8 (`fetched_at_source`).
- [x] **Activity 4.2:** Add test cases in `tests/test_server.py` covering `search_statcan_cubes`, `get_cube_dimensions`, and structured ambiguity errors.
- [x] **Activity 4.3:** Run Ruff, Pyright, and Pytest verification suites (`python scripts/verify.py` -> 100% pass across 203 tests).

### Phase 5: User Manual Deliverables & Walkthrough
- [x] **Activity 5.1:** Create interactive manual verification script `scripts/demo_mcp_hardening.py`.
- [x] **Activity 5.2:** Write comprehensive walkthrough and manual testing guide for the user in `docs/CAN_17_CONNECTOR_AND_FASTMCP_HARDENING_WALKTHROUGH.md`.
