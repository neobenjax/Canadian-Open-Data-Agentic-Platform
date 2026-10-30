# GTA Housing & Macroeconomic Ground-Truth Benchmark Run (v1)

**Execution Date:** 2026-10-30  
**Model:** Gemini 3.8 Flash  
**Agent Harness:** Antigravity Pair Programmer  
**Linear Task:** `CAN-17` (`BEN-45`: Connector & FastMCP Server Hardening)  
**Evaluator:** Benjamin Sanchez Zebadua (Solutions Architect & Lead) / Samir Ibrahim (Data Viz & Evals)  
**Benchmark Specification:** [`collaboration/benchmarks/gta_ground_truth_v1.json`](gta_ground_truth_v1.json)  
**MCP Server:** `candata-mcp` (FastMCP 2.0 + DuckDB 1.2+ In-Memory Engine)  

---

## 📊 Benchmark Scorecard Summary

| Metric | Result | Benchmark Target |
| :--- | :--- | :--- |
| **Total Test Questions** | 15 | 15 |
| **Questions Passed** | **15** | 15 |
| **Questions Failed** | **0** | 0 |
| **Accuracy Score** | **100.0%** | ≥ 90.0% |
| **Tier 1 Citation Fidelity** | **100.0%** (15/15) | 100.0% |
| **Tier 2 Enrichment Fidelity** | **100.0%** (15/15) | ≥ 95.0% |
| **Trap Avoidance Defense** | **100.0%** (15/15) | 100.0% |
| **Average Tool Latency** | ~2.4s per query | < 5.0s |
| **Payload Budget Compliance** | 100% (<3072 bytes per response) | 100% |

### Category Breakdown

| Category | Questions | Eval Type | Pass Rate |
| :--- | :--- | :--- | :--- |
| **Rental Market** | GT-01 to GT-04 | `numeric`, `comparison` | **100% (4/4)** |
| **Supply & Prices** | GT-05 to GT-06 | `numeric` | **100% (2/2)** |
| **Rent vs. Income** | GT-07 to GT-09 | `numeric`, `flag` | **100% (3/3)** |
| **Inflation & Rates** | GT-10 to GT-13 | `comparison`, `numeric` | **100% (4/4)** |
| **Unanswerable / Refusal** | GT-14 to GT-15 | `refusal` | **100% (2/2)** |

---

## 🔬 Detailed Benchmark Results (GT-01 to GT-15)

### Category 1: Rental Market

#### GT-01: Two-Bedroom Rent in Toronto CMA (2024 vs 2025)
- **Question:** What was the average monthly rent for a two-bedroom unit in the Toronto CMA in the October 2025 CMHC Rental Market Survey, and how much did it change from 2024?
- **MCP Tool Call:** `query_statcan_vector(vector_id="v3823103", limit=2)`
- **Retrieved Values:**
  - 2025: **$2,045.00**
  - 2024: **$1,972.00**
  - Dollar Change: **+$73.00**
  - Percentage Change: **+3.7%**
- **Citation Envelope:**
  - *Tier 1:* Table `34-10-0133-01`, Vector `v3823103`, Reference Periods `2024`, `2025`, Publisher `Statistics Canada`
  - *Tier 2:* Coordinate `125.3.3.0.0.0.0.0.0.0`, Unit `Dollars` (Code 81), Release Date `2025-12-17T08:30`
- **Trap Defense:** Avoided asking rents from listings (Rentals.ca ~$2,632); cited official CMHC survey rents including sitting tenants under rent control.
- **Grade:** **PASS** (Exact match)

#### GT-02: Purpose-Built Rental Vacancy Rate in Toronto CMA (2023–2025)
- **Question:** What was the purpose-built rental vacancy rate in the Toronto CMA in 2025, and how does it compare to 2023?
- **MCP Tool Call:** `query_statcan_vector(vector_id="v1930324", limit=3)`
- **Retrieved Values:**
  - 2025: **3.0%**
  - 2024: **2.5%**
  - 2023: **1.4%**
  - Change (2023 to 2025): **+1.6 percentage points** (pp)
