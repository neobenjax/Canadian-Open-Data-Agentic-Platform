# CAN-55 case study: framing and claims (draft)

**Status: draft (2026-11-25).** Owner: Yassir. The sections on evidence are in the other files
of this folder.

## Why this matters

When a figure goes into a status report or a decision, someone may need to go back and check
which period it covers, what it includes and where it came from. We tested whether an AI
assistant can answer questions about Canadian housing and prices with figures that are exact and
traceable.

I remember an incident where incorrect network parameters produced wrong optimization figures.
Planning and operations acted on them, and the network's KPIs were worse after the change was
implemented.

## Who this is for

This report is for people who use official statistics in their work and need to know whether an
AI assistant's figures can be traced and trusted. It is also written for engineers and hiring
managers who want evidence of how the system was tested, including where it failed.

## What we built and tested

CanData-MCP is a public repository with two parts:
- **A server** that gives AI assistants access to Statistics Canada and Bank of Canada data.
- **An agent** that answers a question in four steps: a planner chooses official series and a
  calculation, a fetcher loads them from the official API, a fixed SQL recipe computes the
  figure, and a citation verifier checks every cited series against the publisher.

We measured it in three ways. Each has its own section:
1. A benchmark of 15 questions about the Greater Toronto Area, with answers from the official
   releases (Samir, `CAN_55_evaluation_method_and_results_DRAFT.md`).
2. A comparison with a general assistant with no tools and with a community data server
   (the same file).
3. Live use of the agent with imaginary researchers, in a pilot and in researcher sessions
   (`CAN_55_user_testing_and_lessons_DRAFT.md`).

## What this report claims, and what it does not

This table is the ceiling for what any section may say.

| Claim | Supported? | Source |
|---|---|---|
| Assistants without data access make confident false claims about what official data contains | Yes: 4 false claims, including the GT-14 trap for all three models (2026-10-22) | Baseline, in PR #68 |
| A general data server answers most questions but is slow and leaves unverified IDs | Yes: 11 of 15 correct and 3 partial, median 102 s, 21 unverified IDs (2026-10-22) | Baseline, in PR #68 |
| CanData-MCP on 2026-10-22 was honest but answered few questions | Yes: 3 of 15 correct, 0 false claims, 12 declined | Baseline, in PR #68 |
| The agent cites exactly the right official series on questions run with fixed plans | Yes, for 3 questions on 2026-11-04. Planning was skipped in that run | Harness, in PR #68 |
| The agent answers correctly and completely | **No.** In testing, a green "verified" banner appeared over an incomplete answer (3 runs on 2026-11-09 and 2026-11-10), an unassessed question and a wrong derived figure (2026-11-17) | User-testing file |
| "12 seconds" for the agent end to end | **No.** Answered questions took about 36 to 51 seconds on 2026-11-17 | User-testing file |
| "4 hours" of manual research | **Not measured.** No one has been timed | Manual-research protocol |
| How real researchers use or trust the agent | **Not tested.** The sessions were AI-played | User-testing file |

## One rule for the whole report

The headline in the task title, "4 hours vs 12 seconds", is not a result. Until both sides are
measured, the report gives the measured values and says what is missing.
