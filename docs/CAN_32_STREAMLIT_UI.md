# CAN-32: Streamlit UI with `astream_events` v2 streaming and Plotly charts

The UI lets you ask a question, watch the Supervisor, Data Fetcher, Data Analyst and Citation
Verifier work in real time, and see the official series and computed results as charts, with
their citations and verification verdicts.

It is stacked on #46 (CAN-22), which provides the graph.

## Run it

```bash
uv sync --extra ui --extra agent
uv run streamlit run apps/agent-ui/app.py
```

- **Live mode** (`ANTHROPIC_API_KEY` set): Claude plans any question from StatCan discovery.
- **Demo mode** (no key): only the three example questions (GT-12, GT-05 and GT-13) are
  planned, using fixed, validated plans. Their data is still fetched live from WDS and Valet,
  computed by DuckDB and verified against the publisher; nothing is precomputed. Any other
  question is declined with a pointer to live mode.

Conversations are checkpointed to `.candata/ui_threads.db` (git-ignored by `*.db`), so a thread
survives Streamlit reruns. **New conversation** starts a new thread.

## Layout

| Piece | Where | What it does |
|---|---|---|
| Stream adapter | `candata_agent/ui/stream.py` | `stream_question()` drives `astream_events(version="v2")`. It yields `NodeStarted` / `NodeFinished` per graph node, then `RunFinished(RunResult)`. |
| Charts | `candata_agent/ui/charts.py` | `series_figure()` draws the fetched series; `result_figure()` draws the headline metric of time-series recipes. |
| Session | `candata_agent/ui/session.py` | `open_agent()` builds the graph on live `StatCanClient` / `ValetClient` with a SQLite checkpointer. Also holds `DemoPlanner`. |
| Page | `apps/agent-ui/app.py` | Thin Streamlit page: sidebar, chat, live status box, then the rendered result. |

`RunResult` is built only from **this run's** node outputs, never from the thread's final state.
So a second question on a thread shows only its own series, results and citations.

## Chart rules

- **One y-axis per unit.** Series sharing a unit share an axis. Different units become stacked
  small multiples on a shared time axis, never a second y-axis.
- **Colour follows plan order** (Okabe-Ito palette, colour-blind safe), and every series is named
  by its plan step's description plus its ID, e.g. `Toronto shelter CPI (v41692889)`.
- **Quality flags stay visible** (guardrail 6). Observations with a StatCan status or symbol code
  get an outlined diamond, and the hover text names the code. The page also counts flagged
  observations.
- **Results:** `yoy_point_to_point`, `annual_inflation_rate`, `calendar_year_aggregation` and
  `percentage_point_spread` become bars (grouped for comparisons such as GT-12). Other recipes,
  such as regime-change counts, CAGR and rankings, are shown as tables. Every result also shows
  its table and the SQL that produced it.

## Change outside `ui/`

The Data Fetcher now also writes `<slot>_unit` to the scratchpad next to `<slot>_source`. The UI
uses it to decide whether series can share an axis.

## Verification

- `tests/test_ui.py` has 12 offline tests:
  - The real graph streamed twice on one thread, checking node order, per-run isolation, that
    each message is shown once, and that both GT-12 vectors are verified.
  - A failed fetch surfaced as `failed_step`.
  - The demo planner: it plans exactly the benchmark questions and declines the rest.
  - The chart rules: shared axis, small multiples, flags, grouped bars, period order.
- `scripts/verify.py` is clean.
- **Manual run in demo mode against the live APIs** (2026-11-03). All three examples verified,
  asked one after another on one thread:
  - GT-12: shelter −0.47%, all-items +2.14%.
  - GT-05: 37,718 (2024) vs 26,087 (2025).
  - GT-13: V39079.

## Known gaps / follow-ups

- **Split with Yassir:** the CAN-32 split is still to be agreed. The proposal is that this PR
  covers streaming and charts, and Yassir owns page layout and the user-testing flow (CAN-35).
  The page here is a working baseline to restyle.
- **No root span for streamed runs.** `traced_run` wraps `ainvoke`, not `astream_events`, so a
  streamed run has no `graph.run` root span. Its nodes are still traced individually (CAN-25).
- **No units on live StatCan series.** The live WDS results come back without a unit, so StatCan
  charts have no y-axis title. The unit resolution lives in the connector.
- **Live planner untested.** Live mode is untested until there is a team `ANTHROPIC_API_KEY`
  (same blocker as #46's live test).
- **HITL interrupts not rendered.** The page doesn't show `interrupt()` prompts yet; that is
  CAN-33.
