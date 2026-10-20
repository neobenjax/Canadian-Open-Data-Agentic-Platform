# CAN-11: Async Statistics Canada WDS API Client

**Linear:** `BEN-10` / `CAN-11` · **Branch:** `feat/CAN-11-statcan-wds-client` · **Sprint:** 1 · **Owner:** Benjamin Sanchez Zebadua (Lead / Solutions Architect)

---

## 1. Executive Summary

CanData-MCP requires official Statistics Canada figures (such as Consumer Price Index, housing vacancy rates, rent indices, and building permits) accompanied by strict, verifiable citations to prevent hallucination and temporal drift.

`CAN-11` delivers an asynchronous, resilient, and strictly typed client for the [Statistics Canada Web Data Service (WDS) API](https://www.statcan.gc.ca/en/developers/wds) located in `packages/candata-mcp/src/candata_mcp/connectors/statcan_wds.py`. It integrates directly with the Two-Tier Citation Envelope standard established in PR #8 and verified in PR #14.

---

## 2. Deliverables

| Path | Purpose |
|---|---|
| `packages/candata-mcp/src/candata_mcp/connectors/statcan_wds.py` | `StatCanClient` implementation, data models, coordinate resolver, and error hierarchy |
| `packages/candata-mcp/src/candata_mcp/connectors/__init__.py` | Connector exports (`StatCanClient`, `ValetClient`) |
| `packages/candata-mcp/src/candata_mcp/__init__.py` | Top-level package exports |
| `tests/connectors/test_statcan_wds.py` | 15 offline unit tests + 1 opt-in live smoke test |
| `tests/fixtures/statcan/` | Real StatCan WDS responses (CPI Table 18100004, vector v41690973, errors) |
| `docs/CAN_11_STATCAN_WDS_CLIENT_TASKS.md` | Implementation task checklist and tracking |
| `docs/CAN_11_STATCAN_WDS_CLIENT.md` | Architectural deliverable and developer reference (this document) |

---

## 3. Client Architecture & Capabilities

### 3.1 Client API

| Method | Description |
|---|---|
| `get_cube_metadata(product_id, bypass_cache=False)` | Fetches cube metadata (`productId`, dimensions, member hierarchy, titles, release dates) with in-memory TTL caching (default: 1 hour). |
| `resolve_coordinate(product_id, member_names)` | Resolves human-readable dimension names (e.g. `["Canada", "All-items"]`) to the official 10-part coordinate string (e.g. `"2.2.0.0.0.0.0.0.0.0"`). Supports French member names. |
| `get_data_from_cube(product_id, coordinate, latest_n=1)` | Fetches observation slice for a coordinate, sorted chronologically (oldest first). |
| `get_data_from_vectors(vector_ids, latest_n=1)` | Queries one or more vector IDs (`41690973` or `"v41690973"`). |
| `get_series_info(vector_id)` | Fetches vector metadata, UOM code, frequency, and product ID. |
| `clear_cache()` | Invalidates the in-memory metadata TTL cache. |

### 3.2 Two-Tier Citation Envelope Generation

Calling `.citation()` on a `StatCanSeriesResult` returns a `CitationEnvelope` directly compatible with `candata_mcp.citation`:

| Field | StatCan Value | Compliance Notes |
|---|---|---|
| `publisher` | `"Statistics Canada"` | Official publisher |
| `core.table_id` | e.g. `"18-10-0004-01"` | Formatted 4-part hyphenated table identifier |
| `core.vector_id` | e.g. `"v41690973"` | Vector ID with mandatory `"v"` prefix |
| `core.reference_period` | e.g. `"2026-08/2026-09"` | ISO format matching `PERIOD_FORMAT` |
| `enrichment.coordinate` | e.g. `"2.2.0.0.0.0.0.0.0.0"` | Mandatory 10-part dot-separated coordinate |
| `enrichment.release_or_revision_date` | e.g. `"2026-10-19T08:30"` | **Mandatory for StatCan** (`test_statcan_citations_have_a_release_date`), mapped from WDS data point `releaseTime` |
| `enrichment.bilingual_title` | `en` and `fr` | Sourced from `cubeTitleEn` and `cubeTitleFr` |
| `enrichment.canonical_url` | `https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid={productId}01` | Canonical StatCan data table portal link |

---

## 4. Usage Example

```python
import asyncio
from candata_mcp.connectors import StatCanClient

async def main():
    async with StatCanClient() as client:
        # 1. Resolve human dimension names to 10-part coordinate
        coord = await client.resolve_coordinate(18100004, ["Canada", "All-items"])
        print(f"Resolved coordinate: {coord}")  # '2.2.0.0.0.0.0.0.0.0'

        # 2. Query latest 2 observations
        result = await client.get_data_from_cube(18100004, coord, latest_n=2)
        for obs in result.observations:
            print(f"Period: {obs.ref_per} | Value: {obs.value} | Released: {obs.release_time}")

        # 3. Generate verifiable Citation Envelope
        citation = result.citation()
        print(f"Publisher: {citation.publisher}")
        print(f"Core Verification Tuple: {citation.core}")
        print(f"Enrichment Metadata: {citation.enrichment}")

asyncio.run(main())
```

---

## 5. Verification Results

| Check | Tool | Result |
|---|---|---|
| Static Type Analysis | `uv run pyright` | **0 errors, 0 warnings** (strict mode on `packages/candata-mcp/src`) |
| Code Quality & Linting | `uv run ruff check .` | **All checks passed** |
| Offline Unit Tests | `uv run pytest` | **65 passed, 2 deselected** (100% test pass rate) |
| Live API Smoke Tests | `uv run pytest -m live` | **2 passed** (verified against live Statistics Canada WDS and BoC Valet) |