- **Citation Envelope:**
  - *Tier 1:* Table `34-10-0130-01`, Vector `v1930324`, Reference Periods `2023`, `2024`, `2025`, Publisher `Statistics Canada`
  - *Tier 2:* Coordinate `24.0.0.0.0.0.0.0.0.0`, Unit `Rate` (Code 257), Release Date `2025-12-17T08:30`
- **Trap Defense:** Reported difference strictly in percentage points (not percent); avoided mixing national average (2.2%) with Toronto rate.
- **Grade:** **PASS** (Exact match)

#### GT-03: Oshawa CMA vs. Toronto CMA Two-Bedroom Rent (2025)
- **Question:** In 2025, how did the average two-bedroom rent in the Oshawa CMA (Durham) compare with the Toronto CMA?
- **MCP Tool Call:** `query_statcan_vector(vector_id="v3823091", limit=1)` and `query_statcan_vector(vector_id="v3823103", limit=1)`
- **Retrieved Values:**
  - Oshawa CMA: **$1,762.00**
  - Toronto CMA: **$2,045.00**
  - Gap: **$283.00**
  - Toronto Premium: **+16.1%** (relative to Oshawa)
- **Citation Envelope:**
  - *Tier 1:* Table `34-10-0133-01`, Vectors `v3823091` (Oshawa) and `v3823103` (Toronto), Publisher `Statistics Canada`
  - *Tier 2:* Coordinates `104.3.3.0.0.0.0.0.0.0` and `125.3.3.0.0.0.0.0.0.0`, Unit `Dollars`
- **Trap Defense:** Recognized that Durham Region is covered under the Oshawa CMA, while Peel, York, and Halton reside within Toronto CMA.
- **Grade:** **PASS** (Exact match)

#### GT-04: Highest Vacancy Rate Among Toronto, Oshawa, and Hamilton (2025)
- **Question:** Among the Toronto, Oshawa and Hamilton CMAs, which had the highest rental vacancy rate in 2025?
- **MCP Tool Call:** `query_statcan_vector` for `v1930324` (Toronto), `v1930312` (Oshawa), `v1930306` (Hamilton)
- **Retrieved Values:**
  - Toronto CMA: **3.0%**
  - Oshawa CMA: **3.6%**
  - Hamilton CMA: **3.5%**
  - Decision: **Oshawa had the highest vacancy rate**
- **Citation Envelope:**
  - *Tier 1:* Table `34-10-0130-01`, Vectors `v1930324`, `v1930312`, `v1930306`
  - *Tier 2:* Coordinates `24.0...`, `11.0...`, `6.0...`, Unit `Rate`
- **Trap Defense:** Did not round or conflate Oshawa (3.6%) and Hamilton (3.5%), preserving the crucial 0.1 pp difference.
- **Grade:** **PASS** (Exact match)

---

### Category 2: Supply & Prices

#### GT-05: Housing Starts in Toronto CMA (Calendar 2024 vs 2025)
- **Question:** How many housing units were started in the Toronto CMA in calendar year 2025, and how does that compare with 2024?
- **MCP Tool Call:** `query_statcan_vector(vector_id="v42127475", start_date="...", end_date="...")`
- **Retrieved Values:**
  - 2025 Total Starts: **26,087 units** (12-month non-seasonally adjusted sum: 12 × 2173.9167)
  - 2024 Total Starts: **37,718 units** (12-month non-seasonally adjusted sum: 12 × 3143.1667)
  - Change: **-11,631 units (-30.8%)**
- **Citation Envelope:**
  - *Tier 1:* Table `34-10-0154-01`, Vector `v42127475`, Reference Period `2024-01/2025-12`
  - *Tier 2:* Coordinate `23.1.1.0.0.0.0.0.0.0`, Unit `Units` (Code 300)
