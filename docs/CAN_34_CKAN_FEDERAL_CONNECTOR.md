# CAN-34: Open Government Canada CKAN Federal Datasets Connector

| | |
|---|---|
| **Task** | CAN-34 / BEN-65, Sprint 3 |
| **Branch** | `feat/CAN-34-ckan-federal-connector` |
| **Component** | `packages/candata-mcp` (Official Canadian Open Data Connectors) |
| **Endpoints Connected** | `https://open.canada.ca/data/api/3/action` (`package_search`, `package_show`, `datastore_search`) |
| **Related** | [CAN-11 StatCan WDS](CAN_11_STATCAN_WDS_CLIENT.md), [CAN-12 BoC Valet](CAN_12_BOC_VALET_CLIENT.md), [CAN-16 API Security Audit](CAN_16_API_SECURITY_AND_PROVENANCE_AUDIT.md), [Two-Tier Citation Standards](CORE_DOCS_CITATION_STANDARDS_ACTIVITIES.md) |

---

## 1. Executive Summary & Purpose

`CAN-34` delivers the third major data bridge of the Canadian Open Data Agentic Platform: a high-speed, type-safe, asynchronous connector to **Open Government Canada** (`open.canada.ca`), powered by the **CKAN v3 Action API**.

While Statistics Canada (`StatCanClient`) covers demographic censuses and CPI series, and the Bank of Canada (`ValetClient`) covers macroeconomic policy and interest rate series, Open Government Canada federates **tens of thousands of open datasets across more than 100 federal departments and crown corporations** (including CMHC, IRCC immigration, Environment and Climate Change Canada climate normals, Transport Canada, Natural Resources Canada, and the Treasury Board of Canada Secretariat).

This connector exposes three new read-only FastMCP 2.0 tools and integrates seamlessly into our in-memory **DuckDB 1.2+ Arrow streaming engine**, guaranteeing bounded `<3KB` responses and deterministic SQL math paired with **Two-Tier Citation Envelopes** and **Data Lineage records**.

---

## 2. Key Architecture & Deliverables

### 2.1 Connector Core (`CKANClient`)
- **Module:** `packages/candata-mcp/src/candata_mcp/connectors/ckan_open_canada.py`
- **Catalog Search (`search_datasets`):** Supports keyword search (`q`), organization scoping (`fq="organization:{org}"`), and DataStore filtering (`fq="datastore_active:true"`), returning paginated `CKANDatasetSummary` records with native bilingual title and organization metadata.
- **Dataset Detail Inspection (`get_dataset`):** Retrieves full dataset metadata (`package_show`), notes/abstracts in French and English, license verification (`Open Government Licence - Canada`), temporal coverage intervals (`time_period_coverage_start` / `end`), and inventory of downloadable resources and active DataStore tables. Includes in-memory TTL caching (default 60s).
- **Tabular DataStore Queries (`query_datastore`):** Queries tabular records (`datastore_search`) by resource UUID with optional filters, text search, field projection, and sorting.

### 2.2 In-Memory DuckDB Arrow Streaming & Token Protection (`DuckDBSlicingEngine`)
- **Arrow Table Conversion (`table_from_ckan`):** Converts CKAN DataStore record streams into in-memory Apache Arrow tables with schema metadata preservation (`resource_id`, `package_id`, `publisher`).
- **Slicing & Budget Clamping (`slice_ckan`):** Aggregates and bounds records strictly under the `<3KB` (`3072` bytes) payload budget using DuckDB query registration, preventing LLM context window blowups.
- **Unified SQL Analytics (`execute_sql_analytics`):** Extends the existing MCP analytical tool to accept `source="ckan"`, allowing LLMs to execute read-only aggregation queries (`avg`, `sum`, `count`, `min`, `max`) without mental math errors.

### 2.3 FastMCP 2.0 Tools Registered
1. `search_open_canada_datasets`: Keyword discovery across federal departments with `readOnly: true`, `idempotent: true`, `openWorld: true`.
2. `get_open_canada_dataset`: Detailed package inspection with Two-Tier Citation Envelope.
3. `query_open_canada_datastore`: Tabular DataStore queries returning sliced Arrow records (<3KB).
4. `execute_sql_analytics`: Now supports `source="ckan"` and `series_id="<resource_id>"` or `"<package_id>:<resource_id>"`.

