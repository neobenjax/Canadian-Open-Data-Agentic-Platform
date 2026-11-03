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
- **Fetch steps.** A fetch step loads one series into a named slot (`series_table`, `table_a`, `table_b`, `rent_table`, `income_table`). Vector IDs must match `v[1-9]\d*`. Periods must be `YYYY`, `YYYY-MM` or a real calendar date `YYYY-MM-DD` (`2025-02-30` is rejected), with start ≤ end after normalisation (guardrail 8). A slot holds one series.
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
| `calendar_year_aggregation(agg_func, expected_periods, slot)` | data_analyst | `slot` (default series_table) |
| `discrete_regime_change_counter(year, slot)` | data_analyst | `slot` (default series_table) |

The Data Fetcher normalises periods to whole days: `2024` → `2024-01-01` and `2025` → `2025-12-31`. I checked live that WDS accepts these ranges for monthly (v42127475), annual (v3823103) and single-month (v41692889) series. The fetcher stores rows with `status_code` and `symbol_code`, so the analyst's quality warnings still apply, and adds the connector's citation to `AgentState.citations`.

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
