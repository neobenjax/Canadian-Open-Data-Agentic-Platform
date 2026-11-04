# CAN-41: DeepEval two-tier harness for the agent

The harness asks the GTA ground-truth questions (CAN-14) through the agent graph, records what
the agent answered and cited, and grades each answer with DeepEval in two tiers:

| Tier | Metric | Kind | Passes when |
|---|---|---|---|
| 1 | Core citations | strict pass/fail | every ground-truth Core Verification Tuple (`table_id`, `vector_id`, `reference_period`) is cited, and nothing outside the ground truth is cited. On `refusal` questions: no figures at all. |
| 2 | Metadata enrichment | scored, threshold 0.7 | share of matching fields per cited tuple: publisher, coordinate, English title, French title, canonical URL |
| 2 | Revision freshness | scored, threshold 1.0 | share of cited tuples whose release or revision date is the same as or later than the ground truth's |

All three metrics are deterministic, with no LLM judge, so **grading needs no API key and no
network**. Only `run`, which asks the agent, needs `ANTHROPIC_API_KEY` and the live APIs.

## Run it

```bash
uv sync --extra evals --extra agent

# Ask the questions (needs ANTHROPIC_API_KEY): writes agent_evals/runs/agent_<UTC>.jsonl
uv run python collaboration/benchmarks/run_agent_evals.py run
uv run python collaboration/benchmarks/run_agent_evals.py run --only GT-05 GT-12

# Grade a run file offline: writes <run>_report.json and <run>_report.md
uv run python collaboration/benchmarks/run_agent_evals.py grade collaboration/benchmarks/agent_evals/runs/agent_demo_live_20261104.jsonl
uv run python collaboration/benchmarks/run_agent_evals.py grade <runs.jsonl> --require-tier1   # exit 1 on any Tier 1 failure
```

`--require-tier1` is the gate for CI (CAN-42): grade a committed or freshly recorded run file,
and fail the job when any question fails Tier 1.

## Layout

| Piece | Where | What it does |
|---|---|---|
| Ground truth | `candata_agent/evals/ground_truth.py` | Loads `gta_ground_truth_v1.json` into typed questions with `CitationEnvelope`s. Fails loud on an unknown `eval_type`, a question with no citations, or an empty table or vector ID. |
| Runs | `candata_agent/evals/run.py` | `run_benchmark()` asks each question on its **own** thread (a reused thread would merge the earlier run's citations) and records an `AgentRun`: answer, citations, whether figures were produced, the agent's own verification, declines, failed steps and crashes. Runs are JSONL. |
| Scoring | `candata_agent/evals/scoring.py` | The two tiers as pure functions. |
| Metrics | `candata_agent/evals/metrics.py` | The scores as DeepEval `BaseMetric`s. Each `LLMTestCase` is named by question ID and carries its run in `metadata["run"]`. |
| Report | `candata_agent/evals/report.py` | Runs DeepEval `evaluate()`, then summarises by tier and `eval_type`. |
| CLI | `collaboration/benchmarks/run_agent_evals.py` | Thin entry point that puts the packages on the path. |

## Matching rules

- **Periods are intervals, not strings (guardrail 8).** `2025` is `[2025-01-01, 2026-01-01)`.
  A cited range covers an expected period when it contains it, so the agent's single
  `2025-08/2026-08` citation covers both of GT-12's `2025-08` and `2026-08` tuples. An unparseable
  period never matches.
- **Business-day slack.** A cited daily range may start or end up to 7 days inside an expected
  daily range, because business-daily series have no observation on weekends and holidays.
- **IDs are normalised.** `18-10-0004-01` equals `1810000401`, and vector case is ignored.
- **Extra citations fail Tier 1.** A citation the ground truth doesn't list is unverifiable, so
  it counts as a possible invented source (for example `v0`).
- **A crashed run fails Tier 1** with the error as its reason; the suite carries on.

## Verification

- `tests/test_evals.py` has 11 tests:
  - Ground-truth loading and period intervals, including the error path.
  - Range coverage, ID normalisation and the business-day slack.
  - Tier 1: exact, range and missing-series cases, an invented `v0`, a crash, and refusals.
  - Tier 2: a missing French title scores 4/5, a stale release scores 0, and Valet (no release
    dates) is not applicable.
  - End to end: the real graph (checkpointer, Analyst, Verifier) answers GT-05, GT-12 and GT-13
    with the fakes. The runs are written to JSONL, read back unchanged, and graded by DeepEval.
  - The CLI writes both reports, and `--require-tier1` exits 1 when one citation is removed.
  - The committed live run still passes both tiers.
- `scripts/verify.py` is clean.
- **Live check (2026-11-04).** GT-05, GT-12 and GT-13 ran against live WDS and Valet with fixed
  plans (the CAN-32 demo plans), because no API key is available yet. All three passed Tier 1,
  with 100% enrichment and freshness. The run is committed as
  `collaboration/benchmarks/agent_evals/runs/agent_demo_live_20261104.jsonl` with its report.

## Known gaps / follow-ups

- **15 questions, not 30.** CAN-41 says 30 ground-truth questions; the committed benchmark has
  15. The harness takes any number, so nothing changes in code if more are added. The decision
  is open in BEN-59 / #55.
- **Full-benchmark run needs a key.** Only the three questions with fixed plans have been run.
  `run` on all 15 needs `ANTHROPIC_API_KEY`.
- **Values are not scored.** The task defines scoring on citations. The answer's numbers aren't
  checked against `expected` here. The CAN-15 grader (`run_baseline.py`) does that for prose
  answers and could be reused.
- **`flag` behaviour is not scored.** GT-09 is graded on its citations like a numeric question.
  Whether the agent surfaced the 2020-income-vs-2025-rent mismatch isn't checked.
- **CI wiring is CAN-42** (Benjamin): run `grade --require-tier1` on a recorded run file.
