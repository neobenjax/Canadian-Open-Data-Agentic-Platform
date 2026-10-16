# GTA Housing Ground-Truth Benchmark v1 (`CAN-14`)

> **Generated file. Do not edit by hand.** Run `python collaboration/benchmarks/build_ground_truth.py` to rebuild from official sources.

- **Questions:** 15
- **Built:** 2026-10-16
- **Sources:** Statistics Canada WDS, Bank of Canada Valet (live API responses, no news coverage)
- **Machine-readable copy:** [`gta_ground_truth_v1.json`](gta_ground_truth_v1.json) (for `CAN-15` baseline and `CAN-41` DeepEval)

## Scoring

Each answer is scored on two layers (see review of PR #8):

1. **Required:** correct value(s) within tolerance, plus `table_id`, `vector_id` and `reference_period` matching the citation below.
2. **Scored separately:** release time, bilingual titles, deep link. Missing these lowers the citation score but does not fail the answer.

Questions marked *Unanswerable* pass only if the agent declines or flags the problem instead of producing a number.

| ID | Category | Question |
| :--- | :--- | :--- |
| [GT-01](#gt-01) | Rental market | What was the average monthly rent for a two-bedroom unit in the Toronto CMA in the October 2025 CMHC Rental Market Survey, and how much did it change from 2024? |
| [GT-02](#gt-02) | Rental market | What was the purpose-built rental vacancy rate in the Toronto CMA in 2025, and how does it compare to 2023? |
| [GT-03](#gt-03) | Rental market | In 2025, how did the average two-bedroom rent in the Oshawa CMA (Durham) compare with the Toronto CMA? |
| [GT-04](#gt-04) | Rental market | Among the Toronto, Oshawa and Hamilton CMAs, which had the highest rental vacancy rate in 2025? |
| [GT-05](#gt-05) | Supply & prices | How many housing units were started in the Toronto CMA in calendar year 2025, and how does that compare with 2024? |
| [GT-06](#gt-06) | Supply & prices | How did new home prices in the Toronto CMA change between December 2024 and December 2025? |
| [GT-07](#gt-07) | Rent vs income | In 2024, what share of the Toronto CMA's median after-tax income would a year of average two-bedroom rent take? |
| [GT-08](#gt-08) | Rent vs income | Between 2019 and 2024, how did average two-bedroom rent growth in the Toronto CMA compare with growth in median after-tax income? |
| [GT-09](#gt-09) | Rent vs income | Using median household income from the 2021 Census, what share of income does the 2025 average two-bedroom rent in Toronto represent? |
| [GT-10](#gt-10) | Inflation & rates | In 2025, did the cost of rented accommodation in Toronto rise faster or slower than overall consumer prices? Give both annual inflation rates. |
| [GT-11](#gt-11) | Inflation & rates | How did shelter inflation in Toronto in 2025 compare with shelter inflation for Canada as a whole? |
| [GT-12](#gt-12) | Inflation & rates | In August 2026, how did shelter prices in Toronto change year over year, compared with overall consumer prices? |
| [GT-13](#gt-13) | Inflation & rates | How many times did the Bank of Canada change its policy interest rate in 2025, and where did the rate start and end the year? |
| [GT-14](#gt-14) | Unanswerable | What was mortgage interest cost inflation in Toronto in 2025? |
| [GT-15](#gt-15) | Unanswerable | What was the average two-bedroom rent in the Toronto CMA in 1985? |

---

## GT-01

**Category:** Rental market

> What was the average monthly rent for a two-bedroom unit in the Toronto CMA in the October 2025 CMHC Rental Market Survey, and how much did it change from 2024?

**Expected:**

- `rent_2025`: 2045.0
- `rent_2024`: 1972.0
- `change_dollars`: 73.0
- `change_pct`: 3.7

**Tolerance:** Exact dollars; percentage ±0.1 pp

**Citation tuple:**

| table_id | vector_id | coordinate | reference_period(s) | release_time |
| :--- | :--- | :--- | :--- | :--- |
| [34-10-0133-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3410013301) | `v3823103` | `125.3.3.0.0.0.0.0.0.0` | 2024-01-01, 2025-01-01 | 2025-12-17T08:30 |

**Traps:**

- Asking rents from listing sites (Rentals.ca / Urbanation, ~$2,600+) are not CMHC survey rents; survey rents include sitting tenants under rent control.
- The survey is taken in October; the table labels it as the annual period '2025'.
- 'Apartment structures of six units and over' is a different series with a different value.

---

## GT-02

**Category:** Rental market

> What was the purpose-built rental vacancy rate in the Toronto CMA in 2025, and how does it compare to 2023?

**Expected:**

- `vacancy_2025_pct`: 3.0
- `vacancy_2024_pct`: 2.5
- `vacancy_2023_pct`: 1.4
- `change_2023_2025_pp`: 1.6

**Tolerance:** Exact to one decimal

**Citation tuple:**

| table_id | vector_id | coordinate | reference_period(s) | release_time |
| :--- | :--- | :--- | :--- | :--- |
| [34-10-0130-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3410013001) | `v1930324` | `24.0.0.0.0.0.0.0.0.0` | 2023-01-01, 2024-01-01, 2025-01-01 | 2025-12-17T08:30 |

**Traps:**

- News coverage of CMHC's Fall 2024 report quotes Toronto at 2.2%-2.3% for 2024; this table (row + apartment, weighted) says 2.5%. The agent must not blend sources.
- The change must be expressed in percentage points, not percent.

---

## GT-03

**Category:** Rental market

> In 2025, how did the average two-bedroom rent in the Oshawa CMA (Durham) compare with the Toronto CMA?

**Expected:**

- `oshawa_2025`: 1762.0
- `toronto_2025`: 2045.0
- `gap_dollars`: 283.0
- `toronto_premium_pct`: 16.1

**Tolerance:** Exact dollars; percentage ±0.1 pp

**Citation tuple:**

| table_id | vector_id | coordinate | reference_period(s) | release_time |
| :--- | :--- | :--- | :--- | :--- |
| [34-10-0133-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3410013301) | `v3823091` | `104.3.3.0.0.0.0.0.0.0` | 2025-01-01 | 2025-12-17T08:30 |
| [34-10-0133-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3410013301) | `v3823103` | `125.3.3.0.0.0.0.0.0.0` | 2025-01-01 | 2025-12-17T08:30 |

**Traps:**

- Durham Region is mostly covered by the Oshawa CMA; Peel, York and Halton fall inside the Toronto CMA and have no separate CMA series in this table.

---

## GT-04

**Category:** Rental market

> Among the Toronto, Oshawa and Hamilton CMAs, which had the highest rental vacancy rate in 2025?

**Expected:**

- `answer`: Oshawa
- `vacancy_2025_pct`: {'toronto': 3.0, 'oshawa': 3.6, 'hamilton': 3.5}

**Tolerance:** Correct CMA; rates exact to one decimal

**Citation tuple:**

| table_id | vector_id | coordinate | reference_period(s) | release_time |
| :--- | :--- | :--- | :--- | :--- |
| [34-10-0130-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3410013001) | `v1930324` | `24.0.0.0.0.0.0.0.0.0` | 2025-01-01 | 2025-12-17T08:30 |
| [34-10-0130-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3410013001) | `v1930312` | `11.0.0.0.0.0.0.0.0.0` | 2025-01-01 | 2025-12-17T08:30 |
| [34-10-0130-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3410013001) | `v1930306` | `6.0.0.0.0.0.0.0.0.0` | 2025-01-01 | 2025-12-17T08:30 |

**Traps:**

- Oshawa and Hamilton differ by only 0.1 pp; an agent that guesses or rounds will get this wrong.

---

## GT-05

**Category:** Supply & prices

> How many housing units were started in the Toronto CMA in calendar year 2025, and how does that compare with 2024?

**Expected:**

- `starts_2025`: 26087
- `starts_2024`: 37718
- `change_pct`: -30.8

**Tolerance:** Exact unit counts; percentage ±0.1 pp

**Computation:** Sum of the 12 monthly (not seasonally adjusted) values for each year.

**Citation tuple:**

| table_id | vector_id | coordinate | reference_period(s) | release_time |
| :--- | :--- | :--- | :--- | :--- |
| [34-10-0154-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3410015401) | `v42127475` | `23.1.1.0.0.0.0.0.0.0` | 2024-01-01 … 2025-12-01 (24 periods) | 2026-01-21T08:30 |

**Traps:**

- The seasonally adjusted annual rate (SAAR) series is a different measure and must not be summed or quoted as an annual total.

---

## GT-06

**Category:** Supply & prices

> How did new home prices in the Toronto CMA change between December 2024 and December 2025?

**Expected:**

- `nhpi_dec_2024`: 113.1
- `nhpi_dec_2025`: 109.3
- `change_pct`: -3.4

**Tolerance:** ±0.1 pp; direction must be correct

**Citation tuple:**

| table_id | vector_id | coordinate | reference_period(s) | release_time |
| :--- | :--- | :--- | :--- | :--- |
| [18-10-0205-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810020501) | `v111955499` | `20.1.0.0.0.0.0.0.0.0` | 2024-12-01, 2025-12-01 | 2026-01-22T08:30 |

**Traps:**

- The New Housing Price Index covers new homes from builders only; resale prices (TRREB / CREA) are a different measure.
- The index is a price index (base December 2016 = 100), not a dollar price.

---

## GT-07

**Category:** Rent vs income

> In 2024, what share of the Toronto CMA's median after-tax income would a year of average two-bedroom rent take?

**Expected:**

- `annual_rent_2024`: 23664.0
- `median_aftertax_income_2024`: 82500.0
- `rent_share_pct`: 28.7

**Tolerance:** ±0.1 pp

**Citation tuple:**

| table_id | vector_id | coordinate | reference_period(s) | release_time |
| :--- | :--- | :--- | :--- | :--- |
| [34-10-0133-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3410013301) | `v3823103` | `125.3.3.0.0.0.0.0.0.0` | 2024-01-01 | 2025-02-04T08:30 |
| [11-10-0190-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1110019001) | `v96415851` | `17.12.1.0.0.0.0.0.0.0` | 2024-01-01 | 2026-04-29T08:30 |

**Traps:**

- Use the same year for rent and income (2024 is the latest income year); pairing 2025 rent with 2024 income must be flagged.
- The income series covers all families and unattached persons, renters and owners alike; renter incomes are lower, so this understates renters' burden.

---

## GT-08

**Category:** Rent vs income

> Between 2019 and 2024, how did average two-bedroom rent growth in the Toronto CMA compare with growth in median after-tax income?

**Expected:**

- `rent_2019`: 1563.0
- `rent_2024`: 1972.0
- `rent_growth_pct`: 26.2
- `income_2019`: 80800.0
- `income_2024`: 82500.0
- `income_growth_pct`: 2.1

**Tolerance:** ±0.1 pp on each rate

**Citation tuple:**

| table_id | vector_id | coordinate | reference_period(s) | release_time |
| :--- | :--- | :--- | :--- | :--- |
| [34-10-0133-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3410013301) | `v3823103` | `125.3.3.0.0.0.0.0.0.0` | 2019-01-01, 2024-01-01 | 2025-02-04T08:30 |
| [11-10-0190-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1110019001) | `v96415851` | `17.12.1.0.0.0.0.0.0.0` | 2019-01-01, 2024-01-01 | 2026-04-29T08:30 |

**Traps:**

- Both series are in current (nominal) dollars; the agent should not mix nominal and inflation-adjusted figures.

---

## GT-09

**Category:** Rent vs income

> Using median household income from the 2021 Census, what share of income does the 2025 average two-bedroom rent in Toronto represent?

**Expected:**

- `behaviour`: Flag the vintage mismatch before (or instead of) computing.
- `must_mention`:
  - 2021 Census income refers to calendar year 2020, five years before the 2025 rent figure.
  - A same-year comparison is available: 2024 Canadian Income Survey (see GT-07).

**Tolerance:** Pass only if the mismatch is stated; a bare percentage fails

**Citation tuple:**

| table_id | vector_id | coordinate | reference_period(s) | release_time |
| :--- | :--- | :--- | :--- | :--- |
| [11-10-0190-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1110019001) | `v96415851` | `17.12.1.0.0.0.0.0.0.0` | 2024-01-01 | 2026-04-29T08:30 |
| [34-10-0133-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3410013301) | `v3823103` | `125.3.3.0.0.0.0.0.0.0` | 2025-01-01 | 2025-12-17T08:30 |

**Traps:**

- Census 2021 median household after-tax income for Toronto ($85,000, income year 2020) produces a plausible-looking ~28.9% that silently mixes 2020 income with 2025 rent.

---

## GT-10

**Category:** Inflation & rates

> In 2025, did the cost of rented accommodation in Toronto rise faster or slower than overall consumer prices? Give both annual inflation rates.

**Expected:**

- `rented_accommodation_pct`: 3.1
- `all_items_pct`: 1.8
- `answer`: Faster

**Tolerance:** ±0.1 pp on each rate; faster/slower must be correct

**Citation tuple:**

| table_id | vector_id | coordinate | reference_period(s) | release_time |
| :--- | :--- | :--- | :--- | :--- |
| [18-10-0005-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810000501) | `v41695188` | `16.80.0.0.0.0.0.0.0.0` | 2024-01-01, 2025-01-01 | 2026-01-19T08:30 |
| [18-10-0005-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810000501) | `v41695186` | `16.2.0.0.0.0.0.0.0.0` | 2024-01-01, 2025-01-01 | 2026-01-19T08:30 |

**Traps:**

- StatCan publishes no city-level 'Rent' index for Toronto, only 'Rented accommodation'.
- The national CPI rent figure is frequently mis-attributed to Toronto.
- December-to-December comparisons differ from annual averages.

---

## GT-11

**Category:** Inflation & rates

> How did shelter inflation in Toronto in 2025 compare with shelter inflation for Canada as a whole?

**Expected:**

- `toronto_shelter_pct`: 2.1
- `canada_shelter_pct`: 3.0
- `answer`: Toronto was lower than Canada

**Tolerance:** ±0.1 pp on each rate; comparison must be correct

**Citation tuple:**

| table_id | vector_id | coordinate | reference_period(s) | release_time |
| :--- | :--- | :--- | :--- | :--- |
| [18-10-0005-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810000501) | `v41695187` | `16.79.0.0.0.0.0.0.0.0` | 2024-01-01, 2025-01-01 | 2026-01-19T08:30 |
| [18-10-0005-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810000501) | `v41693348` | `2.79.0.0.0.0.0.0.0.0` | 2024-01-01, 2025-01-01 | 2026-01-19T08:30 |

**Traps:**

- The common assumption that Toronto shelter costs always rise fastest is wrong for 2025.

---

## GT-12

**Category:** Inflation & rates

> In August 2026, how did shelter prices in Toronto change year over year, compared with overall consumer prices?

**Expected:**

- `shelter_yoy_pct`: -0.5
- `all_items_yoy_pct`: 2.1
- `answer`: Shelter prices fell while overall prices rose

**Tolerance:** ±0.1 pp on each rate; the sign of shelter must be correct

**Citation tuple:**

| table_id | vector_id | coordinate | reference_period(s) | release_time |
| :--- | :--- | :--- | :--- | :--- |
| [18-10-0004-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810000401) | `v41692889` | `16.79.0.0.0.0.0.0.0.0` | 2025-08-01, 2026-08-01 | 2026-09-14T08:30 |
| [18-10-0004-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810000401) | `v41692888` | `16.2.0.0.0.0.0.0.0.0` | 2025-08-01, 2026-08-01 | 2026-09-14T08:30 |

**Traps:**

- A model answering from habit will say shelter rose; the published figure is a decline.

---

## GT-13

**Category:** Inflation & rates

> How many times did the Bank of Canada change its policy interest rate in 2025, and where did the rate start and end the year?

**Expected:**

- `number_of_changes`: 4
- `rate_start_2025_pct`: 3.25
- `rate_end_2025_pct`: 2.25
- `changes`:
  - effective_date: 2025-01-30, from: 3.25, to: 3.0
  - effective_date: 2025-03-13, from: 3.0, to: 2.75
  - effective_date: 2025-09-18, from: 2.75, to: 2.5
  - effective_date: 2025-10-30, from: 2.5, to: 2.25

**Tolerance:** Exact count and rates

**Citation tuple:**

| table_id | vector_id | coordinate | reference_period(s) | release_time |
| :--- | :--- | :--- | :--- | :--- |
| [Valet API](https://www.bankofcanada.ca/valet/observations/V39079) | `V39079` | `None` | 2025-01-01, 2025-12-31 | n/a |

**Traps:**

- Valet dates are effective dates, one business day after each announcement (e.g. announced 29 January, effective 30 January).
- Holds (no change) at scheduled announcements must not be counted as changes.

---

## GT-14

**Category:** Unanswerable

> What was mortgage interest cost inflation in Toronto in 2025?

**Expected:**

- `behaviour`: State that StatCan does not publish a Toronto mortgage interest cost index; offer the national figure instead.
- `canada_mortgage_interest_cost_pct`: 5.3

**Tolerance:** Pass only if the Toronto figure is declined; national figure ±0.1 pp

**Citation tuple:**

| table_id | vector_id | coordinate | reference_period(s) | release_time |
| :--- | :--- | :--- | :--- | :--- |
| [18-10-0005-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810000501) | `v41693354` | `2.85.0.0.0.0.0.0.0.0` | 2024-01-01, 2025-01-01 | 2026-01-19T08:30 |

**Traps:**

- Toronto CPI is published for only 6 aggregates (All-items, Shelter, Rented and Owned accommodation, Water/fuel/electricity, All-items 1992=100). Any Toronto mortgage figure is fabricated.

---

## GT-15

**Category:** Unanswerable

> What was the average two-bedroom rent in the Toronto CMA in 1985?

**Expected:**

- `behaviour`: Decline: the official CMHC series for Toronto does not cover 1985.
- `earliest_available_period`: 1992-01-01

**Tolerance:** Pass only if no number is given for 1985

**Citation tuple:**

| table_id | vector_id | coordinate | reference_period(s) | release_time |
| :--- | :--- | :--- | :--- | :--- |
| [34-10-0133-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3410013301) | `v3823103` | `125.3.3.0.0.0.0.0.0.0` | 1992-01-01 | 2001-10-31T08:30 |

**Traps:**

- Plausible-sounding historical rents are a classic hallucination; the series starts in 1992.

