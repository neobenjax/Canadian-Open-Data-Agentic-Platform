# CAN-22: Supervisor Agent

**Owner:** Samir · **Milestone:** 2 (Sprint 2) · **Linear:** BEN-17 · **Code:** `packages/agent-orchestrator/src/candata_agent/supervisor/`

The Supervisor turns a question into a plan of deterministic tool calls and routes each step to the agent that runs it. Claude decides **which official series to load and which calculation to run**. It never states a figure: the Data Fetcher loads the data, the Data Analyst (CAN-23) does the arithmetic in sandboxed SQL, and the Citation Verifier (CAN-24) checks every source before the run ends.

## The graph

```
START → supervisor ─┬→ data_fetcher ─┐
                    ├→ data_analyst ─┤ (back to supervisor after each step)
                    ├→ citation_verifier → END   (plan complete)
                    └→ END                       (declined, planning failed, or a step failed)
```

- **One plan per user message.** Planning is keyed on the message ID, not its text, so a new message starts a new plan on the same thread, including a retry of a question that failed or a repeat of one that finished. Mid-plan, the Supervisor only routes.
- **Every executor finishes its step.** It marks the step `completed` or `failed` and moves `active_step_id` on. A failed step ends the run, with the reason in the messages and in `result_summary`.
- **Verification is per question.** The verifier checks only the citations this question's fetch steps produced. Its report goes in `AgentState.verification` (new field), which is reset when the next question is planned.
- **Tracing.** Every node is wrapped in `traced_node` (CAN-25), so `traced_run` gives one trace per question. This also covers BEN-50 for the Supervisor and the Citation Verifier.

## Planning: Claude proposes, the registry decides

`ClaudePlanner` (`supervisor/planner.py`) runs a bounded tool loop (12 turns by default) on `claude-opus-5-5`:

