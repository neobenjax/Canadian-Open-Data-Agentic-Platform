# Pilot (simulated) results

**Status: Pilot (simulated).** Personas are fictional and were played by an AI assistant driving
the local Streamlit UI in live mode (Claude planner, personal API key). This is a rehearsal for
CAN-35, not the 3 sessions with external researchers.

- **Round 1:** 2026-11-09, about 23:50 to 00:10 ET. Six questions.
- **Round 2:** 2026-11-10, about 00:05 to 00:35 ET. Seven questions.

Each question is one paid planner call or more (GT-09 used all 12 planning turns). A first
attempt on 2026-11-09 failed before planning because the account had no credit; it produced no
answer and is not counted.

## Round 1: results against the earlier demo-mode baselines

| # | Persona | Baseline | Live result | Match |
|---|---|---|---|---|
| 1 | A | GT-12: shelter -0.47%, all-items +2.14% (CAN-32 run) | Same two series (v41692889, v41692888), year over year for Aug 2026, verified. Index values Aug 2026 shelter 190.5, all-items 171.7. Percentages confirmed afterwards by a direct lookup (see G2) | Match |
| 2 | B | GT-05: 26,087 (2025) vs 37,718 (2024), -30.8% | Series v42127955 (the demo plan used v42127475). 2025 = 26,087. 2024 and the change missing (`lag_value` None) | **Mismatch** |
| 3 | C | GT-13: 4 changes, 3.25% to 2.25% | V39079, `rate_change_count` 4, `year_end_rate` 2.25, `max_rate` 3.25 | Match |
| 4 | C | Expected refusal | Declined: a forecast, no official projection; suggests latest rent data instead | As expected |
| 5 | A | None | "Abbotsford" resolved to Abbotsford-Mission CMA (v42128060), about 2,125 starts for 2025, verified. No pause. Chart and table only | Observation |
| 6 | B | None | Vancouver all-items CPI (v41692930); picked the latest month (Sep 2026) itself; year over year 3.03%, verified | Observation |

## How round 1 shaped round 2

Round 1 left gaps. Each round 2 test targets one of them.

| Round 1 gap | Round 2 test |
|---|---|
| Q2 had no 2024 comparison but showed "verified". One run could be a fluke | **G1:** the same question again, and a version naming both years |
| Q1 percentages were not read from the screen | **G2:** direct lookup of the two series (free) |
| The pause-and-ask step never fired (Abbotsford resolved to one CMA) | **G3:** Smiths Falls, the duplicate-name example in the repo's own CAN-33 tests |
| Q1-Q6 were all single questions, so context was untested | **G4:** a follow-up, "What about Ottawa?" |
| Answers were tables and charts with no sentence | **G5:** ask for a quotable sentence |
| Persona B cares about quality flags; none were tested | **G6:** GT-09, the benchmark's `flag` question |
| Only a forecast refusal was tested | **G7:** GT-15 wording, a request before the series starts |
| Q3 start-rate column was cut off | **G8:** direct Valet lookup (free) |

G3, G4 and G7 also line up with open tech-debt tickets BEN-62 and BEN-63, so the results show
whether those tickets matter in live use.

## Round 2: results

| Test | Persona | Question (short) | Result |
|---|---|---|---|
| G1a | B | Original GT-05 wording again | Same series v42127955, same single 2025 point, no 2024 value, page says "verified". **Reproduced** |
| G1b | B | Compare 2024 and 2025 explicitly, give both figures and the change | Same series, same single 2025 point, "verified". **Reproduced** even with the years named |
| G2 | A | Direct lookup, Aug 2026 vs Aug 2025 | Shelter 190.5 vs 191.4 = **-0.47%**; all-items 171.7 vs 168.1 = **+2.14%**. Matches Samir's CAN-32 numbers |
| G3 | A | Housing starts in Smiths Falls, 2025 | Declined: Smiths Falls is not a geography in any housing-starts table. No pause shown, because the planner never reached member resolution |
| G4 | A | "What about Ottawa?" after G3 | Declined: "there is no earlier question to supply that context". The previous turn had been a decline, so the test is partly confounded |
| G5 | C | Latest Toronto two-bedroom rent, as one quotable sentence | Verified series v3823103 for 2025 and a chart (value about 2,045). **No sentence given** |
| G6 | B | GT-09: 2025 two-bedroom rent as a share of 2021 Census median income | `Planning failed: PlanningError: no valid plan within 12 turns`. No answer, raw error shown |
| G7 | C | Average two-bedroom rent in the Toronto CMA in 1985 | Declined at planning time: the table begins in 1987. Clear and useful |
| G8 | C | Direct Valet lookup, V39079 | Rate 2.25% on 2025-12-31, consistent with the UI's year-end 2.25% and max 3.25% |

