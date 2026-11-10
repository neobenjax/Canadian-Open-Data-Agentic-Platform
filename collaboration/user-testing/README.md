# User testing pilot (simulated) for the agent UI

**Status: Pilot (simulated).** This is a rehearsal of the CAN-35 sessions, not the sessions
themselves. The personas are fictional and played by an AI assistant driving the local
Streamlit UI. It does not count as the 3 sessions with external researchers.

## Purpose

1. Rehearse the real sessions: find script and UI problems before external researchers see them.
2. Compare the live planner with the earlier demo-mode results (CAN-32 manual run, CAN-41
   report `collaboration/benchmarks/agent_evals/agent_demo_live_20261104_report.md`).
3. Exercise the live planner and the pause-and-ask step, which no demo run covers.

## Setup

- Local UI in live mode: `uv run streamlit run apps/agent-ui/app.py` with `ANTHROPIC_API_KEY`
  set in `.env` (a personal key, not a team key).
- One new conversation per persona.
- Statistics Canada's service is unavailable 00:00-08:30 ET; run outside that window.

## Method

Each persona asks one question in its own words. Per question we record: time to a verified
answer, whether the numbers match the stored benchmark values, whether citations, series IDs and
quality flags are visible, whether the chart or refusal reads clearly for that persona, and any
confusion, with a severity and a suggested fix. See `feedback_log_template.md`.

Questions 1-3 repeat benchmark questions (GT-12, GT-05, GT-13) so the live answers can be
compared with the stored demo results. Questions 4-6 have no stored baseline and are
observations only.

## Rounds

Round 1 (six questions) ran first. Its gaps decided what round 2 (seven questions) tested; the
mapping is in `pilot_results.md`.

## Setup note

The UI reads `ANTHROPIC_API_KEY` from the process environment, not from `.env`. Export it in the
shell before `streamlit run`, or the page starts in demo mode.

## Files

- `personas.md`: the three personas and their questions.
- `feedback_log_template.md`: the log each run fills in.
- `pilot_results.md`: results of the run (added after the run).
