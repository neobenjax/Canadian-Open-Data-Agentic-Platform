# CAN-17 (BEN-45): Peer Review Feedback Resolution — Task Activities

**Owner:** Benjamin Sanchez Zebadua (Solutions Architect & Lead)  
**Peer Reviewer:** Samir Ibrahim (Data Visualization & Agent Evals Lead)  
**Branch:** `feat/CAN-17-connector-fastmcp-hardening`  
**PR:** [#33](https://github.com/neobenjax/Canadian-Open-Data-Agentic-Platform/pull/33)  

---

## 🎯 Objective
Resolve the 3 blocking review items identified by Samir in PR #33 to enable models in CAN-15 benchmarks to find Toronto in large dimensions, perform multi-word cube discovery with correct match counts, and eliminate fabricated fallback metadata citations.

---

## 📋 Activities Breakdown

### Phase 1: `get_cube_dimensions` Member Search & Paging
- [x] **Activity 17.1:** Add `member_query: str | None = None` and `offset: int = 0` to `StatCanWdsClient.get_cube_dimensions` in `packages/candata-mcp/src/candata_mcp/connectors/statcan_wds.py`.
- [x] **Activity 17.2:** Implement case-insensitive filtering (`member_query.lower() in name.lower()`) on dimension members, apply pagination `[offset: offset + limit]`, and include count metadata (`total_members`, `matched_members_count`, `offset`, `limit`).
- [x] **Activity 17.3:** Expose `member_query` and `offset` in FastMCP tool `get_cube_dimensions` in `packages/candata-mcp/src/candata_mcp/server.py`.

### Phase 2: `search_statcan_cubes` Tokenized Word-Boundary Search
- [x] **Activity 17.4:** Update `search_cubes` in `packages/candata-mcp/src/candata_mcp/connectors/statcan_wds.py` to tokenize query words and match all terms with regex word boundaries (`\b<term>`).
- [x] **Activity 17.5:** Return the true unpaginated match count (`total_results = len(matching_cubes)`) before slicing with `offset` and `limit`, wrapped in `CubeSearchResult`.

### Phase 3: Remove Fabricated Fallback Metadata
- [x] **Activity 17.6:** Remove `FALLBACK_CUBES_LITE` from `statcan_wds.py` and eliminate the silent `except Exception: pass` that served inaccurate titles, dates, and future timestamps.
- [x] **Activity 17.7:** Implement structured `STATCAN_UNAVAILABLE` error payload with retry guidance when WDS catalog is temporarily down.

### Phase 4: Unit Testing & Verification
- [x] **Activity 17.8:** Add unit tests in `tests/connectors/test_statcan_wds.py` and `tests/test_server.py` verifying member search ("Toronto"), offset paging, multi-word matching ("toronto rent"), word-boundary ("rent" vs "current"), and outage handling.
- [x] **Activity 17.9:** Run `python scripts/verify.py` and verify all tests pass with 0 lint, format, or Pyright errors (206 passing tests).
- [x] **Activity 17.10:** Produce walkthrough and manual verification guide in `docs/CAN_17_FEEDBACK_RESOLUTION_WALKTHROUGH.md`.
