# Task Checklist: CAN-17 UOM CodeSets & Coordinate Normalization

Linear Issue: [CAN-17](https://linear.app/canopendataagenticplatform/issue/BEN-45) / BEN-45  
Branch: `feat/CAN-17-connector-fastmcp-hardening`  
Status: Verified & Awaiting User Approval to Push

---

### Phase 1: Authoritative StatCan WDS CodeSets
- [x] 1.1 Ingest all 465 official UOM codes from StatCan WDS `getCodeSets` into `packages/candata-mcp/src/candata_mcp/connectors/statcan_codesets.py` (`STATCAN_UOM_EN`, `STATCAN_UOM_FR`).
- [x] 1.2 Implement `get_uom_codes()` and `get_uom_name()` in `StatCanClient` with 24-hour TTL caching and offline snapshot fallback.
- [x] 1.3 Remove hard-coded `_COMMON_UOM_CODES` and synthetic `"UOM {code}"` fallback; enforce `unit: None` on unmapped or code `0` members.

### Phase 2: Coordinate Normalization & Auto-Padding
- [x] 2.1 Implement `normalize_coordinate(coordinate: str) -> str` to auto-pad coordinates with zeroes up to 10 parts (e.g. `"23"` -> `"23.0.0.0.0.0.0.0.0.0"`).
- [x] 2.2 Validate coordinate segments (non-empty, numeric, $\le 10$ parts).
- [x] 2.3 Integrate `normalize_coordinate` into `StatCanClient.get_data_from_cube` and `CanDataServer.query_statcan_coordinate`.

### Phase 3: Engine Pipeline & Lineage Exposure
- [x] 3.1 Update `_resolve_series_details_from_coord` to extract `uom_code` alongside `uom_name`.
- [x] 3.2 Add `unit_code: int | None = None` to `StatCanSeriesResult`.
- [x] 3.3 Embed `"unit_code"` in Arrow schema metadata in `DuckDBSlicingEngine.table_from_statcan`.
- [x] 3.4 Expose `"unit_code"` and `"unit"` in `DuckDBSlicingEngine.slice_statcan` payload.

### Phase 4: Unit Test Suite & Pinning
- [x] 4.1 Add test pinning UOM codes: `300` -> `"Units"`, `81` -> `"Dollars"`, `239` -> `"Percent"`, `257` -> `"Rate"`, `455` -> `"2024 constant dollars"`.
- [x] 4.2 Add test verifying code `0` and unknown codes return `unit=None` with `unit_code`.
- [x] 4.3 Add test for `normalize_coordinate`: `"23"` -> `"23.0.0.0.0.0.0.0.0.0"`, `"1.2"` -> `"1.2.0.0.0.0.0.0.0.0"`, and invalid inputs.
- [x] 4.4 Add test verifying `query_statcan_coordinate` succeeds with short coordinate `"23"`.

### Phase 5: Verification & Walkthrough
- [x] 5.1 Run `python scripts/verify.py` (Ruff lint, format check, Pyright strict, pytest: 213 passed, 2 deselected).
- [x] 5.2 Produce detailed walkthrough guide for manual verification.
