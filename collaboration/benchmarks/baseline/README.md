# CAN-15 Baseline Benchmark

Before CanData-MCP is compared with anything, we need to know how often an AI is confidently wrong about GTA housing data when it has no tools, and when it has the existing community StatCan server. This folder holds those runs and their grades.

The questions and answers come from the CAN-14 ground truth, [`../gta_ground_truth_v1.json`](../gta_ground_truth_v1.json). Nothing here changes it.

## The three arms

| Arm | Data access | How it is connected |
| :-- | :-- | :-- |
| `no_tools` | None. The model answers from what it learned in training. | No tools, no MCP servers |
| `mcp_statcan` | The community [`mcp-statcan`](https://github.com/Aryan-Jhaveri/mcp-statcan) server (StatCan WDS and SDMX) | Its public hosted endpoint, `https://mcp-statcan.onrender.com/mcp`. Nothing is installed locally. |
| `candata_mcp` | This repo's CanData-MCP server (StatCan WDS, BoC Valet, DuckDB) | `python -m candata_mcp` over stdio |

All three arms use the same model, the same system prompt (in `run_baseline.py`) and the same agent loop: headless Claude Code (`claude -p`), with every built-in tool switched off. Only the data access changes. Each question runs in an empty temporary folder, so the model cannot read the answer key or the repo.

The system prompt asks every arm to cite the table ID, vector ID and reference period. For the no-tools arm that is deliberate: inventing an identifier is exactly the failure we want to measure.

## Running it

You need a logged-in `claude` CLI (`claude auth status`).

```bash
python collaboration/benchmarks/run_baseline.py run --arm no_tools --model claude-sonnet-5-5
python collaboration/benchmarks/run_baseline.py run --arm mcp_statcan --model claude-sonnet-5-5
python collaboration/benchmarks/run_baseline.py run --arm candata_mcp --model claude-sonnet-5-5
python collaboration/benchmarks/run_baseline.py grade
```

- `run` writes `runs/<date>_<arm>_<model>.jsonl`. Each line records:
  - the model IDs the API actually reported, which is the exact ID even when you pass an alias
  - the UTC start time
  - every tool call
  - the full answer
- `--only GT-13 GT-15` runs just those questions, which is useful for a smoke test. The output file gets a `_partial` suffix so it does not overwrite a full run.
- `grade` scores every run file offline and writes `baseline_results_v1.json` and `baseline_results_v1.md`.

Both MCP arms need Statistics Canada's WDS to be up. When it is down, it returns an HTML outage page with HTTP 200. Check it before you run, or the tool arms will be graded on an outage rather than on their design:

```bash
curl -s -X POST -H 'Content-Type: application/json' -d '[{"productId":34100133}]' https://www150.statcan.gc.ca/t1/wds/rest/getCubeMetadata | head -c 80
```

## How answers are graded

Each answer gets one outcome:

| Outcome | Meaning |
| :-- | :-- |
| **correct** | Every expected value is within tolerance, and comparison, refusal and flag questions make the right call |
| **partial** | At least half the expected values, and the right call |
| **abstained** | Declined, or gave no figures |
| **hallucinated** | Any of these:<br>• stated figures that do not match the official data<br>• gave a number for a period with no data (GT-15)<br>• computed across mismatched years without flagging it (GT-09) |

Abstaining is not counted as a hallucination. An agent that says "I can't verify that" is less useful than one that answers correctly, but it is not wrong.

**False claims** are counted separately from outcomes. A false claim is a wrong statement about the official data itself, for example:
- saying StatCan publishes a Toronto mortgage interest cost series (GT-14), when it does not
- giving the wrong start year for a series

An answer can decline the number, and so be graded abstained, or even correct, and still make a false claim. False claims are marked by hand and listed in their own section of the report.

### Tolerances

| Value | Tolerance |
| :-- | :-- |
| Percentages and percentage points | ±0.1 |
| Whole-number values (dollars, unit counts) | ±0.5 |
| Other decimals (index levels, policy rates) | ±0.05 |

Signs are compared as magnitudes, so "fell 30.8%" and "−30.8%" both count. Direction is graded through the comparison patterns.

### Citations

- **Citation coverage** is the share of the ground-truth table IDs and vector IDs that the answer names. `34-10-0133-01`, `3410013301` and `34100133` all count as the same table.
- **Unverified IDs** are StatCan identifiers in the answer that are not in the ground truth. They may be a real alternative table, or an invented one. The report lists them so a person can check.

### Manual review

The automatic grade is a first pass. Read the hallucination log in the report, and record any re-grade in `manual_overrides.json`:

```json
{
  "no_tools/claude-sonnet-5-5/GT-03": {
    "outcome": "partial",
    "reason": "Gave both rents correctly; the 16.1% premium was phrased as 'about 16%'."
  }
}
```

Every field is optional:
- `outcome` and `reason` replace the automatic grade, and are marked with `*` in the report.
- `false_claim` on its own logs a false claim and keeps the automatic grade.

## Why CanData-MCP scored 3 of 15

In the Oct 22 run, CanData-MCP answered 3 questions correctly and declined 12, against 11 correct for `mcp-statcan` on the same model. Its data tools return the right values when given a valid vector or coordinate (for example, `v3823103` returns $2,045). The model could not get that far, for three reasons:

- **No discovery tools.** `query_statcan_coordinate` needs a table ID and a 10-part coordinate, and nothing on the server lists tables or dimension members. The model guessed coordinates, most guesses failed, and it declined.
- **Errors carry no reason.** A failed call returns `Error executing tool` with no detail, so the model cannot correct its next call.
- **Responses carry no member labels.** On GT-03 the model retrieved $2,045 but could not confirm that the series was Toronto.

The declines were honest: no wrong figures and no false claims. `mcp-statcan` exposes table search and metadata tools, which is what let it find the series.

The fixes are tracked in CAN-17 (BEN-45): discovery tools (table search and dimension listing) and actionable error payloads. Member labels on sliced payloads come in CAN-26. Re-run the `candata_mcp` arm once those land.

## Known limits

- Grading is pattern-based, with no LLM judge. It can miss correct answers phrased in unusual ways, which is why the manual overrides exist.
- An answer that lists many numbers can match expected values by chance. The hallucination log and the unverified IDs are there to catch this.
- The no-tools arm is graded against data released after some models' training cutoffs. That is intended: it measures whether the model admits it doesn't know.
- The two MCP arms expose different tool sets, so `candata_mcp` against `mcp_statcan` measures server design (which tools exist) as well as data quality. That is fine for a baseline, but it is not a like-for-like comparison of the data layer.
- One run per arm and model. Run-to-run variance is not measured yet; that belongs in the DeepEval harness (CAN-41).
- Every run in `runs/` uses the same harness: the version that records `tools_available` and runs MCP tools with `ENABLE_TOOL_SEARCH=false`. The part-1 Haiku and Sonnet runs predated that version and were re-run in part 2.