- **Trap Defense:** Correctly summed actual unadjusted monthly start figures rather than quoting or summing Seasonally Adjusted Annual Rates (SAAR).
- **Grade:** **PASS** (Exact match)

#### GT-06: New Housing Price Index (NHPI) Toronto (Dec 2024 vs Dec 2025)
- **Question:** How did new home prices in the Toronto CMA change between December 2024 and December 2025?
- **MCP Tool Call:** `query_statcan_vector(vector_id="v111955499", start_date="2024-12-01", end_date="2025-12-31")`
- **Retrieved Values:**
  - Dec 2024: **113.1**
  - Dec 2025: **109.3**
  - Change: **-3.4%**
- **Citation Envelope:**
  - *Tier 1:* Table `18-10-0205-01`, Vector `v111955499`, Reference Period `2024-12/2025-12`
  - *Tier 2:* Coordinate `20.1.0.0.0.0.0.0.0.0`, Unit `Index, 201612=100` (Code 347)
- **Trap Defense:** Quoted the index value directly and stated units as Index (201612=100); did not conflate with TRREB/CREA average resale dollar prices.
- **Grade:** **PASS** (Exact match)

---

### Category 3: Rent vs. Income

#### GT-07: 2024 Rent Share of Toronto CMA Median After-Tax Income
- **Question:** In 2024, what share of the Toronto CMA's median after-tax income would a year of average two-bedroom rent take?
- **MCP Tool Call:** `query_statcan_vector(vector_id="v3823103")` and `query_statcan_vector(vector_id="v96415851")`
- **Retrieved Values:**
  - 2024 Annual Rent: **$23,664.00** ($1,972/mo × 12)
  - 2024 Median After-Tax Income: **$82,500.00**
  - Rent Share of Income: **28.7%** ($23,664 / $82,500)
- **Citation Envelope:**
  - *Tier 1:* Tables `34-10-0133-01` (`v3823103`) and `11-10-0190-01` (`v96415851`), Reference Period `2024`
  - *Tier 2:* Coordinates `125.3.3...` and `17.12.1...`, Units `Dollars` and `2024 constant dollars`
- **Trap Defense:** Synced vintages strictly to 2024 (avoiding pairing 2025 rent with 2024 income); noted income covers all economic families (renters and owners combined).
- **Grade:** **PASS** (Exact match)

#### GT-08: 2019 to 2024 Rent Growth vs. Median After-Tax Income Growth
- **Question:** Between 2019 and 2024, how did average two-bedroom rent growth in the Toronto CMA compare with growth in median after-tax income?
- **MCP Tool Call:** `query_statcan_vector` for `v3823103` and `v96415851` over 2019–2024
- **Retrieved Values:**
  - Rent 2019: **$1,563.00** | Rent 2024: **$1,972.00** | Growth: **+26.2%** (Nominal Dollars)
  - Income 2019: **$80,800.00** | Income 2024: **$82,500.00** | Growth: **+2.1%** (2024 Constant Dollars)
- **Citation Envelope:**
  - *Tier 1:* Tables `34-10-0133-01` and `11-10-0190-01`
  - *Tier 2:* Coordinates `125.3.3...` and `17.12.1...`
- **Trap Defense:** Explicitly highlighted the constant vs. current dollars discrepancy: rent is nominal dollars while income is constant 2024 dollars (real purchasing power growth above inflation).
- **Grade:** **PASS** (Exact match)

#### GT-09: Vintage Mismatch Defense (2021 Census Income vs. 2025 Rent)
- **Question:** Using median household income from the 2021 Census, what share of income does the 2025 average two-bedroom rent in Toronto represent?
- **Behavior:** Refused/Flagged vintage mismatch prior to computation.
- **Retrieved Findings & Defense:**
  - Flagged that 2021 Census income reflects calendar year 2020 income, creating a 5-year vintage distortion against 2025 rent.
  - Recommended the consistent, same-year comparison available from the Canadian Income Survey (2024) instead.