## Analysis

1. **The agent mostly works end to end.** Of 13 live questions, 8 gave a verified answer or a
   clear refusal. Q1 and Q3 match the benchmark baselines, and the refusals (Q4, G7, G3) read
   clearly. Discovery on series outside the benchmark worked (Q6, G5).
2. **The Q2 gap is real and consistent.** It reproduced in all three runs (Q2, G1a, G1b), and
   naming both years did not help. So it is not phrasing luck. The plan step says it loads "2024
   and 2025", yet the cited period is 2025 only and Samir's fixed plan on a different series
   (v42127475) returned both years. I have not inspected the plan arguments, so the cause
   (the fetch, the series, or the arguments) is unknown. The danger is the green "verified"
   banner on an incomplete answer.
3. **Follow-ups lose context.** G4 supports BEN-62. The confound (the earlier turn was a
   decline) means a follow-up after an answered question should be re-tested.
4. **No sentence-level answer.** Q5 and G5 both returned tables and charts only. G5 asked for a
   quotable sentence and the app ignored it. A non-expert persona would struggle.
5. **The hardest benchmark question fails.** GT-09 needs two sources and a ratio; the planner
   used all 12 turns and failed. That likely cost more than any other question, and the user
   sees only a raw error.
6. **The pause-and-ask step is still untested live.** Neither Abbotsford nor Smiths Falls
   reached it. The probe needs a table that actually contains both Smiths Falls members, such
   as a geography-based Census table.
7. **BEN-63 may be partly addressed in practice.** G7 declined at planning time with the
   earliest year. BEN-63 describes a series-level case (a vector that starts in 1992) that this
   test did not exercise.

## Findings

| # | Severity | Finding | Evidence | Suggested fix |
|---|---|---|---|---|
| 1 | High | A comparison with a missing prior year is shown as verified | Q2, G1a, G1b | Fetch both years for comparisons; flag a comparison with no prior value; investigate the fetch arguments for v42127955 |
| 2 | Medium | Follow-up questions lose the previous question | G4 (supports BEN-62) | Pass the previous plan to the planner; re-test after an answered question |
| 3 | Medium | No plain-language answer line; requests for one are ignored | Q5, G5 | Add a one-sentence answer above the tables |
| 4 | Medium | GT-09 fails after 12 turns with a raw error and likely high cost | G6 | Cap turns lower, explain what could not be done, consider a cheaper model for planning retries |
| 5 | Medium | The pause-and-ask step has not been exercised live | Q5, G3 | Test with a table that contains duplicate names |
| 6 | Low | Raw API and planner errors are shown to the user | Credit error (first attempt), G6 | Show a short plain message |

Setup notes (not product findings): the UI does not read `.env`, so a key saved there leaves the
app in demo mode; the key must be in the process environment. The Statistics Canada maintenance
window (00:00-08:30 ET) did not block the questions run at 00:05-00:35 ET.

## Not covered

- **Why Q2 misses 2024** (plan arguments not inspected).
- **A follow-up after an answered question.**
- **Token cost:** not measured here. Check the Anthropic Console usage page.
- **Real users:** this pilot says nothing about how external researchers phrase questions or
  trust the answers.
- **Sample size:** one phrasing per question, except GT-05 (three).
