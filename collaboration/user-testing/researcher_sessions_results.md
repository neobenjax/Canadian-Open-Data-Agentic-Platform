# CAN-35 researcher sessions: results (AI-played, imaginary personas)

**Status: simulated.** An AI assistant (Claude) played three imaginary researchers, described in
`personas_researchers.md`, and asked the nine fixed questions in that file. No real people took
part. What follows shows how the agent behaved for these questions on one day. It does not show
how real researchers would use it. CAN-35 was amended to cover these AI-played sessions.

- **Date:** 2026-11-17.
- **Build:** `main` after PR #92 (`682f129`), local Streamlit page in live mode.
- **Planner:** `ClaudePlanner`, default model `claude-opus-5-5` per `planner.py`.
- **Key:** a personal key, loaded from the environment. It is never shown on the page, and the
  page only says "Live mode".
- **One run per question.** Planner behaviour varies; a rerun may differ.
- **Checks:** each figure was compared with the official Statistics Canada service
  (`getDataFromVectorsAndLatestNPeriods`, `getCubeMetadata`, `getAllCubesListLite`) on the same
  day. Where a check was not possible, it says so.
- **Live-marked test (BEN-73 / #99):** `test_live_ottawa_follow_up_pauses_and_resumes_with_the_chosen_member`
  in `tests/test_clarification.py` passed once on the same day (43.7 s).

## Summary

| ID | Persona | Outcome | Time | Checked against official data |
|----|---------|---------|------|-------------------------------|
| M1 | Marcus | Answered, verified | about 49 s | Match |
| M2 | Marcus | Declined (plan limits) | 90 s | Reason accurate |
| M2 follow-up | Marcus | Answered, verified (4 of 4), **half unanswered** | about 51 s | Rates match; significance not assessed |
| M3 | Marcus | Answered, verified (2 of 2), **one derived figure wrong** | about 36 s | Inputs match; spread wrong |
| H1 | Amara | Answered (asked in French, answered in English) | about 48 s | Match |
| H2 | Amara | Declined, **reason partly wrong** | 23 s | Table facts accurate; one table missed |
| H3 | Amara | Declined | 30 s | Accurate |
| E1 | Jordan | Declined (expected scope) | 20 s | StatCan facts accurate |
| E2 | Jordan | Declined | 14 s | Accurate |
| E3 | Jordan | Declined (forecast) | 4 s | Consistent |

## Findings, most important first

1. **"Verified" does not cover the calculation (M3).** The page showed "All cited series
   verified (2 of 2)". The wage and price tables were right: Alberta's youth average hourly wage
   went from $19.44 (2019) to $21.40 (2025), +10.08%, and Alberta's CPI from 143.1 to 172.2,
   +20.34%. The third table, "an approximate inflation-adjusted change", showed a spread of
   -150.8 percentage points. That is 21.4 - 172.2, the difference of the two levels. The gap
   between the two changes is -10.25 points, and the real wage change is about -8.5%
   (computed here from the official values). The wrong figure carries the same green badge.
2. **"Verified" does not mean "complete" (M2 follow-up).** Marcus asked whether the Ontario and
   Alberta changes were statistically meaningful. The page loaded and verified four series,
   including the standard errors of the year-over-year change (Ontario 0.3, Alberta 0.6 in the
   official data). No step compares a change with its standard error, and no sentence says
   whether the change is meaningful. This is the same pattern as #78 (a verified banner over a
   half-complete answer), on a different question.
3. **A decline built on a wrong premise (H2).** The page said no table publishes
   age-standardized heart disease mortality for each province. Table 13-10-0393-01 does, for
   Canada and every province, through 2013 on the 1991 standard population ("Diseases of
   heart"). Its other claims (13-10-0833-01 groups provinces by income quintile; 13-10-0007-01
   ends in 1996) are accurate. I did not test whether the planner's search could surface the
   2013 table.
4. **The agent stays inside Statistics Canada and Bank of Canada data (E1, E3), as intended.**
   The E1 decline correctly said the two Statistics Canada emissions tables do not overlap
   (2009 to 2023 and 1990 to 2008) and pointed to Environment and Climate Change Canada. The
   federal open-data portal lists that department's inventory and projections datasets, but the
   agent package does not use that portal (the connector is in the MCP server package). Declining
   at that boundary is the expected result, not a defect. The portal datasets were not opened.
5. **Honest limits set by the app (M2, E2, H3).** M2: ranking ten provinces needs about twenty
   series, above the app's limit of 12 plan steps and five data slots (`MAX_STEPS` and `DataSlot`
   in `supervisor/registry.py`). Statistics Canada does not set these limits. E2: summing
   generation types and dividing by population is not available to the agent. H3: British
   Columbia overdose deaths are not in a Statistics Canada table (table 13-10-0156-01 covers
   Canada only). All three were declined with accurate statements about the tables. M2 took 90 s
   to say no.