---

## 3. Provenance & Two-Tier Citation Envelope Conformance

In accordance with `AGENTS.md` §18, every CKAN DataStore query and dataset detail lookup generates a Two-Tier Citation Envelope:

| Citation Envelope Field | CKAN Source Mapping | Pass/Fail or Scored |
|---|---|---|
| **Publisher** | `f"Open Government Canada / {organization_en}"` (or `"Open Government Canada"`) | Core Attribution |
| **`table_id`** (Tier 1) | Dataset `package_id` (slug or UUID); fallback `"CKAN"` for bare DataStore queries | **Strict Pass/Fail** |
| **`vector_id`** (Tier 1) | DataStore `resource_id` (or `package_id` for dataset-level citations) | **Strict Pass/Fail** |
| **`reference_period`** (Tier 1) | `f"{start}/{end}"` or normalized date `YYYY-MM-DD` | **Strict Pass/Fail** |
| **`release_or_revision_date`** (Tier 2) | Dataset `metadata_modified` or resource `last_modified` | Scored Enrichment |
| **`coordinate`** (Tier 2) | Active query descriptor: `f"DataStore ({row_count} rows)"` | Scored Enrichment |
| **`bilingual_title`** (Tier 2) | `BilingualTitle(en=title_en, fr=title_fr)` extracted from native `title_translated` | Scored Enrichment |
| **`canonical_url`** (Tier 2) | `https://open.canada.ca/data/en/dataset/<package_id>` | Scored Enrichment |
| **`license_url`** (Tier 2) | `license_url` (defaults to Open Government Licence - Canada) | Scored Enrichment |

---

## 4. Traps Avoided & Security Hardening

1. **Zero-Tolerance Identifier Validation (`AGENTS.md` §6):**
   - Rejects empty, whitespace, or malformed identifiers (`re.fullmatch(r"^[A-Za-z0-9_\-]+$")`). Prevents parameter injection or path traversals.
2. **HTTP 200 Body-Level Failures (`CAN-16` Finding):**
   - CKAN Action APIs can return HTTP 200 with `{"success": false, "error": {...}}`. `CKANClient` asserts `body["success"] is True` and maps `Not Found Error` to `CKANNotFoundError`.
3. **HTML Outage Detection:**
   - Detects upstream reverse-proxy maintenance pages returning HTML instead of JSON and fails loud with `CKANResponseError`.
4. **Driver-Level DuckDB Sandboxing (`AGENTS.md` §7):**
   - In-memory DuckDB connection enforces `enable_external_access=False` and `lock_configuration=True`. All external file read functions (`read_csv`, `read_text`) are locked down at the engine level.
5. **Polite Backoff & `Retry-After`:**
   - Honors RFC 7231 `Retry-After` on HTTP 429 and 503 responses, applying exponential backoff with jitter on retryable statuses `{429, 500, 502, 503, 504}`.

---

## 5. Verification & Test Suite

The test suite provides 100% offline coverage using `respx` and unit test assertions:
- `tests/connectors/test_ckan_open_canada.py`: 10 targeted tests validating identifier security, HTTPS enforcement, dataset search, bilingual titles, DataStore queries, error handling, HTML outage recovery, and HTTP 500 retries.
- `tests/test_duckdb_engine.py`: Tests PyArrow table conversion (`table_from_ckan`), schema metadata, DuckDB slicing (`slice_ckan`), and SQL analytics execution over CKAN tables.
- `tests/test_server.py`: Verifies tool registration, FastMCP 2026 tool annotations (`read_only_hint`, `idempotent_hint`), and end-to-end tool invocations.

Full verification passing report:
```text
==========================================================================
 🍁 CANDATA PRE-FLIGHT VERIFICATION: ALL CHECKS PASSED
==========================================================================
 ✅ [0.2s]  Ruff Linter
 ✅ [0.1s]  Ruff Formatter
 ✅ [8.1s]  Pyright Type Checker
 ✅ [36.4s] Pytest Suite (342 passed, 3 deselected in 33.36s)
--------------------------------------------------------------------------
✨ Codebase clean and ready for commit & PR!
```