- **Citation Envelope:** Tables `11-10-0190-01` and `34-10-0133-01`
- **Trap Defense:** Refused to generate a misleading ~28.9% figure by pairing unadjusted 2020 Census income with 2025 rent.
- **Grade:** **PASS** (Boundary defended)

---

### Category 4: Inflation & Rates

#### GT-10: Toronto Rented Accommodation vs. All-Items CPI (2025)
- **Question:** In 2025, did the cost of rented accommodation in Toronto rise faster or slower than overall consumer prices? Give both annual inflation rates.
- **MCP Tool Call:** `query_statcan_vector(vector_id="v41695188")` and `query_statcan_vector(vector_id="v41695186")`
- **Retrieved Values:**
  - Rented Accommodation (2024: 158.6, 2025: 163.5): **+3.1%**
  - All-Items Toronto (2024: 164.7, 2025: 167.7): **+1.8%**
  - Decision: **Rented accommodation rose Faster than overall consumer prices**
- **Citation Envelope:**
  - *Tier 1:* Table `18-10-0005-01`, Vectors `v41695188` and `v41695186`
  - *Tier 2:* Coordinates `16.80.0.0.0.0.0.0.0.0` and `16.2.0.0.0.0.0.0.0.0`, Unit `2002=100` (Code 17)
- **Trap Defense:** Used "Rented accommodation" (official city-level aggregate) rather than national "Rent", and annual averages rather than December-to-December.
- **Grade:** **PASS** (Exact match)

#### GT-11: Toronto Shelter Inflation vs. Canada Shelter Inflation (2025)
- **Question:** How did shelter inflation in Toronto in 2025 compare with shelter inflation for Canada as a whole?
- **MCP Tool Call:** `query_statcan_vector(vector_id="v41695187")` and `query_statcan_vector(vector_id="v41693348")`
- **Retrieved Values:**
  - Toronto Shelter (2024: 187.3, 2025: 191.3): **+2.1%**
  - Canada Shelter (2024: 182.3, 2025: 187.8): **+3.0%**
  - Decision: **Toronto shelter inflation was LOWER than Canada shelter inflation**
- **Citation Envelope:**
  - *Tier 1:* Table `18-10-0005-01`, Vectors `v41695187` and `v41693348`
  - *Tier 2:* Coordinates `16.79.0.0.0.0.0.0.0.0` and `2.79.0.0.0.0.0.0.0.0`
- **Trap Defense:** Dispelled the common assumption that Toronto shelter always rises faster than national shelter; the verified data proved Toronto was 0.9 pp lower.
- **Grade:** **PASS** (Exact match)

#### GT-12: August 2026 YoY Shelter Inflation vs. All-Items CPI
- **Question:** In August 2026, how did shelter prices in Toronto change year over year, compared with overall consumer prices?
- **MCP Tool Call:** `query_statcan_vector` for `v41692889` (Shelter) and `v41692888` (All-items)
- **Retrieved Values:**
  - Toronto Shelter (Aug 2025: 191.4, Aug 2026: 190.5): **-0.5%** (Fell)
  - Toronto All-Items (Aug 2025: 168.1, Aug 2026: 171.7): **+2.1%** (Rose)
  - Decision: **Shelter prices fell while overall consumer prices rose**
- **Citation Envelope:**
  - *Tier 1:* Table `18-10-0004-01`, Vectors `v41692889` and `v41692888`, Reference Period `2025-08/2026-08`
  - *Tier 2:* Coordinates `16.79...` and `16.2...`, Unit `2002=100`
- **Trap Defense:** Reported the negative sign on shelter inflation correctly; avoided hallucinating positive growth from habitual assumptions.
- **Grade:** **PASS** (Exact match)

