# Walkthrough & Manual Verification Guide: CAN-17 (BEN-45)

**Feature:** Connector & FastMCP Server Hardening  
**Linear Task:** `BEN-45` (`CAN-17`)  
**Assignee:** Benjamin Sanchez Zebadua (Solutions Architect & Lead)  
**Branch:** `feat/CAN-17-connector-fastmcp-hardening`  
**Milestone:** Milestone 2: LangGraph Multi-Agent Orchestration & Observability (Sprint 2)

---

## 1. Executive Summary

This feature resolves all audit findings (**V-F1 through V-F8**) identified in the CAN-16 API Security and Provenance Audit, strengthens Statistics Canada dimension resolution against silent ambiguity errors (Guardrail 6), and equips the FastMCP server with token-budgeted catalog discovery tools (`search_statcan_cubes`, `get_cube_dimensions`).

---

## 2. Summary of Architectural Changes

### A. Bank of Canada Valet Hardening (`boc_valet.py`)
1. **RFC 7231 `Retry-After` Header Parsing (`V-F1`):** Supports both integer delta-seconds and IMF-fixdate HTTP dates (`Wed, 21 Oct 2026 07:28:00 GMT`), with jittered exponential backoff capped at 60s.
2. **Client-Side Concurrency Cap & 30s TTL Response Cache (`V-F2`):** Wraps outbound calls in an `asyncio.Semaphore(max_concurrency=5)` and caches GET responses for 30s (matching Valet's `max-age=30`).
3. **Bounded Default History (`V-F3`):** Queries without `recent` or date intervals default to `recent=10` to avoid unbounded multi-decade history dumps.
4. **Strict Series Identifier Checking (`V-F4`):** Switched to `re.fullmatch(r"^[A-Za-z0-9_\-]+$")`, rejecting trailing newlines (`"V39079\n"`).
5. **HTTPS Base URL Enforcement (`V-F5`):** Fails closed against insecure HTTP URLs unless explicitly pointing to `localhost` or `127.0.0.1` for mock testing.
6. **Descriptive User-Agent (`V-F6`):** Updated default header to `CanDataMCP/0.1.0 (+https://github.com/neobenjax/Canadian-Open-Data-Agentic-Platform)`.
7. **License Attribution (`V-F7`):** Enriched `CitationEnvelope` with `license_url="https://www.bankofcanada.ca/terms/"`.
8. **Provenance Source Tracking (`V-F8`):** Observation sets now explicitly state `fetched_at_source: "server_date" | "local_clock"`.

### B. Statistics Canada WDS Hardening (`statcan_wds.py`)
1. **Structured `StatCanAmbiguousMemberError` (Guardrail 6):** Exception now carries `member_name`, `dimension_position`, `dimension_name`, `product_id`, and `candidate_ids` for structured programmatic recovery.
2. **Licence Attribution (`STATCAN_LICENCE_URL`):** Enriched `CitationEnvelope` with `license_url="https://www.statcan.gc.ca/en/reference/licence"`.
3. **Catalog Search Discovery:** Added `search_cubes(query, limit, offset)` backed by `getAllCubesListLite` with 24h caching and resilient offline fallback.

### C. FastMCP Discovery Tools & Error Envelopes (`server.py`)
1. **`search_statcan_cubes(query, limit=10, offset=0)`:** Enables LLM planning nodes to search tables by topic (e.g. "cpi", "housing") and receive token-budgeted summaries.
2. **`get_cube_dimensions(product_id, max_members_per_dim=25)`:** Returns dimension hierarchies with member pruning and `has_more_members` flags to avoid blowing agent context windows.
3. **Structured RFC 7807-Style Error Envelopes:** Catches `StatCanAmbiguousMemberError` and returns `error_code: "AMBIGUOUS_MEMBER"` with candidate IDs and actionable recovery guidance for LangGraph Supervisor nodes.

---

## 3. Automated Test Suite Results

Run unified verification:
```bash
python scripts/verify.py
```
**Output:**
```
==========================================================================
 🍁 CANDATA PRE-FLIGHT VERIFICATION: ALL CHECKS PASSED
==========================================================================
 ✅ [0.1s]  Ruff Linter
 ✅ [0.1s]  Ruff Formatter
 ✅ [5.5s]  Pyright Type Checker
 ✅ [31.3s] Pytest Suite (203 passed, 2 deselected in 29.79s)
--------------------------------------------------------------------------
✨ Codebase clean and ready for commit & PR!
```

---

## 4. How to Test as a User (Manual Verification Guide)

### Method 1: Run the Interactive CLI Demo Probe
We have provided an automated probe script that exercises every hardened feature and discovery tool:

```bash
uv run python scripts/demo_mcp_hardening.py
```

**Expected Terminal Output:**
1. **Valet Hardening:**
   - Validates `DEFAULT_USER_AGENT` includes repo contact URI.
   - Shows `_name("V39079\n")` is blocked with `ValueError`.
   - Shows `citation.enrichment.license_url` is `https://www.bankofcanada.ca/terms/`.
   - Shows `fetched_at_source` is `server_date`.
   - Shows insecure `http://www.bankofcanada.ca/valet` fails closed.
2. **StatCan Discovery Tools:**
   - `search_statcan_cubes("housing")` returns official matching tables with product IDs and frequencies.
   - `get_cube_dimensions("18100004", max_members_per_dim=3)` returns pruned dimensions showing `has_more=True`.
   - Simulates `StatCanAmbiguousMemberError` on duplicate municipalities and prints structured candidate IDs `(101, 102)`.

---

### Method 2: Test via the MCP Inspector (Interactive Browser UI)

To inspect tool schemas, annotations, and test live calls in your browser:

1. In your terminal, run:
   ```bash
   npx @modelcontextprotocol/inspector uv run python -m candata_mcp.server
   ```
2. Open your browser at `http://localhost:5173`.
3. In the **Tools** tab:
   - Click on **`search_statcan_cubes`**: Enter `{"query": "cpi", "limit": 3}` and click **Call Tool**. Verify that it returns 3 compact summaries.
   - Click on **`get_cube_dimensions`**: Enter `{"product_id": "18100004", "max_members_per_dim": 5}` and click **Call Tool**. Verify that the dimension members list is pruned to 5 and `has_more_members: true`.
   - Click on **`query_statcan_coordinate`**: Pass an ambiguous coordinate or municipality name and verify that the structured error payload returns `error_code: "AMBIGUOUS_MEMBER"` without crashing the server.
