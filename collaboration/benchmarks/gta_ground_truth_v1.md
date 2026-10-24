# GTA Housing Ground-Truth Benchmark v1 (`CAN-14`)

> **Generated file. Do not edit by hand.** Run `python collaboration/benchmarks/build_ground_truth.py` to rebuild from official sources.

- **Questions:** 15
- **Built:** 2026-10-22
- **Sources:** Statistics Canada WDS, Bank of Canada Valet (live API responses, no news coverage)
- **Machine-readable copy:** [`gta_ground_truth_v1.json`](gta_ground_truth_v1.json) (for `CAN-15` baseline and `CAN-41` DeepEval)

## Target Systems

The benchmark is model-agnostic. It measures the industry baseline problem (frontier LLMs answering Canadian data questions), not one vendor. Typical runs compare:

1. Frontier LLMs **without tools**, from any vendor
2. The same models with an existing open-source StatCan MCP server
3. The same models with CanData-MCP

Every run must record the **exact model ID and run date**, since model versions change faster than this benchmark.

## Scoring

Citations follow the two-tier **Citation Envelope** from PR #8 ([`docs/CORE_DOCS_CITATION_STANDARDS_ACTIVITIES.md`](../../docs/CORE_DOCS_CITATION_STANDARDS_ACTIVITIES.md)):

1. **Tier 1, Core Verification Tuple (strict pass/fail):** `table_id`, `vector_id`, `reference_period`, plus the value(s) within tolerance.
2. **Tier 2, Metadata Enrichment (weighted):** `coordinate`, `release_or_revision_date`, `bilingual_title`, `canonical_url`. Missing fields lower the score but never fail the answer.

Each question has an `eval_type`:

| eval_type | Passes when |
| :--- | :--- |
| `numeric` | Values match within tolerance |
| `comparison` | The categorical answer (which / faster / lower) is right and supporting values match |
| `refusal` | The agent declines to give the requested number (a fabricated number fails) |
| `flag` | The agent states the problem (e.g. mismatched data years) before or instead of answering |

## CI Policy

- **Pull requests:** run only the offline tests in `tests/test_ground_truth_benchmark.py` against this committed JSON. No network calls, so API outages can't block a PR.
- **Scheduled or manual:** run `build_ground_truth.py --check` to detect official revisions. It compares each question's expected answer, every citation's core tuple, and every `release_or_revision_date`. If it reports drift, rebuild and review the diff in a normal PR.

## Source Notes

- **Statistics Canada:** every citation carries the WDS `releaseTime` of its reference period as `release_or_revision_date`, and the table titles from `getCubeMetadata` (English and French).
- **Bank of Canada (Valet):** Valet publishes no release or revision time, so `release_or_revision_date` is `null` and Tier 2 is always partial for BoC series. Valet also has no French labels (`?lang=fr` returns HTTP 400); the French title is the Bank's own term from its [French policy-rate page](https://www.banqueducanada.ca/grandes-fonctions/politique-monetaire/taux-directeur/). `table_id` is `Valet` and `vector_id` is the series name.
- **External figures:** a few traps mention numbers from outside the official tables (news, listing sites, the Census). They are listed under each question's *External figures* with their source. `--check` cannot verify them.

## Questions

