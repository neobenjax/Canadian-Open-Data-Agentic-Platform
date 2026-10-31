# Task Activities: CAN-17 Edge Cases Resolution (PR #33)

**Feature Branch:** `feat/CAN-17-connector-fastmcp-hardening`  
**Linear Task:** `CAN-17` (`BEN-45`)  
**Target Pull Request:** [PR #33](https://github.com/neobenjax/Canadian-Open-Data-Agentic-Platform/pull/33)  
**Lead Solutions Architect:** Benjamin Sanchez Zebadua (`neobenjax`)  
**Reviewer:** Samir Ibrahim (`samiromer2`)

---

## Activities Checklist

- [x] **Activity 17.1: Preserve Data Quality Flags in DuckDB Arrow Streaming**
  - [x] Add `status_code` (`int | None`) and `symbol_code` (`int | None`) to PyArrow table schema in `DuckDBSlicingEngine.table_from_statcan`.
  - [x] Include `status_code` and `symbol_code` in `DuckDBSlicingEngine.slice_statcan` output rows so downstream agents and benchmarks (e.g. GT-05) have full data quality visibility (Guardrail 6).

- [x] **Activity 17.2: Eliminate Bogus Defaults (`_int(..., 0)`)**
  - [x] Replace `_int(..., 0)` with required positive integer validation for `memberId`, `dimensionPositionId`, and `frequencyCode` in `statcan_wds.py` (Guardrail 6).
  - [x] Fail loudly with `StatCanResponseError` on missing or malformed identifiers instead of fabricating `0`.

- [x] **Activity 17.3: Map Unit of Measure (UOM) in StatCan Series**
  - [x] Extract `uom` / `memberUomCode` in `getSeriesInfoFromVector` and coordinate resolution, populating `StatCanSeriesResult.unit` and `series_title_en` so models distinguish constant dollars (UOM 455) from nominal amounts (GT-08 benchmark fix).

- [x] **Activity 17.4: Punctuation & Accent-Safe Token Search**
  - [x] Strip non-alphanumeric punctuation while preserving table dashes (`34-10-0133`) during tokenization in `search_cubes`.
  - [x] Apply Unicode NFKD normalization (`unicodedata.normalize`) so accented French terms (e.g. `Montréal`, `Québec`) match unaccented queries (`montreal`).

- [x] **Activity 17.5: Verification & FastMCP Pre-Flight**
  - [x] Unit test: Verify `status_code` and `symbol_code` presence in sliced StatCan table output.
  - [x] Unit test: Verify hyphenated and accented queries match in `search_cubes`.
  - [x] Run full pre-flight verification: `python scripts/verify.py` (210 tests passed).
