# CAN-55 case study: index and status

**Status: in progress (2026-11-25).** CAN-55 is the case study comparing manual research with
agentic synthesis. This folder holds its sections. Each file states its owner and what is still
missing. Nothing here claims more than a committed test, run file or official source supports.

## Sections

| # | Section | Owner | Status |
|---|---------|-------|--------|
| 1 | Framing and what we claim: `CAN_55_framing_and_claims_DRAFT.md` | Yassir | Draft |
| 2 | Benchmark, baseline and agent harness: `CAN_55_evaluation_method_and_results_DRAFT.md` | Samir | Draft in PR #68, not merged |
| 3 | Manual-research timing: `CAN_55_manual_research_protocol.md` | Yassir | Protocol only. No one has been timed yet |
| 4 | User testing and what broke: `CAN_55_user_testing_and_lessons_DRAFT.md` | Yassir | Draft, from the pilot (2026-11-09, 2026-11-10) and the researcher sessions (2026-11-17) |
| 5 | Limits and reproduction | Both | Not started; each file has its own limits section |

## What is still open before this can be published

1. **Time manual research.** No manual research has been timed. Without it, the "4 hours" in the
   task title cannot be claimed. See section 3.
2. **Time the agent end to end on the 15 benchmark questions.** The only end-to-end timings are
   from the 10 questions of the researcher sessions (about 36 to 51 seconds for answered
   questions). A full live run of `collaboration/benchmarks/run_agent_evals.py run` needs an API
   key. Nothing measured supports "12 seconds".
3. **Re-run the CanData-MCP baseline arm on `main`.** The committed arm is from 2026-10-22 and
   scored 3 of 15. Re-running it is tracked in #54 (BEN-58).
4. **Re-test the fixed problems live.** Two fixes merged on 2026-11-24 and 2026-11-25 (#106,
   #107) and have not been re-run in a live session.
5. **Decide where the report is published.** The repository does not say. Options: this folder,
   the docs portal, or the portfolio site.
6. **Align the owner.** `TASKS.md` lists Yassir and Samir; BEN-36 in Linear lists Samir as owner
   and Yassir as collaborator.

## Issues this case study points to

These are the open and recent issues behind the findings. Re-check their status before
publishing.

| Issue | Linear | What it covers | State on 2026-11-25 |
|---|---|---|---|
| #109 | BEN-77 | Significance questions get no answer, though standard errors are verified | Open, Sprint 7 |
| #103 | BEN-75 | A wrong "no table" decline; PR #108 | Open |
| #102 | BEN-76 | A French question answered in English; a wrong axis label | Open |
| #80 | BEN-69 | No plain-language answer line | Open |
| #79 | BEN-68 | GT-09 uses all 12 planning turns and shows a raw error | Open |
| #54 | BEN-58 | Re-run the CanData-MCP baseline arm on `main` | Open |
| #55 | BEN-59 | The harness targets 30 questions but the benchmark has 15 | Open |
| #78, #101 | BEN-67, BEN-74 | Missing prior year; wrong spread | Closed by PRs #106 and #107 |

## Rules for every section

- Cite a source for each number: a committed run file, a report or an official table.
- Say when a result is simulated. The researcher sessions used imaginary, AI-played personas
  and say nothing about how real researchers behave.
- Report results that do not favour the project. On 2026-10-22 the community server answered 11
  of 15 questions and CanData-MCP answered 3.
