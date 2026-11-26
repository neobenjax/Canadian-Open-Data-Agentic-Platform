# CAN-55 case study: live run results, 2026-11-25 (draft)

**Status: draft.** Owner: Yassir. This file records one manual run and one agent run on
the same benchmark questions, on one day. Both are small. Read the limits section before
quoting any number.

## 1. What was run

**Part A, manual research (3 questions).** One participant, a project team member,
answered GT-02, GT-06 and GT-10 from the official Statistics Canada website, with a
stopwatch page that logs start and stop times to the millisecond. Rules: official websites
and a calculator only, no AI tools, no help. The participant chose the stop point. The
participant did not see expected values until all three were finished.

**Part B, the agent (all 15 questions).** The live agent in the Streamlit page, on `main`
at commit c493990, with the real planner and a personal API key. Each question was asked in
a new conversation. An AI assistant typed the questions. Times are the node durations the
page shows (Supervisor, which includes planning, plus Data Fetcher, Data Analyst and
Citation Verifier). Values and citations were read from the agent's saved thread state.

**Grading.** Against `collaboration/benchmarks/gta_ground_truth_v1.json`, using each
question's tolerance. The ground truth was read after the answers were recorded. This is
not the scripted harness (`run_agent_evals.py run`), so there are no Tier 1 or Tier 2
scores. Series were compared with the ground-truth citations by hand.

## 2. Part A: manual research

| Question | Time | What was entered | Expected (official) | Result |
|---|---|---|---|---|
| GT-02 | 32.7 s | Gave up, no figure | 3.0% (2025), 1.4% (2023), +1.6 points | Not answered |
| GT-06, run 1 | 76.7 s | Stopped as "cited figure", nothing entered | 113.1 to 109.3, -3.4% | Not answered |
| GT-06, run 2 | 97.4 s | Cited table `16-001-M2025003`, no figure | same | Not answered (unrelated paper) |
| GT-10 | 3 min 52 s | Stopped as "cited figure", nothing entered | 3.1% vs 1.8%, "faster" | Not answered |

**Reading.** Nobody found an answer, so there is no manual time to a correct answer. The
times are the times at which the participant stopped, not the time needed. They cannot
support "4 hours" or any other figure. The participant noted that site search returned
articles rather than data tables. The participant's trail was not recorded: no steps were
marked, and the browser kept only the last page.

## 3. Part B: the agent

| Q | Time | Values vs ground truth | Cited the ground-truth series? | Page ended with |
|---|---|---|---|---|
| GT-01 | 32.8 s | Correct | Yes | Verified |
| GT-02 | 15.6 s | Match (3.0, 1.4, +1.6) | No: 34-10-0127-01, not 34-10-0130-01 | Verified |
| GT-03 | 34.1 s | Both rents loaded ($1,762, $2,045); gap never computed | Yes | Verified, "no computed result" |
| GT-04 | 29.8 s | Oshawa highest (correct); rates 3.7 / 3.6 vs expected 3.6 / 3.5 | No: 34-10-0127-01 | Verified, "no computed result" |
| GT-05 | 15.5 s | 2025 right (26,087); no 2024, no change | No: v42127955, not v42127475 | Verified with a warning: "comparison prior period is missing" |
| GT-06 | 13.5 s | Correct (-3.36% vs -3.4%) | Yes | Verified |
| GT-07 | 27.8 s | Match (28.68% vs 28.7%) | Rent yes; income series differs | Verified |
| GT-08 | 41.4 s | Correct (26.17%, 2.10%) | Yes | **Step failed**, not verified |
| GT-09 | 31.5 s | No answer | None | "no valid plan within 12 turns" |
| GT-10 | 25.9 s | Correct (3.09%, 1.82%) | Yes | **Step failed**, not verified |
| GT-11 | 36.6 s | Correct (2.14%, 3.02%) | Yes | **Step failed**, not verified |
| GT-12 | 21.9 s | Correct (-0.47%, +2.14%) | Yes | **Step failed**, not verified |
| GT-13 | 11.3 s | Correct (4 changes, 3.25 to 2.25) | Yes | Verified |
| GT-14 | 23.4 s | Pass: declined Toronto | n/a | Declined |
| GT-15 | 11.1 s | Pass: no number for 1985 | n/a | Declined |

**Counts.** Values within tolerance: 9 (GT-01, 02, 06, 07, 08, 10, 11, 12, 13). Partial: 3
(GT-03, 04, 05). Failed: 1 (GT-09). Refusals passed: 2 (GT-14, 15). The page ended verified
on 8 questions, with a failed step on 4, with a planning error on 1 and declined on 2.

**Time.** Median 25.9 s, range 11.1 to 41.4 s, across all 15 questions including the
failures and declines.

## 4. The three questions both runs attempted

| Question | Manual (one participant) | Agent |
|---|---|---|
| GT-02 | Gave up at 32.7 s | 15.6 s, values match, different table |
| GT-06 | No answer at 76.7 s or 97.4 s | 13.5 s, correct |
| GT-10 | No answer at 3 min 52 s | 25.9 s, values correct, step failed |

## 5. Findings

1. **Four correct answers ended in a failed step (#112, BEN-78).** For GT-08, GT-10, GT-11
   and GT-12 the plan added a `percentage_point_spread` step that reads the raw series, not
   the growth rates just computed. The rate check from #107 rejects it, and the citations show
   "not checked". GT-12 was verified in the 2026-11-04 harness and the 2026-11-09 pilot.
2. **#106 flags the missing prior year but does not fix it.** GT-05 now shows a warning, but
   the planner still returns only 2025.
3. **GT-09 still fails** with a raw error after 12 turns (#79).
4. **Three questions cite a different valid table from the ground truth.** GT-02 and GT-04 use
   34-10-0127-01 (apartments of six units and over); the ground truth uses 34-10-0130-01 (row
   and apartment structures of three units and over). GT-07's income series differs.
5. **GT-03 and GT-04 never state an answer.** The agent loaded the right series, but no step
   computed the comparison, and the page says "no computed result".
6. **Both refusals were correct.**

## 6. What this does and does not show

- **One run per question** with a planner that varies. A rerun may differ.
- **One manual participant** who knows the project. This is not a sample.
- **An AI assistant typed the agent's questions.** The questions were fixed and copied from
  the ground-truth file.
- **Times are page node durations,** not wall-clock from the user's view.
- **The AI's own attempt at the manual task was blocked.** Statistics Canada's data site
  returned a bot check (HTTP 403) to the AI's browser. That attempt is not counted. The agent
  reaches the data through the official API.
- **Edits on the participant's behalf** were limited to difficulty notes the participant
  approved. The AI's own invalid attempt was first saved under the participant's label; it is
  listed separately as excluded in the raw file and counted nowhere.
- **No cost measure.**
- **Not a replacement for the scripted benchmark.** Re-running the harness would give
  Tier 1 and Tier 2 scores on the same questions.

## 7. Raw data

`CAN_55_live_run_2026-11-25_raw.json`: the participant's four timer entries, and for each
agent question the node times, the values, the cited series and the verifier's verdict.
