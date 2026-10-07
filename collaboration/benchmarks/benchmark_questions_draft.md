# GTA Housing Ground-Truth Benchmark — Initial Draft (`CAN-02`)

Three seed questions for the CanData-MCP evaluation suite. They establish the format that `CAN-14` will expand to 15 questions and `CAN-41` (DeepEval harness) will consume.

Every expected answer below was pulled directly from the official Statistics Canada full-table CSV downloads (not from news coverage), on **2026-10-07**.

---

## 📐 Question Format

| Field | Purpose |
| :--- | :--- |
| **Question** | Natural-language prompt sent to the agent, exactly as written. |
| **Expected answer** | Ground-truth value(s) the agent must return. |
| **Tolerance** | Acceptable deviation for numeric grading. |
| **Source** | StatCan table ID + vector ID the agent must cite (checked by the Citation Verifier, `CAN-24`). |
| **Traps** | Known ways an agent can be confidently wrong — used to log hallucinations in `CAN-15`. |

---

## 🏠 Q1 — Average Two-Bedroom Rent (Rent Level)

**Question:**
> What was the average monthly rent for a two-bedroom unit in the Toronto CMA in the most recent CMHC Rental Market Survey, and how much did it change from the previous year?

**Expected answer:**
- **2025:** $2,045 / month
- **2024:** $1,972 / month
- **Change:** +$73 (**+3.7%**)

**Tolerance:** Exact dollar values; percentage ±0.1 pp.

**Source:**
- Table **34-10-0133-01** — *CMHC, average rents for areas with a population of 10,000 and over*
- Vector **v3823103** — Toronto, Ontario · Row and apartment structures of three units and over · Two bedroom units

**Traps:**
- Asking rents from listing sites (Rentals.ca / Urbanation reported ~$2,600+ in 2024) are **not** CMHC survey rents. Survey rents reflect what sitting tenants pay, including long-term rent-controlled units.
- The survey is taken in **October**; "2025" means October 2025, not the calendar-year average.
- Using the "Apartment structures of six units and over" series instead gives $2,056 — a different universe.

---

## 🔑 Q2 — Rental Vacancy Rate (Market Tightness)

**Question:**
> What was the purpose-built rental vacancy rate in the Toronto CMA in 2025, and how does it compare to 2023?

**Expected answer:**
- **2025:** 3.0%
- **2024:** 2.5%
- **2023:** 1.4%
- **Change 2023 → 2025:** +1.6 percentage points (vacancy more than doubled)

**Tolerance:** Exact to one decimal.

**Source:**
- Table **34-10-0130-01** — *CMHC, vacancy rates, row and apartment structures of three units and over, privately initiated in census metropolitan areas, weighted average*
- Vector **v1930324** — Toronto, Ontario

**Traps:**
- News coverage of CMHC's Fall 2024 report quotes Toronto at **2.2%–2.3%** for 2024, which does not match this table's 2.5%. The published figures differ by structure universe (apartment-only vs. row + apartment, weighted). The agent must cite the table it actually used and not blend numbers across sources.
- Answering in "percent change" (e.g. "+114%") instead of percentage points must be flagged as ambiguous.

---

## 📈 Q3 — Rent Inflation vs. General Inflation

**Question:**
> In 2025, did the cost of rented accommodation in Toronto rise faster or slower than overall consumer prices? Give both annual inflation rates.

**Expected answer:**
- **Rented accommodation CPI:** 158.6 (2024) → 163.5 (2025) = **+3.1%**
- **All-items CPI:** 164.7 (2024) → 167.7 (2025) = **+1.8%**
- **Conclusion:** Rent rose **faster** than overall inflation, by about 1.3 pp.
- *(Context: in 2024, Toronto rented-accommodation CPI rose +6.5% vs. 2023.)*

**Tolerance:** ±0.1 pp on each rate; the faster/slower conclusion must be correct.

**Source:**
- Table **18-10-0004-01** — *Consumer Price Index, monthly, not seasonally adjusted* (base 2002 = 100)
- Vector **v41692890** — Toronto, Ontario · Rented accommodation
- Vector **v41692888** — Toronto, Ontario · All-items
- Annual figures = mean of the 12 monthly index values (2024: 12 months; 2025: 12 months).

**Traps:**
- Statistics Canada does not publish a city-level "Rent" sub-index for Toronto; only **Rented accommodation** (which includes tenant insurance and maintenance). An agent quoting a "Toronto rent CPI" is mislabelling the series.
- The national CPI rent figure (+8.2% in 2024) is frequently mis-attributed to Toronto.
- December-to-December comparisons give different numbers than annual averages; the question asks for annual rates.

---

## 🔁 Reproducing the Ground Truth

All three tables can be downloaded as open-data CSVs:

```text
https://www150.statcan.gc.ca/n1/tbl/csv/34100133-eng.zip   # average rents
https://www150.statcan.gc.ca/n1/tbl/csv/34100130-eng.zip   # vacancy rates
https://www150.statcan.gc.ca/n1/tbl/csv/18100004-eng.zip   # CPI monthly
```

Filter on the `VECTOR` column for the IDs listed above. The `CAN-14` follow-up should turn this into a scripted fixture so expected answers are regenerated rather than hand-copied.

---

## 🗺️ Next Steps (handed to `CAN-14`)

- [ ] Add **rent-to-income** questions (Census 2021 median household income by CMA vs. CMHC rents). Watch out for vintage mismatch: Census income is for 2020.
- [ ] Extend beyond the Toronto CMA to the other GTA municipalities (Peel, York, Durham, Halton).
- [ ] Add Bank of Canada policy-rate questions for the mortgage-cost side.
- [ ] Store questions as structured YAML/JSON for the DeepEval harness (`CAN-41`).
