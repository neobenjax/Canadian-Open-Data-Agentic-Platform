# GTA Ground Truth Benchmark Execution — Task Activities

**Owner:** Benjamin Sanchez Zebadua (Solutions Architect & Lead)  
**Evaluator Role:** Samir Ibrahim / Benjamin Sanchez Zebadua  
**Milestone:** FastMCP 2.0 Core & Ground-Truth Benchmarks / Multi-Agent Orchestration  
**Target File:** `collaboration/benchmarks/gta_ground_truth_v1.json`  
**Linear Task:** `CAN-17` (`BEN-45`: Connector & FastMCP Server Hardening)  

---

## 🎯 Objective
Verify the operational status of the `candata-mcp` MCP server tools in Antigravity and execute all 15 benchmark questions from `collaboration/benchmarks/gta_ground_truth_v1.json` using official Statistics Canada and Bank of Canada MCP tools (`search_statcan_cubes`, `get_cube_dimensions`, `query_statcan_coordinate`, `query_statcan_vector`, `query_valet_series`, `query_valet_policy_rate`), validate two-tier citations, verify data quality/reliability flags, grade the outputs against ground-truth expectations, and generate a comprehensive evaluation scorecard.

---

## 📋 Activities Breakdown

### Phase 1: MCP Server Tool Verification & Connectivity
- [x] **Activity 1.1:** Confirm `candata-mcp` registration in `C:\Users\besaz\.gemini\config\mcp_config.json`.
- [x] **Activity 1.2:** Inspect MCP schema availability in `C:\Users\besaz\.gemini\antigravity\mcp\candata-mcp\`.
- [x] **Activity 1.3:** Test live tool execution for `search_statcan_cubes`, `query_statcan_vector`, and `query_statcan_coordinate` to verify upstream WDS & DuckDB connectivity.

### Phase 2: Implementation Plan & User Requirements Alignment
- [x] **Activity 2.1:** Draft formal Implementation Plan artifact detailing execution batching, citation validation, scoring rubric, and error handling.
- [x] **Activity 2.2:** Align user requirements on execution efficiency, model naming (Gemini 3.8 Flash), task tracking (`CAN-17`), and report telemetry persistence.

### Phase 3: Benchmark Question Execution via Native MCP Tools
- [x] **Activity 3.1:** Execute Category 1: Rental Market Questions:
  - [x] `GT-01`: 2-Bedroom Rent in Toronto CMA (2024 vs 2025) via `query_statcan_vector` (Table `34-10-0133-01`) -> **PASS** ($2,045 vs $1,972, +$73, +3.7%).
  - [x] `GT-02`: Purpose-Built Rental Vacancy Rate in Toronto CMA (2023, 2024, 2025) via Table `34-10-0130-01` -> **PASS** (3.0% vs 1.4%, +1.6 pp).
  - [x] `GT-03`: Oshawa vs. Toronto 2-Bedroom Rent Comparison (2025) via Table `34-10-0133-01` -> **PASS** (Oshawa $1,762, Toronto $2,045, +16.1% premium).
  - [x] `GT-04`: Highest Vacancy Rate among Toronto, Oshawa, and Hamilton (2025) via Table `34-10-0130-01` -> **PASS** (Oshawa 3.6% > Hamilton 3.5% > Toronto 3.0%).
- [x] **Activity 3.2:** Execute Category 2: Supply & Prices Questions:
  - [x] `GT-05`: Housing Starts in Toronto CMA (Calendar 2024 vs 2025 sum of monthly starts) via Table `34-10-0154-01` -> **PASS** (2025: 26,087 vs 2024: 37,718, -30.8%).
  - [x] `GT-06`: New Housing Price Index (NHPI) in Toronto CMA (Dec 2024 vs Dec 2025) via Table `18-10-0205-01` -> **PASS** (109.3 vs 113.1, -3.4%).
- [x] **Activity 3.3:** Execute Category 3: Rent vs. Income Questions:
  - [x] `GT-07`: 2024 Rent Share of Median After-Tax Income in Toronto CMA via Tables `34-10-0133-01` & `11-10-0190-01` -> **PASS** ($23,664 / $82,500 = 28.7%).
  - [x] `GT-08`: 2019-2024 Rent Growth vs. Median After-Tax Income Growth (constant vs current dollars trap) via Tables `34-10-0133-01` & `11-10-0190-01` -> **PASS** (Rent +26.2% nominal, Income +2.1% real).
  - [x] `GT-09`: Vintage Mismatch Handling (2021 Census income vs 2025 rent flag) via Table `11-10-0190-01` -> **PASS** (Defended boundary, flagged 5-yr mismatch).
- [x] **Activity 3.4:** Execute Category 4: Inflation & Rates Questions:
  - [x] `GT-10`: Toronto Rented Accommodation vs. All-Items CPI Inflation (2025) via Table `18-10-0005-01` -> **PASS** (Rented accommodation 3.1% > All-items 1.8%).
  - [x] `GT-11`: Toronto vs. Canada Shelter Inflation Comparison (2025) via Table `18-10-0005-01` -> **PASS** (Toronto 2.1% < Canada 3.0%).
  - [x] `GT-12`: August 2026 YoY Shelter Inflation vs. All-Items CPI via Table `18-10-0004-01` -> **PASS** (Shelter fell -0.5% while All-items rose +2.1%).
  - [x] `GT-13`: Bank of Canada Policy Rate Changes & Levels in 2025 via Bank of Canada Valet series `V39079` -> **PASS** (4 changes: 3.25% -> 2.25%, with all 4 effective dates).
- [x] **Activity 3.5:** Execute Category 5: Refusal / Boundary Defense Questions:
  - [x] `GT-14`: Toronto Mortgage Interest Cost Inflation Refusal (decline unanswerable city-level subcomponent, provide Canada figure) via Table `18-10-0005-01` -> **PASS** (Toronto declined, Canada +5.3% provided).
  - [x] `GT-15`: 1985 Historical 2-Bedroom Rent in Toronto CMA Refusal (decline out-of-bounds period prior to 1992 start date) via Table `34-10-0133-01` -> **PASS** (Declined 1985, proved series begins 1992).

### Phase 4: Scoring, Analysis & Deliverables
- [x] **Activity 4.1:** Verify Two-Tier Citation Envelopes (Tier 1 core identifiers, Tier 2 enrichment).
- [x] **Activity 4.2:** Grade outputs against expected numeric tolerances, comparison judgments, and refusal behaviors (15/15 = 100.0%).
- [x] **Activity 4.3:** Generate comprehensive Benchmark Scorecard artifact and markdown report in `collaboration/benchmarks/gta_benchmark_run_gemini_3_8_flash_2026_10_30.md`.
- [x] **Activity 4.4:** Provide user manual walkthrough explaining results, methodology, and how to re-run queries independently.
