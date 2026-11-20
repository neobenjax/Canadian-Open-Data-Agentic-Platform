# CAN-55 case study: evaluation method and results (Samir's section, draft)

> **Status: draft.** This is the evaluation part of the CAN-55 case study. Yassir and Samir
> haven't agreed the split yet; the proposal is that this section covers method and results,
> and the framing and manual-research comparison go elsewhere. Every figure below comes from a
> committed run file or report, listed under [Sources](#sources).
>
> **The headline in the task title, "4 hours vs 12 seconds", is not measured yet.** Neither
> side has been timed:
> - Nobody has timed manual research.
> - The agent's end-to-end time with its live planner can't be measured until there is an
>   API key.
>
> [What the numbers support](#what-the-numbers-support-and-what-they-dont) explains what's
> missing and how to measure it.

## 1. What we measured

Housing and price questions about the Greater Toronto Area have exact answers in Statistics
Canada and Bank of Canada data. We measured how often an AI assistant gets them right, gets them
wrong, or declines, and whether it can show where each figure came from. We measured that in
two stages:

| Stage | What it tests | Task |
|---|---|---|
| **Baseline** | A general assistant (Claude via headless Claude Code) answering with no tools, with a community StatCan MCP server, and with our CanData-MCP server | CAN-15 |
| **Agent harness** | Our agent graph (planner, fetcher, SQL analyst, citation verifier), graded on whether it cites exactly the right official series | CAN-41 |

## 2. The benchmark

There are 15 questions about GTA rents, incomes, housing starts, prices and the policy rate.
They're in `collaboration/benchmarks/gta_ground_truth_v1.json` (CAN-14). For each question we
recorded:
- the expected values, from the official release
- the tolerance
- the official citation: table, vector, reference period and release date
- the traps an assistant is likely to fall into

| Type | Questions | What a right answer does |
|---|---|---|
| `numeric` | 8 (GT-01, 02, 03, 05, 06, 07, 08, 13) | States the official value within tolerance |
| `comparison` | 4 (GT-04, 10, 11, 12) | Gets the values and the direction or ranking right |
| `flag` | 1 (GT-09) | Warns that 2020 incomes and 2025 rents are not comparable |
| `refusal` | 2 (GT-14, 15) | Says the data does not exist, rather than inventing it |

Two of the traps:
- **GT-14** asks for a Toronto mortgage interest cost index, which Statistics Canada doesn't
  publish.
- **GT-15** asks for a rent from a year the survey doesn't cover.

## 3. Baseline (CAN-15)

### Method

- **Three setups ("arms"):**

  | Arm | Data access |
  |---|---|
  | `no_tools` | none |
  | `mcp_statcan` | the community `mcp-statcan` server |
  | `candata_mcp` | our server as it was on 22 October 2026 |

- **What's held constant:** every arm used the same 15 questions, the same system prompt and
  the same agent loop. The model was `claude-sonnet-5-5`. The no-tools arm was also run with
  `claude-haiku-5-5` and `claude-opus-5-5`.
- **Outcomes:** each answer is graded `correct`, `partial`, `abstained` or `hallucinated`
  against the ground truth. This is done by code, with no LLM judge, and hand re-grades are
  recorded in `manual_overrides.json`.
- **False claims:** wrong statements about the data itself, such as saying a series exists
  when it doesn't. They're counted separately, whatever the outcome.
- **Timing:** the wall-clock time per answer, as recorded in each run file.

### Results

| Arm · model | Correct | Partial | Abstained | Hallucinated | False claims | Unverified IDs | Median time | Slowest | Tool calls per answer |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| no tools · Haiku | 2 | 0 | 12 | **1** | 2 | 4 | 5.7 s | 8.4 s | 0 |
| no tools · Sonnet | 3 | 0 | 12 | 0 | 1 | 6 | 8.2 s | 11.2 s | 0 |
| no tools · Opus | 3 | 0 | 12 | 0 | 1 | 8 | 9.6 s | 16.3 s | 0 |
| mcp-statcan · Sonnet | **11** | 3 | 1 | 0 | 1 | 21 | 102.0 s | 249.5 s | 12.5 |
| CanData-MCP (22 Oct) · Sonnet | 3 | 0 | 12 | 0 | **0** | 17 | 18.2 s | 100.5 s | 4.5 |

### Findings

1. **Without data access, assistants mostly decline, but they still get things confidently
   wrong.**
   - All three models declined 12 of 15. Their correct answers were the GT-09 flag and the
     GT-15 refusal, plus, for Opus and Sonnet, the GT-13 policy-rate count from their training
     data.
   - Haiku answered GT-13 with 3 rate changes; there were 4 (3.25% to 2.25%).
   - All three models said a Toronto mortgage interest cost series exists. That's the GT-14
     trap, and accounts for 3 of the 4 no-tools false claims.
   - A wrong statement about what the data contains is harder to catch than a wrong number,
     because there's no number to check.
2. **A data server makes most questions answerable, but it is slow and its citations are loose.**
   - `mcp-statcan` got 11 correct and 3 partial.
   - It took a median of 102 seconds per answer, and up to about 4 minutes.
   - Its answers named 21 table or vector IDs that aren't in the ground truth. They might be
     real alternatives or invented, and they have to be checked by hand.
3. **Our server, as measured on 22 October, was honest but couldn't find the data.**
   - CanData-MCP gave no wrong figures and made no false claims, but declined 12 questions.
     The reason was that it had no way to discover tables and dimension members. The model
     had to guess coordinates, and it declined when the guesses failed.
   - Its answers still named 17 IDs that aren't in the ground truth, so loose citations
     weren't only a problem for the other server.
   - Discovery tools and clearer errors were added later (CAN-17, CAN-26), but the arm hasn't
     been re-run on `main` since (BEN-58), so no newer score is reported here.

## 4. Agent harness (CAN-41)

### Method

Our agent graph doesn't let the model write answers or SQL:
1. A planner chooses official series and a calculation.
2. The fetcher loads the series from the official API.
3. A fixed SQL recipe computes the figure.
4. A citation verifier checks every cited series against the publisher.

The CAN-41 harness grades each run in two tiers, with no LLM judge:

| Tier | Score | Rule |
|---|---|---|
| 1 | Core citations, strict pass/fail | Every ground-truth (table, vector, period) is cited, and nothing else is |
| 2 | Metadata enrichment, 0 to 100% | Publisher, coordinate, English and French titles, and URL match the ground truth |
| 2 | Revision freshness, 0 to 100% | The release date of the data used is the same as or later than the ground truth's |

### Results (4 November 2026, live StatCan and Bank of Canada data)

Without an API key, the planner step was replaced by the fixed plans the UI's demo mode uses.
Fetching, SQL and verification ran for real against the live APIs.

| Question | Tier 1 | Enrichment | Freshness | Verified by the agent | Agent time (fetch, SQL, verify) |
|---|---|--:|--:|---|--:|
| GT-05 Toronto housing starts, 2025 vs 2024 | pass | 100% | 100% | yes | 0.89 s |
| GT-12 Toronto shelter vs all-items CPI, Aug 2026 | pass | 100% | 100% | yes | 0.30 s |
| GT-13 Policy rate changes in 2025 | pass | 100% | not applicable* | yes | 0.91 s |

\* The Bank of Canada publishes no release dates.

The figures were:
- **GT-05:** 37,718 starts in 2024 and 26,087 in 2025.
- **GT-12:** shelter −0.47% and all-items +2.14%.
- **GT-13:** 4 changes.

**Finding:** on the questions it ran, the agent cited exactly the official series, with full
metadata, and verified each one against the publisher in under a second. **Caveat:** three
questions with fixed plans don't measure the agent's real performance, because planning was
skipped.

## What the numbers support, and what they don't

| Claim | Supported? |
|---|---|
| Assistants without data access make confident false claims about what official data contains | **Yes:** 4 false claims, including the GT-14 trap for all three models |
| A general data server answers most questions but takes minutes and leaves unverified IDs | **Yes:** median 102 s, 21 unverified IDs |
| Our agent cites exactly the right official series and verifies them | **Yes, for 3 questions with fixed plans**; not yet for the full benchmark with a live planner |
| "12 seconds" for the agent end to end | **Not measured.** The 0.3–0.9 s above excludes planning. A planned run needs `ANTHROPIC_API_KEY`. |
| "4 hours" of manual research | **Not measured.** No manual research has been timed. |

**Two measurements would support the headline:**

1. **Agent, end to end:**
   - Run `uv run python collaboration/benchmarks/run_agent_evals.py run` with a team API key.
   - Report the median and slowest time per question, and Tier 1 across all 15.
2. **Manual research:**
   - Time two or three people answering a sample of the same questions (for example GT-01,
     GT-05, GT-12) from the Statistics Canada and Bank of Canada websites.
   - Time each from reading the question to having a cited figure.
   - Record the time, the steps taken, and whether the answer matched the ground truth.

Until both are done, the case study should give the measured values above instead of
"4 hours vs 12 seconds".

## Reproduce

```bash
# Baseline: grade the committed runs
python collaboration/benchmarks/run_baseline.py grade

# Agent harness: grade the committed live run offline (no key needed)
uv run python collaboration/benchmarks/run_agent_evals.py grade collaboration/benchmarks/agent_evals/runs/agent_demo_live_20261104.jsonl
```

## Sources

- **Ground truth:** `collaboration/benchmarks/gta_ground_truth_v1.json` (CAN-14).
- **Baseline:**
  - `collaboration/benchmarks/baseline/baseline_results_v1.md` and `.json`
  - the run files in `collaboration/benchmarks/baseline/runs/` (2026-10-22). Times are each
    file's `duration_s`.
- **Agent harness:**
  - `collaboration/benchmarks/agent_evals/runs/agent_demo_live_20261104.jsonl` and its report
    (CAN-41, PR #64, not merged yet). Times are each run's `seconds`.
- **Why CanData-MCP scored 3 of 15:** `collaboration/benchmarks/baseline/README.md`.