6. **Language and labels (H1).** A French question got an English answer, English labels and
   English series titles, with no note about it. The chart axis says "Spread (percentage
   points)" for values that are years, and the chart title works around it ("values are
   years"). The series covers "Canada, all provinces except Prince Edward Island" and says so
   only in the Sources tab.
7. **No plain-language answer line (M1, M2 follow-up, M3, H1).** Results are tables and charts.
   M1 shows -2.9 (a relative change) while an analyst would quote -0.2 points, which sits in
   the `change_absolute` column. This is already tracked as #80.

**What worked:** M1 and H1 matched the official data exactly. Citations, series IDs and the
publisher were visible in the Sources tab, with no quality flags raised. The follow-up in M2
kept the context of the question before it. Every decline named the table it relied on, said what
it could not do, and invented no number.

## Suggested follow-ups (not filed)

- Compute a spread from the two change values, and sanity-check a percentage-point spread
  (finding 1).
- Use fetched standard errors in a computed check, or say that significance was not assessed
  (finding 2). Tracks with #78.
- Surface 13-10-0393-01 and 13-10-0396-01 in discovery, and answer with the vintage stated when
  the newest data is old (finding 3).
- Reply in the question's language, or say that the reply is in English (finding 6).
- Show a unit label that matches the values (finding 6).

## Log (template: `feedback_log_template.md`)

Times are the durations the page showed. "Series" means vector IDs.

### M1 - Marcus
- **Question as asked:** What was Canada's unemployment rate in October 2026, seasonally adjusted, and what was it a year earlier?
- **Mode:** live. **Time to verified answer:** about 49 s (Supervisor 47.9 s, Fetcher 0.4 s, Analyst 1.1 s, Verifier 0.0 s).
- **Answer given:** current 6.7, a year earlier 6.9, change -0.2 (-2.8986%); banner "All cited series verified (1 of 1)".
- **Baseline and match:** official v2062815: 2026-10 = 6.7 (released 2026-11-06), 2025-10 = 6.9. Match.
- **Series:** v2062815, table 14-10-0287-01, Statistics Canada, seasonally adjusted.
- **Citations, series IDs, flags visible:** yes; quality flags 0.
- **Chart or table readable:** partly. The chart plots only the -2.9% change; the two rates are in a table.
- **Refusal or pause:** none.
- **Confusion or friction:** no answer sentence; "seasonally adjusted" appears only in the series title.
- **Severity:** low-medium. **Suggested fix:** an answer line with both rates and the change in points.

### M2 - Marcus
- **Question as asked:** Which province had the largest rise in its unemployment rate over the past 12 months, and is that change statistically meaningful?
- **Mode:** live. **Outcome:** declined after 90.3 s.
- **Answer given:** table 14-10-0287-01 has each province's rate and the standard error of its year-over-year change, but ranking ten provinces needs about twenty series, above the 12-step and five-slot limits; "name one or two provinces".
- **Baseline and match:** the table has 11 geographies and a "Standard error of year-over-year change" statistic. Accurate.
- **Refusal or pause:** decline (a plan limit, not a data gap).
- **Confusion or friction:** a province ranking is a basic analyst question; 90 s to be told no; no shortlist offered.
- **Severity:** medium. **Suggested fix:** wider comparisons, or offer a shortlist.

### M2 follow-up - Marcus
- **Question as asked:** Then compare Ontario and Alberta: how did each province's unemployment rate change over the past 12 months, and is either change statistically meaningful?
- **Mode:** live. **Time to verified answer:** about 51 s (Supervisor 44.7 s, Fetcher 5.7 s, Analyst 0.0 s, Verifier 0.1 s).
- **Answer given:** Ontario 7.6 to 7.3 (-0.3, -3.9474%), Alberta 7.6 to 7.3 (-0.3, -3.9474%); banner "4 of 4 verified".
- **Baseline and match:** official v2063949 and v2064516 both 7.6 (2025-10) and 7.3 (2026-10). Match; the identical values are real. Standard errors v101887840 (0.3) and v101889100 (0.6) were fetched and verified.
- **Series:** v2063949, v2064516, v101887840, v101889100.
- **Chart or table readable:** partly; a relative change (-3.95%) is shown for a rate.
- **Confusion or friction:** the "statistically meaningful" half is not answered anywhere (finding 2).
- **Severity:** high. **Suggested fix:** compute change versus standard error, or state that it was not assessed.