| ID | eval_type | Category | Question |
| :--- | :--- | :--- | :--- |
| [GT-01](#gt-01) | `numeric` | Rental market | What was the average monthly rent for a two-bedroom unit in the Toronto CMA in the October 2025 CMHC Rental Market Survey, and how much did it change from 2024? |
| [GT-02](#gt-02) | `numeric` | Rental market | What was the purpose-built rental vacancy rate in the Toronto CMA in 2025, and how does it compare to 2023? |
| [GT-03](#gt-03) | `numeric` | Rental market | In 2025, how did the average two-bedroom rent in the Oshawa CMA (Durham) compare with the Toronto CMA? |
| [GT-04](#gt-04) | `comparison` | Rental market | Among the Toronto, Oshawa and Hamilton CMAs, which had the highest rental vacancy rate in 2025? |
| [GT-05](#gt-05) | `numeric` | Supply & prices | How many housing units were started in the Toronto CMA in calendar year 2025, and how does that compare with 2024? |
| [GT-06](#gt-06) | `numeric` | Supply & prices | How did new home prices in the Toronto CMA change between December 2024 and December 2025? |
| [GT-07](#gt-07) | `numeric` | Rent vs income | In 2024, what share of the Toronto CMA's median after-tax income would a year of average two-bedroom rent take? |
| [GT-08](#gt-08) | `numeric` | Rent vs income | Between 2019 and 2024, how did average two-bedroom rent growth in the Toronto CMA compare with growth in median after-tax income? |
| [GT-09](#gt-09) | `flag` | Rent vs income | Using median household income from the 2021 Census, what share of income does the 2025 average two-bedroom rent in Toronto represent? |
| [GT-10](#gt-10) | `comparison` | Inflation & rates | In 2025, did the cost of rented accommodation in Toronto rise faster or slower than overall consumer prices? Give both annual inflation rates. |
| [GT-11](#gt-11) | `comparison` | Inflation & rates | How did shelter inflation in Toronto in 2025 compare with shelter inflation for Canada as a whole? |
| [GT-12](#gt-12) | `comparison` | Inflation & rates | In August 2026, how did shelter prices in Toronto change year over year, compared with overall consumer prices? |
| [GT-13](#gt-13) | `numeric` | Inflation & rates | How many times did the Bank of Canada change its policy interest rate in 2025, and where did the rate start and end the year? |
| [GT-14](#gt-14) | `refusal` | Unanswerable | What was mortgage interest cost inflation in Toronto in 2025? |
| [GT-15](#gt-15) | `refusal` | Unanswerable | What was the average two-bedroom rent in the Toronto CMA in 1985? |

---

## GT-01

**Category:** Rental market · **eval_type:** `numeric`

> What was the average monthly rent for a two-bedroom unit in the Toronto CMA in the October 2025 CMHC Rental Market Survey, and how much did it change from 2024?

**Expected:**

- `rent_2025`: 2045.0
- `rent_2024`: 1972.0
- `change_dollars`: 73.0
- `change_pct`: 3.7

**Tolerance:** Exact dollars; percentage ±0.1 pp

**Citation envelopes:**

| table_id | vector_id | reference_period | coordinate | release_or_revision_date |
| :--- | :--- | :--- | :--- | :--- |
| [34-10-0133-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3410013301) | `v3823103` | `2024` | `125.3.3.0.0.0.0.0.0.0` | 2025-02-04T08:30 |
| [34-10-0133-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3410013301) | `v3823103` | `2025` | `125.3.3.0.0.0.0.0.0.0` | 2025-12-17T08:30 |

**Traps:**

- Asking rents from listing sites (Rentals.ca / Urbanation, ~$2,600) are not CMHC survey rents; survey rents include sitting tenants under rent control.
- The survey is taken in October; the table labels it as the annual period '2025'.
- 'Apartment structures of six units and over' is a different series with a different value.

**External figures (not covered by `--check`):**

- $2,632: Rentals.ca average asking rent, all apartment types, Toronto, December 2024 (listings, not the CMHC survey) ([source](https://www.cp24.com/local/toronto/2025/01/10/the-cost-to-rent-a-toronto-apartment-fell-by-about-7-per-cent-last-year-report/))

---

## GT-02

**Category:** Rental market · **eval_type:** `numeric`

> What was the purpose-built rental vacancy rate in the Toronto CMA in 2025, and how does it compare to 2023?

**Expected:**

- `vacancy_2025_pct`: 3.0
- `vacancy_2024_pct`: 2.5
- `vacancy_2023_pct`: 1.4
- `change_2023_2025_pp`: 1.6

**Tolerance:** Exact to one decimal

**Citation envelopes:**

| table_id | vector_id | reference_period | coordinate | release_or_revision_date |
| :--- | :--- | :--- | :--- | :--- |
| [34-10-0130-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3410013001) | `v1930324` | `2023` | `24.0.0.0.0.0.0.0.0.0` | 2024-06-06T08:30 |
| [34-10-0130-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3410013001) | `v1930324` | `2024` | `24.0.0.0.0.0.0.0.0.0` | 2025-02-04T08:30 |
| [34-10-0130-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3410013001) | `v1930324` | `2025` | `24.0.0.0.0.0.0.0.0.0` | 2025-12-17T08:30 |

**Traps:**

- CMHC's Fall 2024 report gives a national purpose-built average of 2.2% for 2024, and news coverage sometimes places it next to Toronto; this table (Toronto, row + apartment, weighted) says 2.5%. The agent must not blend sources.
- The change must be expressed in percentage points, not percent.

**External figures (not covered by `--check`):**

- 2.2%: CMHC national average purpose-built vacancy rate, October 2024 (not Toronto) ([source](https://assets.cmhc-schl.gc.ca/sites/cmhc/professional/housing-markets-data-and-research/market-reports/rental-market-report/fall-2024/rental-market-report-fall-2024-en.pdf))

---

## GT-03

**Category:** Rental market · **eval_type:** `numeric`

> In 2025, how did the average two-bedroom rent in the Oshawa CMA (Durham) compare with the Toronto CMA?

**Expected:**

- `oshawa_2025`: 1762.0
- `toronto_2025`: 2045.0
- `gap_dollars`: 283.0
- `toronto_premium_pct`: 16.1

**Tolerance:** Exact dollars; percentage ±0.1 pp

**Citation envelopes:**

| table_id | vector_id | reference_period | coordinate | release_or_revision_date |
| :--- | :--- | :--- | :--- | :--- |
| [34-10-0133-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3410013301) | `v3823091` | `2025` | `104.3.3.0.0.0.0.0.0.0` | 2025-12-17T08:30 |
| [34-10-0133-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3410013301) | `v3823103` | `2025` | `125.3.3.0.0.0.0.0.0.0` | 2025-12-17T08:30 |

**Traps:**

- Durham Region is mostly covered by the Oshawa CMA; Peel, York and Halton fall inside the Toronto CMA and have no separate CMA series in this table.

---

## GT-04

**Category:** Rental market · **eval_type:** `comparison`

> Among the Toronto, Oshawa and Hamilton CMAs, which had the highest rental vacancy rate in 2025?

**Expected:**

- `answer`: Oshawa
- `vacancy_2025_pct`: {'toronto': 3.0, 'oshawa': 3.6, 'hamilton': 3.5}

**Tolerance:** Correct CMA; rates exact to one decimal

**Citation envelopes:**

| table_id | vector_id | reference_period | coordinate | release_or_revision_date |
| :--- | :--- | :--- | :--- | :--- |
| [34-10-0130-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3410013001) | `v1930324` | `2025` | `24.0.0.0.0.0.0.0.0.0` | 2025-12-17T08:30 |
| [34-10-0130-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3410013001) | `v1930312` | `2025` | `11.0.0.0.0.0.0.0.0.0` | 2025-12-17T08:30 |
| [34-10-0130-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3410013001) | `v1930306` | `2025` | `6.0.0.0.0.0.0.0.0.0` | 2025-12-17T08:30 |

**Traps:**

- Oshawa and Hamilton differ by only 0.1 pp; an agent that guesses or rounds will get this wrong.

---

## GT-05

**Category:** Supply & prices · **eval_type:** `numeric`

> How many housing units were started in the Toronto CMA in calendar year 2025, and how does that compare with 2024?

**Expected:**

- `starts_2025`: 26087
- `starts_2024`: 37718
- `change_pct`: -30.8

**Tolerance:** Exact unit counts; percentage ±0.1 pp

**Computation:** Sum of the 12 monthly (not seasonally adjusted) values for each year.

**Citation envelopes:**

| table_id | vector_id | reference_period | coordinate | release_or_revision_date |
| :--- | :--- | :--- | :--- | :--- |
| [34-10-0154-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3410015401) | `v42127475` | `2024-01/2025-12` | `23.1.1.0.0.0.0.0.0.0` | 2026-01-21T08:30 |

**Traps:**

- The seasonally adjusted annual rate (SAAR) series is a different measure and must not be summed or quoted as an annual total.

---

## GT-06

**Category:** Supply & prices · **eval_type:** `numeric`

> How did new home prices in the Toronto CMA change between December 2024 and December 2025?

**Expected:**

- `nhpi_dec_2024`: 113.1
- `nhpi_dec_2025`: 109.3
- `change_pct`: -3.4

**Tolerance:** ±0.1 pp; direction must be correct

**Citation envelopes:**

| table_id | vector_id | reference_period | coordinate | release_or_revision_date |
| :--- | :--- | :--- | :--- | :--- |
| [18-10-0205-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810020501) | `v111955499` | `2024-12` | `20.1.0.0.0.0.0.0.0.0` | 2025-01-24T08:30 |
| [18-10-0205-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810020501) | `v111955499` | `2025-12` | `20.1.0.0.0.0.0.0.0.0` | 2026-01-22T08:30 |

**Traps:**

- The New Housing Price Index covers new homes from builders only; resale prices (TRREB / CREA) are a different measure.
- The value is an index (Index, 201612=100), not a dollar price.

---

## GT-07

**Category:** Rent vs income · **eval_type:** `numeric`

> In 2024, what share of the Toronto CMA's median after-tax income would a year of average two-bedroom rent take?

**Expected:**

- `annual_rent_2024`: 23664.0
- `median_aftertax_income_2024`: 82500.0
- `rent_share_pct`: 28.7

**Tolerance:** ±0.1 pp

**Citation envelopes:**

| table_id | vector_id | reference_period | coordinate | release_or_revision_date |
| :--- | :--- | :--- | :--- | :--- |
| [34-10-0133-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3410013301) | `v3823103` | `2024` | `125.3.3.0.0.0.0.0.0.0` | 2025-02-04T08:30 |
| [11-10-0190-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1110019001) | `v96415851` | `2024` | `17.12.1.0.0.0.0.0.0.0` | 2026-04-29T08:30 |

**Traps:**

- Use the same year for rent and income (2024 is the latest income year); pairing 2025 rent with 2024 income must be flagged.
- The income series covers all families and unattached persons, renters and owners alike; renter incomes are lower, so this understates renters' burden.

---

## GT-08

**Category:** Rent vs income · **eval_type:** `numeric`

> Between 2019 and 2024, how did average two-bedroom rent growth in the Toronto CMA compare with growth in median after-tax income?

**Expected:**

- `rent_2019`: 1563.0
- `rent_2024`: 1972.0
- `rent_growth_pct`: 26.2
- `income_2019`: 80800.0
- `income_2024`: 82500.0
- `income_growth_pct`: 2.1
- `rent_dollars`: Dollars
- `income_dollars`: 2024 constant dollars

**Tolerance:** ±0.1 pp on each rate

**Citation envelopes:**

| table_id | vector_id | reference_period | coordinate | release_or_revision_date |
| :--- | :--- | :--- | :--- | :--- |
| [34-10-0133-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3410013301) | `v3823103` | `2019` | `125.3.3.0.0.0.0.0.0.0` | 2020-01-17T08:30 |
| [34-10-0133-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3410013301) | `v3823103` | `2024` | `125.3.3.0.0.0.0.0.0.0` | 2025-02-04T08:30 |
| [11-10-0190-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1110019001) | `v96415851` | `2019` | `17.12.1.0.0.0.0.0.0.0` | 2026-04-29T08:30 |
| [11-10-0190-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1110019001) | `v96415851` | `2024` | `17.12.1.0.0.0.0.0.0.0` | 2026-04-29T08:30 |

**Traps:**

- The two series are in different dollars: rent in dollars (current, nominal) and income in 2024 constant dollars (inflation-adjusted). Income's growth is real growth, so nominal income grew faster and the gap is narrower in like-for-like terms. An answer that presents the two rates as directly comparable without saying so should be flagged.

---

## GT-09

**Category:** Rent vs income · **eval_type:** `flag`

> Using median household income from the 2021 Census, what share of income does the 2025 average two-bedroom rent in Toronto represent?

**Expected:**

- `behaviour`: Flag the vintage mismatch before (or instead of) computing.
- `must_mention`:
  - 2021 Census income refers to calendar year 2020, five years before the 2025 rent figure.
  - A same-year comparison is available: 2024 Canadian Income Survey (see GT-07).

**Tolerance:** Pass only if the mismatch is stated; a bare percentage fails

**Citation envelopes:**

| table_id | vector_id | reference_period | coordinate | release_or_revision_date |
| :--- | :--- | :--- | :--- | :--- |
| [11-10-0190-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1110019001) | `v96415851` | `2024` | `17.12.1.0.0.0.0.0.0.0` | 2026-04-29T08:30 |
| [34-10-0133-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3410013301) | `v3823103` | `2025` | `125.3.3.0.0.0.0.0.0.0` | 2025-12-17T08:30 |

**Traps:**

- Census 2021 median household after-tax income for Toronto ($85,000, income year 2020) produces a plausible-looking ~28.9% that silently mixes 2020 income with 2025 rent.

**External figures (not covered by `--check`):**

- $85,000: 2021 Census median household after-tax income, Toronto CMA (income year 2020) ([source](https://www150.statcan.gc.ca/n1/daily-quotidien/220713/mc-d002-eng.htm))

---

## GT-10

**Category:** Inflation & rates · **eval_type:** `comparison`

> In 2025, did the cost of rented accommodation in Toronto rise faster or slower than overall consumer prices? Give both annual inflation rates.

**Expected:**

- `rented_accommodation_pct`: 3.1
- `all_items_pct`: 1.8
- `answer`: Faster

**Tolerance:** ±0.1 pp on each rate; faster/slower must be correct

**Citation envelopes:**

| table_id | vector_id | reference_period | coordinate | release_or_revision_date |
| :--- | :--- | :--- | :--- | :--- |
| [18-10-0005-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810000501) | `v41695188` | `2024` | `16.80.0.0.0.0.0.0.0.0` | 2025-01-21T08:30 |
| [18-10-0005-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810000501) | `v41695188` | `2025` | `16.80.0.0.0.0.0.0.0.0` | 2026-01-19T08:30 |
| [18-10-0005-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810000501) | `v41695186` | `2024` | `16.2.0.0.0.0.0.0.0.0` | 2025-01-21T08:30 |
| [18-10-0005-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810000501) | `v41695186` | `2025` | `16.2.0.0.0.0.0.0.0.0` | 2026-01-19T08:30 |

**Traps:**

- StatCan publishes no city-level 'Rent' index for Toronto, only 'Rented accommodation'.
- The national CPI rent figure is frequently mis-attributed to Toronto.
- December-to-December comparisons differ from annual averages.

---

## GT-11

**Category:** Inflation & rates · **eval_type:** `comparison`

> How did shelter inflation in Toronto in 2025 compare with shelter inflation for Canada as a whole?

**Expected:**

- `toronto_shelter_pct`: 2.1
- `canada_shelter_pct`: 3.0
- `answer`: Toronto was lower than Canada

**Tolerance:** ±0.1 pp on each rate; comparison must be correct

**Citation envelopes:**

| table_id | vector_id | reference_period | coordinate | release_or_revision_date |
| :--- | :--- | :--- | :--- | :--- |
| [18-10-0005-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810000501) | `v41695187` | `2024` | `16.79.0.0.0.0.0.0.0.0` | 2025-01-21T08:30 |
| [18-10-0005-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810000501) | `v41695187` | `2025` | `16.79.0.0.0.0.0.0.0.0` | 2026-01-19T08:30 |
| [18-10-0005-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810000501) | `v41693348` | `2024` | `2.79.0.0.0.0.0.0.0.0` | 2025-01-21T08:30 |
| [18-10-0005-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810000501) | `v41693348` | `2025` | `2.79.0.0.0.0.0.0.0.0` | 2026-01-19T08:30 |

**Traps:**

- The common assumption that Toronto shelter costs always rise fastest is wrong for 2025.

---

## GT-12

**Category:** Inflation & rates · **eval_type:** `comparison`

> In August 2026, how did shelter prices in Toronto change year over year, compared with overall consumer prices?

**Expected:**

- `shelter_yoy_pct`: -0.5
- `all_items_yoy_pct`: 2.1
- `answer`: Shelter prices fell while overall prices rose

**Tolerance:** ±0.1 pp on each rate; the sign of shelter must be correct

**Citation envelopes:**

| table_id | vector_id | reference_period | coordinate | release_or_revision_date |
| :--- | :--- | :--- | :--- | :--- |
| [18-10-0004-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810000401) | `v41692889` | `2025-08` | `16.79.0.0.0.0.0.0.0.0` | 2025-09-16T08:30 |
| [18-10-0004-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810000401) | `v41692889` | `2026-08` | `16.79.0.0.0.0.0.0.0.0` | 2026-09-14T08:30 |
| [18-10-0004-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810000401) | `v41692888` | `2025-08` | `16.2.0.0.0.0.0.0.0.0` | 2025-09-16T08:30 |
| [18-10-0004-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810000401) | `v41692888` | `2026-08` | `16.2.0.0.0.0.0.0.0.0` | 2026-09-14T08:30 |

**Traps:**

- A model answering from habit will say shelter rose; the published figure is a decline.

---

## GT-13

**Category:** Inflation & rates · **eval_type:** `numeric`

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

**Citation envelopes:**

| table_id | vector_id | reference_period | coordinate | release_or_revision_date |
| :--- | :--- | :--- | :--- | :--- |
| [Valet](https://www.bankofcanada.ca/valet/observations/V39079) | `V39079` | `2025-01-01/2025-12-31` | n/a | n/a |

**Traps:**

- Valet dates are effective dates, one business day after each announcement (e.g. announced 29 January, effective 30 January).
- Holds (no change) at scheduled announcements must not be counted as changes.

---

## GT-14

**Category:** Unanswerable · **eval_type:** `refusal`

> What was mortgage interest cost inflation in Toronto in 2025?

**Expected:**

- `behaviour`: State that StatCan does not publish a Toronto mortgage interest cost index; offer the national figure instead.
- `canada_mortgage_interest_cost_pct`: 5.3

**Tolerance:** Pass only if the Toronto figure is declined; national figure ±0.1 pp

**Citation envelopes:**

| table_id | vector_id | reference_period | coordinate | release_or_revision_date |
| :--- | :--- | :--- | :--- | :--- |
| [18-10-0005-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810000501) | `v41693354` | `2024` | `2.85.0.0.0.0.0.0.0.0` | 2025-01-21T08:30 |
| [18-10-0005-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810000501) | `v41693354` | `2025` | `2.85.0.0.0.0.0.0.0.0` | 2026-01-19T08:30 |

**Traps:**

- Toronto CPI is published for only 6 aggregates (All-items, Shelter, Rented and Owned accommodation, Water/fuel/electricity, All-items 1992=100). Any Toronto mortgage figure is fabricated.

---

## GT-15

**Category:** Unanswerable · **eval_type:** `refusal`

> What was the average two-bedroom rent in the Toronto CMA in 1985?

**Expected:**

- `behaviour`: Decline: the official CMHC series for Toronto does not cover 1985.
- `earliest_available_period`: 1992

**Tolerance:** Pass only if no number is given for 1985

**Citation envelopes:**

| table_id | vector_id | reference_period | coordinate | release_or_revision_date |
| :--- | :--- | :--- | :--- | :--- |
| [34-10-0133-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3410013301) | `v3823103` | `1992` | `125.3.3.0.0.0.0.0.0.0` | 2001-10-31T08:30 |

**Traps:**

- Plausible-sounding historical rents are a classic hallucination; the series starts in 1992.

