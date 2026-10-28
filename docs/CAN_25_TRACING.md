# CAN-25: OpenTelemetry Tracing for Sub-Agents

**Owner:** Yassir · **Milestone:** 2 (Sprint 2) · **Linear:** BEN-20 · **Code:** `packages/agent-orchestrator/src/candata_agent/tracing.py`

Every LangGraph node can emit one OpenTelemetry span per run. The span records step latency and, for nodes that call a model, the tokens and estimated cost added by that step. Spans export over OTLP/HTTP to Arize Phoenix and LangSmith.

## Using it

```python
from candata_agent import TokenPricing, setup_tracing, traced_node

setup_tracing()  # once at startup; reads the environment, returns None if nothing is set


@traced_node("supervisor", pricing=TokenPricing(input_per_million=3.0, output_per_million=15.0))
async def supervisor(state: AgentState) -> dict[str, Any]:
    ...
    return {"plan": plan, "token_budget": new_budget}
```

`traced_node` works on any async node taking a Pydantic `AgentState` or a dict state, with extra positional or keyword arguments passed through.

## What a span carries

| Attribute | Source |
| :-- | :-- |
| `candata.agent` | the name given to `traced_node` |
| `candata.run_id`, `candata.thread_id`, `candata.session_id` | `AgentState` |
| `candata.latency_ms` | wall time of the node, also set when it raises |
| `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens` | `token_budget` in the node's update, minus the `token_budget` it received |
| `candata.tokens_remaining` | `TokenBudget.remaining_tokens` after the step |
| `candata.cost_usd` | tokens × `TokenPricing`, only when pricing is passed |

**One graph run is one trace.** The first traced node starts the trace and stores its W3C `traceparent` and span ID in `AgentState.trace_context`. Every later node reads that field and becomes a child span, so a run shows as a single tree with end-to-end latency (for example `supervisor` → `data_analyst`, `citation_verifier`). A checkpoint can be tied back to its trace through the same field, and a time-travel replay continues the original trace. A node that sets its own `trace_context` keeps it.

An exception is recorded on the span (status `ERROR`) and re-raised.

## Configuration

Set in `.env` (see `.env.example`). With none set, `setup_tracing()` returns `None` and spans go nowhere, which is the default in tests and CI.

| Variable | Effect |
| :-- | :-- |
| `PHOENIX_COLLECTOR_ENDPOINT` | Full OTLP traces URL. Local Phoenix is `http://localhost:6006/v1/traces`. |
| `PHOENIX_API_KEY` | Sent as a bearer token. Not needed for local Phoenix. |
| `PHOENIX_PROJECT_NAME` | Phoenix project, set as `openinference.project.name`. |
| `LANGSMITH_API_KEY` | Enables the LangSmith OTLP exporter (`api.smith.langchain.com/otel/v1/traces`). |
| `LANGSMITH_PROJECT` | Sent as the `Langsmith-Project` header. |
| `LANGSMITH_ENDPOINT` | LangSmith base URL, default `https://api.smith.langchain.com`. Use `https://eu.api.smith.langchain.com` for the EU region, or the self-hosted URL ending in `/api/v1`. The OTLP path `/otel/v1/traces` is appended. |

`opentelemetry-api` is a base dependency. The SDK and OTLP exporter are in the optional `tracing` extra (`uv sync --extra tracing`) and also in the dev group, so tests run without it.

## Contract for node authors (CAN-22, CAN-23, CAN-24)

- Decorate each node with `@traced_node("<name>")`: `supervisor`, `data_analyst`, `citation_verifier`.
- A node that calls a model returns `token_budget` with the cumulative counts after the call. The decorator derives the delta.
- Nodes with no model call (the Citation Verifier) report latency only; its cost is the WDS and Valet round trips.
- No node logic changes: this PR adds a decorator and does not edit CAN-22 to CAN-24.

## Verification

- 16 offline tests in `tests/test_tracing.py`:
  - span name and attributes, `traceparent` matching the span, token delta and cost, error status, dict state, nested and cross-node traces;
  - the environment-to-exporter mapping;
  - a **wire-level test** that runs a local OTLP/HTTP receiver and checks that Phoenix and LangSmith configurations each POST the span to the right path with the right headers (`authorization: Bearer …`, `x-api-key`, `langsmith-project`) and the project resource attribute.
- `ruff`, `ruff format --check`, `pyright` (strict) and `pytest` pass.
- **Smoke run against a real Phoenix server** (a throwaway environment, not committed): a LangGraph `StateGraph` with `supervisor`, `data_analyst` and `citation_verifier` nodes decorated with `traced_node`, exporting to a local Phoenix 6006. Phoenix accepted the export, listed the spans under the configured project, and showed the token, cost and latency attributes. The analyst and verifier spans had the supervisor span as parent, one trace per run. This also confirms the decorator works with LangGraph's calling convention and a Pydantic `AgentState`.
- LangSmith's endpoint and header names were checked against its OpenTelemetry documentation.
- **Not verified: export to the live LangSmith service.** It needs an API key. See the follow-up issue linked in the PR.

## Not in scope

- Auto-instrumenting LLM client calls (OpenInference or LangChain callbacks). Nodes report their own token counts.
- Wrapping the CAN-22 to CAN-24 nodes. Each author adds the decorator, or a follow-up does once all three merge.
- A pricing table per model.