### M3 - Marcus
- **Question as asked:** How have average hourly wages for workers aged 15 to 24 in Alberta changed since 2019 after adjusting for inflation?
- **Mode:** live. **Time to verified answer:** about 36 s (Supervisor 34.6 s, Fetcher 1.1 s, Analyst 0.1 s, Verifier 0.1 s).
- **Answer given:** wage 19.44 to 21.40 (+10.0823%); CPI 143.1 to 172.2 (+20.3354%); "gap" table with spread -150.8 pp (-15,080 bps); banner "2 of 2 verified".
- **Baseline and match:** official v2293021 (table 14-10-0064-01) and v41694625 (table 18-10-0005-01): inputs match. The spread is wrong (finding 1).
- **Series:** v2293021, v41694625 (right series; annual data).
- **Confusion or friction:** the real wage change (about -8.5%) is never stated; the shown spread is off by about 140 points.
- **Severity:** high. **Suggested fix:** spread from the two change values; a test on this case.

### H1 - Amara
- **Question as asked:** Quelle est l'espérance de vie à la naissance des femmes et des hommes au Canada, et comment l'écart a-t-il évolué depuis 2010?
- **Mode:** live. **Time to verified answer:** about 48 s (Supervisor 26.1 s, Fetcher 20.6 s, Analyst 0.1 s, Verifier 0.9 s).
- **Answer given:** a bar chart and table of the female-minus-male gap by year: 4.33 (2010), 4.80 (2021), 4.26 (2024). 2024: women 84.29, men 80.03. Banner "2 of 2 verified", in English.
- **Baseline and match:** official v1300144496 (women) and v1300144487 (men), table 13-10-0837-01: match.
- **Citations, series IDs, flags visible:** yes; quality flags 0. The title says "Canada, all provinces except Prince Edward Island".
- **Confusion or friction:** English reply to a French question; axis labelled in percentage points for years (finding 6).
- **Severity:** medium. **Suggested fix:** reply language; unit label.

### H2 - Amara
- **Question as asked:** Which provinces have the highest age-standardized mortality rate from heart disease, and are any of those figures flagged as unreliable?
- **Mode:** live. **Outcome:** declined after 23.0 s ("No available table publishes age-standardized heart disease mortality for each province...").
- **Baseline and match:** 13-10-0833-01 and 13-10-0007-01 described accurately. 13-10-0393-01 (2000 to 2013, all provinces, "Diseases of heart") contradicts the headline claim (finding 3).
- **Severity:** medium-high. **Suggested fix:** surface the older tables and state the vintage.

### H3 - Amara
- **Question as asked:** How many people died of a drug overdose in British Columbia last year?
- **Mode:** live. **Outcome:** declined after 30.4 s, offering a national count instead.
- **Baseline and match:** table 13-10-0156-01 has Canada as its only geography; no catalogue table gives British Columbia overdose deaths. Accurate. The coroner and federal surveillance attribution was not checked.
- **Severity:** none-low. **Suggested fix:** make the offered alternative a one-click follow-up.

### E1 - Jordan
- **Question as asked:** What were Canada's total greenhouse gas emissions in 2022, and how do they compare with 2005?
- **Mode:** live. **Outcome:** declined after 19.8 s.
- **Baseline and match:** tables 38-10-0097-01 (2009 to 2023) and 38-10-0111-01 (1990 to 2008) as stated. The "discontinued method" detail was not checked. The department's inventory is outside the agent's sources, so the decline is the expected result (finding 4).
- **Severity:** none.

### E2 - Jordan
- **Question as asked:** Which province generates the most electricity from renewable sources per person?
- **Mode:** live. **Outcome:** declined after 13.5 s.
- **Baseline and match:** table 25-10-0015-01 has types (hydraulic, wind, solar, tidal, biomass and others) but no renewable total. Accurate.
- **Severity:** medium. **Suggested fix:** derived totals and per-person division as analysis steps.

### E3 - Jordan
- **Question as asked:** What will Canada's emissions be in 2035 if current policies continue?
- **Mode:** live. **Outcome:** declined after 3.8 s as expected (a forecast), naming the department that publishes projections.
- **Baseline and match:** the federal portal lists that department's projections dataset (not opened).
- **Severity:** none.

## Limits of this round

- Simulated: an AI played the researchers, so phrasing, patience and reactions are not those of
  real users.
- One run per question, one day, one build.
- Figures were checked against the public Statistics Canada service. The portal datasets, the
  "discontinued method" remark and the coroner attribution were not opened.
- Screenshots are kept outside the repository (ignored `captures/` folder).