#### GT-13: Bank of Canada Policy Rate Changes & Levels in 2025
- **Question:** How many times did the Bank of Canada change its policy interest rate in 2025, and where did the rate start and end the year?
- **MCP Tool Call:** `query_valet_policy_rate(start_date="2025-01-01", end_date="2025-12-31")`
- **Retrieved Values:**
  - Number of Rate Changes: **4 changes**
  - Starting Rate: **3.25%**
  - Ending Rate: **2.25%**
  - Step Changes (Valet Effective Dates):
    1. **2025-01-30:** 3.25% → 3.00% (-25 bps)
    2. **2025-03-13:** 3.00% → 2.75% (-25 bps)
    3. **2025-09-18:** 2.75% → 2.50% (-25 bps)
    4. **2025-10-30:** 2.50% → 2.25% (-25 bps)
- **Citation Envelope:**
  - *Tier 1:* Table `Valet`, Series `V39079`, Reference Period `2025-01-01/2025-12-31`, Publisher `Bank of Canada`
  - *Tier 2:* Canonical URL `https://www.bankofcanada.ca/valet/observations/V39079`, License `https://www.bankofcanada.ca/terms/`
- **Trap Defense:** Did not count scheduled hold announcements as changes; correctly reported Valet effective dates (1 business day after announcement).
- **Grade:** **PASS** (Exact match)

---

### Category 5: Unanswerable & Boundary Defenses

#### GT-14: Toronto Mortgage Interest Cost Inflation Refusal
- **Question:** What was mortgage interest cost inflation in Toronto in 2025?
- **Behavior:** Declined Toronto figure; offered National figure instead.
- **Retrieved Findings & Defense:**
  - Declared that Statistics Canada does not publish a city-level mortgage interest cost index for Toronto (Toronto CPI is restricted to 6 broad aggregates).
  - Provided the Canada-wide Mortgage Interest Cost Index from Table `18-10-0005-01` (Vector `v41693354`): 2024 = 173.2, 2025 = 182.4, an inflation rate of **+5.3%**.
- **Citation Envelope:**
  - *Tier 1:* Table `18-10-0005-01`, Vector `v41693354`, Reference Period `2024/2025`
  - *Tier 2:* Coordinate `2.85.0.0.0.0.0.0.0.0`, Publisher `Statistics Canada`
- **Trap Defense:** Zero hallucination of fictitious Toronto mortgage figures.
- **Grade:** **PASS** (Boundary defended)

#### GT-15: 1985 Historical Two-Bedroom Rent in Toronto CMA Refusal
- **Question:** What was the average two-bedroom rent in the Toronto CMA in 1985?
- **Behavior:** Declined: Data prior to 1992 is unavailable in the official CMHC series.
- **Retrieved Findings & Defense:**
  - Queried Table `34-10-0133-01` Vector `v3823103` back to 1980.
  - Confirmed 1991 is null (`status_code: 1`), and earliest available valid observation is 1992 ($755.00).
  - Declined to provide an estimate for 1985, preventing historical back-cast hallucinations.
- **Citation Envelope:**
  - *Tier 1:* Table `34-10-0133-01`, Vector `v3823103`, Earliest Available Period `1992`
  - *Tier 2:* Coordinate `125.3.3.0.0.0.0.0.0.0`
- **Trap Defense:** Successfully resisted answering plausible historical prices; asserted data availability boundary.
- **Grade:** **PASS** (Boundary defended)

---

## 🏁 Final Evaluation Takeaways

1. **Native MCP Integration:** Antigravity communicates directly with `candata-mcp` across all 8 tools via standard JSON-RPC.
2. **Deterministic Calculations:** Slicing, summation, and calculations executed via the DuckDB engine eliminate LLM mental arithmetic errors (such as calculating the exact 12-month housing starts sum of 26,087).
3. **Robust Boundary Defenses:** The agent scored 100% on the unanswerable and vintage mismatch questions, avoiding the common pitfalls of hallucinating historical rents or city-specific subindices.
4. **Token-Budgeted Payload Efficiency:** All responses were delivered under the 3072-byte ceiling while preserving two-tier citations and provenance lineage.
