# CAN-17 (BEN-45): Peer Review Feedback Resolution — Walkthrough & Stress Test Guide

**Branch:** `feat/CAN-17-connector-fastmcp-hardening`  
**PR:** [#33](https://github.com/neobenjax/Canadian-Open-Data-Agentic-Platform/pull/33)  
**Author:** Benjamin Sanchez Zebadua (`neobenjax`) — Solutions Architect & Lead  
**Peer Reviewer:** Samir Ibrahim (`samiromer2`) — Data Visualization & Agent Evals Lead  

---

## 1. Executive Summary

During peer review of PR #33, Samir Ibrahim re-ran the official CAN-15 benchmark with `claude-sonnet-5-5`. The results showed major architectural progress:
* **`main` baseline (Oct 22):** 3 Correct, 0 Partial, 12 Abstained, 0 Wrong
* **PR #33 (Oct 28):** **6 Correct, 3 Partial, 6 Abstained, 0 Wrong**

However, 3 blocking issues in the discovery tools were identified that prevented models from reaching Toronto data and risked unflagged fallback citations. This deliverable directly resolves all 3 blocking issues:

| # | Samir's Observation | Technical Solution | Validation Result |
|:---|:---|:---|:---|
| 1 | `get_cube_dimensions` capped members at 100 with no filter or offset, cutting off Toronto (`memberId: 125` at index 160 of 247). | Added `member_query` (case-insensitive name search) and `offset` pagination directly to `get_cube_dimensions`. | Directly retrieves Toronto (`memberId 125`) from 247 members; offset 150 pages into position 160. |
| 2 | `search_statcan_cubes` matched only contiguous substrings (`"toronto rent"` -> 0, `"rent"` matched `"current account"`), and returned page length instead of total matches. | Tokenized queries across whitespace and matched all terms using regex word boundaries (`\b<term>`). Wrapped in `CubeSearchResult` returning unpaginated `total_results`. | `"toronto rent"` matches 34-10-0133-01; `"rent"` strictly rejects `"current account"`; `total_results` accurately counts 2 matches when limit=1. |
| 3 | `FALLBACK_CUBES_LITE` served hardcoded metadata with inaccurate titles, start dates, and future timestamps (2026) for 24h on transient errors. | Completely eliminated `FALLBACK_CUBES_LITE`. Raised structured `StatCanUnavailableError` with retry guidance and actionable error payloads. | Outages return `STATCAN_UNAVAILABLE` with `retry_after: 30` and `suggested_action`. Zero fabricated provenance. |

---

## 2. Code Changes Summary

1. [`packages/candata-mcp/src/candata_mcp/connectors/statcan_wds.py`](file:///d:/AI/PARTY%20PROJECTS/AI%20Engineer%20-%20Collaboration/packages/candata-mcp/src/candata_mcp/connectors/statcan_wds.py):
   - Added `StatCanUnavailableError` with `message` and `retry_after`.
   - Added `CubeSearchResult(total_results: int, cubes: tuple[CubeSummary, ...])` implementing iteration protocols for backward compatibility.
   - Removed `FALLBACK_CUBES_LITE`.
   - Rewrote `get_all_cubes_list_lite` to fail loud on WDS outages with actionable errors.
   - Rewrote `search_cubes` to tokenize multi-word terms and apply regex word boundaries (`\b<term>`).
2. [`packages/candata-mcp/src/candata_mcp/server.py`](file:///d:/AI/PARTY%20PROJECTS/AI%20Engineer%20-%20Collaboration/packages/candata-mcp/src/candata_mcp/server.py):
   - Updated `search_statcan_cubes` tool to report unpaginated `total_results` and structured `STATCAN_UNAVAILABLE` error payloads.
   - Updated `get_cube_dimensions` tool to accept `member_query`, `dimension_name`, `offset`, and `limit`, returning rich pagination metadata (`matched_members_count`, `total_members`, `has_more_members`).
3. [`tests/connectors/test_statcan_wds.py`](file:///d:/AI/PARTY%20PROJECTS/AI%20Engineer%20-%20Collaboration/tests/connectors/test_statcan_wds.py) & [`tests/test_server.py`](file:///d:/AI/PARTY%20PROJECTS/AI%20Engineer%20-%20Collaboration/tests/test_server.py):
   - Added unit tests for multi-word search, word boundary isolation, outage error payloads, member query filtering, and offset pagination.
4. [`scripts/stress_test_pr33_feedback.py`](file:///d:/AI/PARTY%20PROJECTS/AI%20Engineer%20-%20Collaboration/scripts/stress_test_pr33_feedback.py):
   - Standalone stress-testing script validating all 3 observations against real-world inputs.

---

## 3. How to Test & Verify Manually

Run the dedicated stress-testing script:
```bash
uv run python scripts/stress_test_pr33_feedback.py
```

### Expected Output:
```
============================================================================
 🍁 STRESS-TESTING PR #33 RESOLUTION AGAINST SAMIR'S REVIEW COMMENTS
============================================================================

[STRESS 1] Validating get_cube_dimensions member search & pagination...
 ✅ member_query='Toronto' successfully retrieved Toronto (memberId 125) from 247!
 ✅ Pagination offset=150, limit=15 reached position 160 (Toronto) successfully!

[STRESS 2] Validating search_statcan_cubes tokenized word-boundary matching...
 ✅ Multi-word query 'housing rent' matched 34-10-0133-01!
 ✅ Multi-word query 'two bedroom rent' matched 34-10-0133-01!
 ✅ Word boundary check: 'rent' matched CMHC & CPI, rejected 'current account'!
 ✅ Pagination count check: total_results reflects 2 while page length is 1!

[STRESS 3] Validating FALLBACK_CUBES_LITE elimination and outage error handling...
 ✅ Confirmed FALLBACK_CUBES_LITE has been completely removed from module scope.
 ✅ Outage produced structured STATCAN_UNAVAILABLE payload with retry guidance.

============================================================================
 🍁 ALL STRESS TESTS PASSED: SAMIR'S 3 BLOCKING OBSERVATIONS ARE 100% RESOLVED!
============================================================================
```

Run pre-flight verification:
```bash
python scripts/verify.py
```
**Result:** 206 passed, 2 deselected in 19.67s. Zero Ruff errors, zero Pyright errors.
