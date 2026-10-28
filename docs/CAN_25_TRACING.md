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

Nested nodes share one trace, so a supervisor span has the analyst and verifier spans as children. An exception is recorded on the span (status `ERROR`) and re-raised.

The node's returned update also gains `trace_context` (W3C `traceparent` and span ID) so a checkpoint can be tied back to its trace. A node that sets its own `trace_context` keeps it.

## Configuration

Set in `.env` (see `.env.example`). With none set, `setup_tracing()` returns `None` and spans go nowhere, which is the default in tests and CI.

| Variable | Effect |
| :-- | :-- |
| `PHOENIX_COLLECTOR_ENDPOINT` | Full OTLP traces URL. Local Phoenix is `http://localhost:6006/v1/traces`. |
| `PHOENIX_API_KEY` | Sent as a bearer token. Not needed for local Phoenix. |
| `PHOENIX_PROJECT_NAME` | Phoenix project, set as `openinference.project.name`. |
| `LANGSMITH_API_KEY` | Enables the LangSmith OTLP exporter (`api.smith.langchain.com/otel/v1/traces`). |
| `LANGSMITH_PROJECT` | Sent as the `Langsmith-Project` header. |

`opentelemetry-api` is a base dependency. The SDK and OTLP exporter are in the optional `tracing` extra (`uv sync --extra tracing`) and also in the dev group, so tests run without it.

## Contract for node authors (CAN-22, CAN-23, CAN-24)

- Decorate each node with `@traced_node("<name>")`: `supervisor`, `data_analyst`, `citation_verifier`.
- A node that calls a model returns `token_budget` with the cumulative counts after the call. The decorator derives the delta.
- Nodes with no model call (the Citation Verifier) report latency only; its cost is the WDS and Valet round trips.
- No node logic changes: this PR adds a decorator and does not edit CAN-22 to CAN-24.

## Verification

- 13 offline tests in `tests/test_tracing.py` using an in-memory exporter: span name and attributes, `traceparent` matching the span, token delta and cost, error status, dict state, nested traces, and the environment-to-exporter mapping.
- `ruff`, `ruff format --check`, `pyright` (strict) and `pytest` pass.
- **Not verified:** export to live Phoenix or LangSmith. The LangSmith endpoint and header names follow its OTLP documentation but were not exercised against the service.

## Not in scope

- Auto-instrumenting LLM client calls (OpenInference or LangChain callbacks). Nodes report their own token counts.
- Wrapping the CAN-22 to CAN-24 nodes. Each author adds the decorator, or a follow-up does once all three merge.
- A pricing table per model.