| Tool | Kind | What it does |
| :-- | :-- | :-- |
| `search_statcan_tables` | discovery | All-words search over the WDS cube list (CAN-17) |
| `find_members` | discovery | A table's dimensions and the members whose name matches, for example Toronto |
| `lookup_series` | discovery | A table and coordinate → vector ID, series title and unit |
| `submit_plan` | terminal | The plan: steps of `{tool, args_json, description}` |
| `decline` | terminal | Official data cannot answer the question (the series isn't published) |

- **Strict tools, no forced `tool_choice`.** Every tool is `strict: true`. Forced tool use returns a 400 on current models, so the prompt steers the model to finish with `submit_plan` or `decline`.
- **Refusals.** Requests send `fallbacks: "default"` (beta `server-side-fallback-2026-07-01`), so a policy decline is retried on a fallback model. A final `refusal`, or a run that hits `max_tokens`, raises `PlanningError`.
- **Validation feedback.** Every `submit_plan` goes through `validate_plan`. Its problems go back to Claude as an error tool result, so it can fix the plan within the same turn budget.

`validate_plan` (`supervisor/registry.py`) is the deterministic gate. Nothing runs until it passes:

- **Known tools only.** Each tool's arguments are validated against a frozen Pydantic model with `extra="forbid"`. Every problem in the draft is reported in one pass.
- **Fetch steps.** A fetch step loads one series into a named slot (`series_table`, `table_a` to `table_d`, `rent_table`, `income_table`). Vector IDs must match `v[1-9]\d*`. Periods must be `YYYY`, `YYYY-MM` or a real calendar date `YYYY-MM-DD` (`2025-02-30` is rejected), with start ≤ end after normalisation (guardrail 8). A slot holds one series.
- **Confirmed vectors only.** The Claude planner passes the vector IDs `lookup_series` returned in that conversation as `confirmed_vectors`, and any other StatCan vector is rejected. A well-formed guess would otherwise fetch a real but wrong series, and its citation would still verify. Valet series names have no lookup tool, so they aren't checked. Scripted plans (`confirmed_vectors=None`) skip the check.
- **Analyst steps.** An analyst step must read only slots that an earlier fetch step filled. Single-series recipes read the slot named in `slot` (default `series_table`), so a comparison (GT-08, GT-10, GT-11, GT-12) loads two series into two slots and runs the recipe once per slot. The step's `series_id` is **copied from the fetch step that filled the slot it reads**; the model cannot supply it (guardrail 6).
- **Recipes not exposed to the planner.** `multi_year_cagr` would need the model to type numbers. Free-form `custom_sql` isn't deterministic. `cross_geography_ranking` needs input a fetch step can't produce yet.

| Plan tool | Agent | Reads |
| :-- | :-- | :-- |
| `fetch_statcan_vector(vector_id, start, end, into)` | data_fetcher | |
| `fetch_valet_series(series_id, start, end, into)` | data_fetcher | |
| `annual_inflation_rate(expected_periods, slot)` | data_analyst | `slot` (default series_table) |
| `yoy_point_to_point(lag, interval_years, slot)` | data_analyst | `slot` (default series_table) |
| `percentage_point_spread(series_a_name, series_b_name)` | data_analyst | table_a, table_b |
| `affordability_burden_ratio()` | data_analyst | rent_table, income_table |
| `change_vs_standard_error(estimate_slot, standard_error_slot, change_period)` | data_analyst | the two slots it names (#109) |
| `calendar_year_aggregation(agg_func, expected_periods, slot)` | data_analyst | `slot` (default series_table) |
| `discrete_regime_change_counter(year, slot)` | data_analyst | `slot` (default series_table) |

The Data Fetcher normalises periods to whole days: `2024` → `2024-01-01` and `2025` → `2025-12-31`. I checked live that WDS accepts these ranges for monthly (v42127475), annual (v3823103) and single-month (v41692889) series. The fetcher stores rows with `status_code` and `symbol_code`, so the analyst's quality warnings still apply, and adds the connector's citation to `AgentState.citations`.

## Significance questions (#109)

In the CAN-35 sessions (M2 follow-up), the question asked whether Ontario's and Alberta's 12-month changes in the unemployment rate were statistically meaningful. The page fetched and verified four series, the two rates and the standard errors of their year-over-year change, but only computed each change. No step compared a change with its standard error, and the banner read "All cited series verified (4 of 4)".

**What StatCan publishes.** Labour Force Survey table 14-10-0287-01 has a Statistics dimension: Estimate, Standard error of estimate, Standard error of month-to-month change and Standard error of year-over-year change. The change itself isn't published. The table's footnote says to compute it as the estimate minus the estimate for the same month a year earlier, and that the change is significant at the 68% level when the change ± 1 SE excludes zero (± 2 SE for about 95%). The published standard errors are averages over the previous 12 months, updated in February and August.

**`change_vs_standard_error`** (`analyst/recipes.py`) does exactly that, for each period that has a standard error:

| Column | Meaning |
| :-- | :-- |
| `current_value`, `lag_value` | The estimate and the estimate 12 months (or 1 month) earlier |
| `change_absolute`, `standard_error` | The change and the published SE for that period |
| `change_in_se` | Change divided by SE (charted) |
| `ci68_low`, `ci68_high`, `ci95_low`, `ci95_high` | change ± 1 SE and ± 2 SE |
| `significant_68`, `significant_95` | Whether that interval excludes zero |

- The step names its two slots (`estimate_slot`, `standard_error_slot`, which must differ) and `change_period` (`year_over_year` by default, or `month_to_month`). `validate_plan` copies both series IDs from the fetch steps, so the model can't supply them, and the analyst fails loud without both Tier 1 citations.
- It fails loud when the two series have different units, or no period has both an estimate and an SE. A missing prior value or a non-positive SE leaves the significance columns null with a warning.
- The change and SE are rounded to six decimals before comparing. A change equal to its SE (Ontario: 7.6 → 7.3, SE 0.3) touches zero and is not significant, and float noise (7.9 − 7.6 = 0.30000000000000071) can't flip that.
- Comparing two provinces takes four slots, so `table_c` and `table_d` were added.
- A planner rule says to look up the published SE for a significance question, and never to treat a change as significant without one.

**The page.** `RunResult.significance_not_assessed` is true when the question asks about significance (statistically, significant, margin of error, standard error, confidence interval, and the French equivalents) and no `change_vs_standard_error` step ran. The banner then turns into a warning: "All cited series verified (4 of 4), but the question asks about statistical significance, and no step compared a change with its standard error. Significance was not assessed." A bare "meaningful" doesn't count, because "a meaningful drop" is usually not a statistical question.

With October 2026 data (released 2026-11-06): Ontario 7.6 → 7.3 with SE 0.3 (68% interval −0.6 to 0.0), and Alberta 7.6 → 7.3 with SE 0.6 (change of −0.5 SE). Neither change is significant at the 68% level. `tests/test_supervisor.py::test_graph_answers_the_m2_significance_follow_up` runs this case through the graph twice on one thread.

## Follow-up questions (BEN-62)

A follow-up such as "What about Oshawa?" needs the question before it. When the Supervisor plans a new question, the plan still in the state is the previous question's. If that plan completed, the Supervisor builds a `PlanContext` (`supervisor/context.py`) from the previous question, the plan's objective and one line per step (tool, description, arguments), and passes it to `planner.plan(question, context=...)`. It holds no figures, because a step's result summary is not copied in. The text is cleaned and truncated like other untrusted text, only the previous turn is used, and at most eight steps are listed. The planner is told it is background and not an instruction.

A turn that ended in a decline, a failed step or a cancelled clarification leaves no plan, so the next question gets no context. When a follow-up needs a clarification, the context is kept in the scratchpad and used again when the planner plans after the user's choice. A planner that does not take `context` still works until a second question is asked on the same thread.

## Finding archived tables (#103)

In the CAN-35 sessions (question H2), the planner declined to give age-standardized heart disease mortality by province, saying no table publishes it. Three tables do: 13-10-0393-01 (to 2013), 13-10-0396-01 (to 2013) and 13-10-0800-01 (to 2023). All three have every province and "Diseases of heart". The search missed them for two reasons:

- **Word forms.** The question says "age-standardized". The titles say "age standardizing" and "age standardization". The search matched each word as a prefix, so `\bage-standardized` matched neither.
- **The cause is not in the title.** "Heart" is a member of the cause dimension, so no title search for it can succeed. The planner has to search for the measure and then call `find_members`.

The fix:

- **`search_cubes`** (`statcan_wds.py`) splits terms on hyphens and slashes, and matches -ize/-ise forms by stem and a plural "s". So "age-standardized mortality", "age-standardised mortality rates" and "age standardized mortality rate" all return 13-10-0393-01 and 13-10-0800-01 first. Matching still starts at a word, so "rent" doesn't match "current". Tables whose titles contain the query's exact words rank first, which keeps precise queries ("deaths causes") from being pushed down by the looser match. Each result carries `archived` from the WDS cube list ("1" archived, "2" current). The MCP tool `search_statcan_cubes` returns it too.
- **The planner** sees `"archived": true` on archived tables. Its prompt now says:
  - search for the measure, because titles don't name every breakdown;
  - an archived table is still official data;
  - when an archived table is the only one with the figure, plan from it and name its last period instead of declining.

Checked against the live catalog (8,263 tables, 2026-11-24):

- "age-standardized mortality" returns 5 tables, with 13-10-0393-01 and 13-10-0800-01 in them. Before the fix it returned 2 tables, neither of them.
- "deaths causes" has both tables in its first eight.
- Across 11 common queries (CPI, unemployment rate, housing starts, labour force, GDP and others), the match counts are the same, apart from "population estimates" at 100 instead of 98.
- Eight of the 11 queries show the same first eight tables. In the other three, exact-word titles moved up. "Consumer price index" now shows 18-10-0010-01 (CPI, seasonally adjusted) instead of 18-10-0003-01 (inter-city indexes).

Tests:
- `tests/connectors/test_statcan_wds.py` uses the real catalog entries for these tables.
- `test_planner_search_reaches_archived_mortality_tables_for_h2` in `tests/test_supervisor.py` runs the planner's search tool through the real `search_cubes`.

**Not checked:** a live planner run of H2. Claude may still decline, or choose 13-10-0393-01 over the newer 13-10-0800-01. A rerun of the CAN-35 question with an API key would confirm the change in behaviour.

## Using it

```python
from anthropic import AsyncAnthropic

from candata_agent import AsyncSqliteSaver, traced_run
from candata_agent.state import AgentMessage, MessageRole
from candata_agent.supervisor import build_agent_graph
from candata_agent.supervisor.planner import ClaudePlanner  # needs: uv sync --extra agent
from candata_mcp.connectors.boc_valet import ValetClient
from candata_mcp.connectors.statcan_wds import StatCanClient

question = "How many housing units were started in the Toronto CMA in 2025?"
async with StatCanClient() as statcan, ValetClient() as valet, AsyncSqliteSaver("runs.db") as saver:
    app = build_agent_graph(
        planner=ClaudePlanner(AsyncAnthropic(), statcan),
        statcan=statcan,
        valet=valet,
        checkpointer=saver,
    )
    out = await traced_run(
        app,
        {
            "session_id": "s1",
            "thread_id": "t1",
            "messages": (AgentMessage(role=MessageRole.USER, content=question),),
        },
        {"configurable": {"thread_id": "t1"}},
    )
    out["sql_artifacts"][-1].rows  # exact SQL results with their citation
    out["verification"]["passed"]  # every source checked against WDS / Valet
```

## Fork fix (CAN-21 follow-up)

`AsyncSqliteSaver.arollback_to(..., new_thread_id=...)` built the fork checkpoint by hand: no `step` in the metadata and empty `channel_versions`. LangGraph couldn't resume from it (`KeyError: 'step'`). The fork now **copies the source checkpoint as LangGraph wrote it**, keeping its versions and metadata, with `source: "fork"`. Only the state's `thread_id` changes, and `session_id` is kept. `test_forked_thread_continues_with_the_graph` runs a second question on the fork. It fails with the old code and passes with the fix.

## Verification

- **21 offline tests** in `tests/test_supervisor.py`, with real WDS and Valet series in the fakes:
  - **Validation:** the GT-05 plan; every problem reported in one pass; the model can't set `series_id`; a slot holds one series; a recipe reads the slot it names and cites that slot's series (GT-12); impossible dates; unconfirmed vectors; excluded recipes; period bounds.
  - **Planner loop** (fake Messages API): discovery, then an invalid plan fixed from the feedback; a vector submitted before `lookup_series` returned it is rejected; decline; refusal; turn budget. It also asserts strict tools, no `tool_choice`, and `fallbacks: "default"`.
  - **Full graph** (real `StateGraph`, checkpointer, analyst and verifier):
    - Two questions on one thread. GT-05 gives **37,718 / 26,087**, then GT-13 gives **4 changes, 3.25 → 2.25**, and only the second question's citation is re-verified.
    - GT-12 compares two series: Toronto shelter **−0.47%** and all-items **+2.14%** year over year (real WDS values), each citing and verifying its own vector. Asking it again on the same thread plans again.
    - A failed fetch ends the run, and the first question's report isn't carried over. Retrying the same question plans it again and succeeds.
    - Decline and planner errors end the run with a message.
    - The fork resumes.
- `python scripts/verify.py` passes.
- **Not yet run:** `pytest -m live tests/test_supervisor.py`, the real Claude planner with live StatCan discovery on GT-05. It needs `ANTHROPIC_API_KEY`; see `.env.example`.

## Not in scope

- **Writing the final answer.** The run ends with structured results, citations and a verification report. Composing the prose answer from them, and refusing to answer when verification fails, belongs to the answer step, along with CAN-33 (HITL on ambiguity).
- **Plans that need several series in one slot**, for example ranking CMAs. That needs a multi-series fetch step.
