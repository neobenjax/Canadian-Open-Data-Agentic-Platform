# CAN-55 case study: user testing and what broke (draft)

**Status: draft (2026-11-25).** Owner: Yassir. Statuses of issues and pull requests are as of
2026-11-25 and must be re-checked before publishing.

**Everything here is simulated.** The personas are imaginary and were played by an AI assistant
(Claude) driving the local Streamlit page in live mode. No real people took part. The results
show how the agent behaved for these questions on these days. They do not show how real
researchers would use it or trust it.

## 1. What was run

| Run | Date | Questions | Source file |
|---|---|---|---|
| Pilot, round 1 | 2026-11-09 | 6 | `collaboration/user-testing/pilot_results.md` |
| Pilot, round 2 | 2026-11-10 | 7 agent questions, plus 2 direct lookups | the same file |
| Researcher sessions | 2026-11-17 | 9, plus 1 follow-up | `collaboration/user-testing/researcher_sessions_results.md` |

The personas are in `personas.md` (pilot) and `personas_researchers.md` (sessions). In the
sessions, every figure was compared with the official Statistics Canada service on the same day.
Each question was run once, except GT-05, which was run three times in the pilot.

## 2. What happened

**Pilot.** The pilot's own count: of 13 live questions, 8 gave a verified answer or a clear
refusal. Two questions matched the earlier benchmark values (GT-12 and GT-13). Six findings came
out of it, listed in section 4.

**Researcher sessions (10 questions).**
- **Answered, 4:**
  - M1 (unemployment rate, October 2026) matched the official data.
  - H1 (life expectancy gap, asked in French) matched the official data.
  - The Ontario and Alberta comparison (M2 follow-up) had matching rates, but never assessed
    whether the change was statistically meaningful.
  - M3 (Alberta youth wages after inflation) had matching inputs and a wrong derived figure.
- **Declined, 6:**
  - Five declines (M2, H3, E1, E2, E3) made accurate statements about the tables.
  - One (H2) said no table publishes provincial age-standardized heart disease mortality. That
    was wrong: tables exist, through 2013 and through 2023 (section 4).

## 3. How long answers took

- **2026-11-04, fixed plans (Samir):** 0.30 to 0.91 seconds on three questions. Planning was
  skipped, so this is not an end-to-end time.
- **2026-11-17, live planner:** the four answered questions took about 36, 48, 49 and 51 seconds
  (median about 49 seconds). The six declines took 3.8 to 90.3 seconds.
- **Pilot:** no per-question times were recorded.

The sessions used different questions from the 15-question benchmark, so they do not replace a
full timed run. Nothing measured supports "12 seconds" for a planned answer.

## 4. What broke, and what has happened since

| Finding | First seen | Issue | Status on 2026-11-25 |
|---|---|---|---|
| A comparison with a missing prior year shown as verified (2025 value only, 26,087) | Pilot Q2, 2026-11-09; reproduced in G1a and G1b, 2026-11-10 | #78 | Closed. PR #106 merged 2026-11-24: the planner prompt loads both periods, the recipe warns when the prior value is missing, and the page flags it. Not re-run live |
| A wrong derived figure under a verified badge: an "inflation-adjusted change" of -150.8 points (21.4 - 172.2). The correct gap is -10.25 points, a real wage change of about -8.5% | Session M3, 2026-11-17 | #101 | Closed. PR #107 merged 2026-11-25: rate validation, a new `real_wage_change` recipe, and an end-to-end test on this case. Not re-run live |
| "Statistically meaningful?" never assessed, though the standard errors (0.3 and 0.6) were fetched and verified, under "4 of 4 verified" | Session M2 follow-up, 2026-11-17 | #109 (first noted as a comment on #78) | Open, filed 2026-11-25 (BEN-77, Sprint 7). PR #106 as described covers the missing prior period only |
| A decline saying no provincial table exists for age-standardized heart disease mortality | Session H2, 2026-11-17 | #103 | Open. PR #108 (open) says three tables exist, including 13-10-0800-01 (2000 to 2023, inactive, 2011 standard population); the table search missed them. I verified 13-10-0800-01 against the official catalogue |
| A question in French answered in English; an axis labelled "percentage points" for years | Session H1, 2026-11-17 | #102 | Open |
| No plain-language answer line; a request for one was ignored | Pilot Q5 and G5, 2026-11-09 and 2026-11-10 | #80 | Open |
| GT-09 used all 12 planning turns and showed a raw error | Pilot G6, 2026-11-10 | #79 | Open |
| Follow-up questions lost the previous question | Pilot G4, 2026-11-10 (partly confounded) | BEN-62 | Fixed: PR #87 merged 2026-11-11. In the sessions, a follow-up ("Then compare Ontario and Alberta") used the earlier question |
| The pause-and-ask step was not exercised live | Pilot Q5 and G3 | #81, #99 | Run by hand on 2026-11-15 and recorded in `docs/CAN_33_HITL_CLARIFICATION.md`; the automated live test passed once on 2026-11-17 |

Note: `researcher_sessions_results.md` and issue #103 first described the older tables as ending
in 2013. A third table runs to 2023. Both records were corrected on 2026-11-25.

## 5. What the pattern teaches

In three separate cases, the page showed a green "verified" banner over an answer that was
incomplete, unassessed or wrong:
1. **Incomplete.** The 2024 value and the change were missing (pilot, three runs).
2. **Unassessed.** The significance question was never answered (session M2 follow-up).
3. **Wrong.** A derived figure subtracted two levels (session M3).

In each case the cited series did match the publisher. The banner checks the series, not whether
the answer is complete or the calculation is right. Two of the three have a merged fix. From
first sighting to merge, the missing prior year took 15 days (2026-11-09 to 2026-11-24) and the
wrong spread took 8 days (2026-11-17 to 2026-11-25).

The declines were the strongest behaviour. Five of the six session declines were accurate and
specific, named the table and said what the tools cannot do. The sixth was wrong about the data,
and is the one still open.

## 6. Limits

- Simulated: an AI played the researchers, so phrasing, patience and reactions are not those of
  real users.
- Small: 13 pilot questions and 10 session questions, mostly one run each.
- The two fixes (#106, #107) have been merged, not re-run in a live session. A live re-run of the
  pilot's Q2 and the session's M3 would show whether they work in use.
- Token cost was not measured.
- Status information changes. Re-check section 4 before publishing.
