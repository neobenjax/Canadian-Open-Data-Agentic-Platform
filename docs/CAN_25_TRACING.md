# CAN-25: OpenTelemetry Tracing for Sub-Agents

**Owner:** Yassir · **Milestone:** 2 (Sprint 2) · **Linear:** BEN-20 · **Code:** `packages/agent-orchestrator/src/candata_agent/tracing.py`

Every graph invocation emits one OpenTelemetry trace: a `graph.run` root span with one `agent.<name>` child span per node run. A node span records step latency and, for nodes that call a model, the tokens and estimated cost added by that step. Spans export over OTLP/HTTP to Arize Phoenix and LangSmith.

## Using it

```python
from candata_agent import TokenPricing, setup_tracing, traced_node, traced_run

setup_tracing()  # once at startup; reads the environment, returns None if nothing is set


@traced_node("supervisor", pricing=TokenPricing(input_per_million=3.0, output_per_million=15.0))
async def supervisor(state: AgentState) -> dict[str, Any]:
    ...
    return {"plan": plan, "token_budget": new_budget}


# Where the compiled graph is invoked, use traced_run instead of app.ainvoke:
result = await traced_run(app, {"run_id": run_id, ...}, {"configurable": {"thread_id": thread_id}})
```

`traced_node` works on any async node taking a Pydantic `AgentState` or a dict state, with extra positional or keyword arguments passed through. A node that returns `None` (which LangGraph allows) is treated as returning `{}`.

## What a span carries

| Attribute | Source |
| :-- | :-- |
| `candata.agent` | the name given to `traced_node` (node spans only) |
| `candata.run_id`, `candata.thread_id`, `candata.session_id` | `AgentState`, on node spans and the `graph.run` root (the root also reads `configurable.thread_id` from the config) |
| `candata.latency_ms` | wall time of the node, also set when it raises |
| `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens` | `token_budget` in the node's update, minus the `token_budget` it received |
| `candata.tokens_remaining` | `TokenBudget.remaining_tokens` after the step |
| `candata.cost_usd` | tokens × `TokenPricing`, only when pricing is passed |

**One graph invocation is one trace.** `traced_run` opens the `graph.run` root span, calls `app.ainvoke` inside it, and the node spans become its children through OpenTelemetry's own context (checked with a real LangGraph graph; the context reaches the node tasks). The root span gives the run its end-to-end latency, so a run shows as one tree in Phoenix or LangSmith: `graph.run` → `agent.supervisor`, `agent.data_analyst`, `agent.citation_verifier`.

- **Two questions on one thread are two traces.** `AgentState.trace_context` is checkpointed, so a node that read its parent from state would attach the second question to the first question's finished span. Node spans therefore never read parent context from state. `traced_run` also overwrites `input.trace_context` with the new root's context, so the checkpoint always points at the latest run.
- **Tracing never writes a state channel.** `traced_node` returns the node's update unchanged. Two traced nodes in one parallel step cannot collide on `trace_context` (LangGraph rejects two writes to one key in a step).
- **Resuming a trace.** To replay a checkpoint inside its original trace, pass the stored context: `traced_run(app, input, config, continue_from=stored_trace_context)`.
- **Without `traced_run`**, each node span is the root of its own trace. Use `traced_run` wherever the graph is invoked.

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

## Contract for node authors and graph callers

- Decorate each node with `@traced_node("<name>")`: `supervisor`, `data_analyst`, `citation_verifier`. Each node's owner adds the line in their own PR.
- Invoke the compiled graph through `traced_run`, not `app.ainvoke`.
- A node that calls a model returns `token_budget` with the cumulative counts after the call. The decorator derives the delta.
- Nodes with no model call (the Citation Verifier) report latency only; its cost is the WDS and Valet round trips.
- No node logic changes: this PR adds the tracing module and does not edit the CAN-22 to CAN-24 nodes.

## Verification

- 24 offline tests in `tests/test_tracing.py`:
  - span name and attributes, token delta and cost, error status, dict state, `None` and non-mapping updates, the update returned unchanged;
  - **traces:** a checkpointed fake graph invoked twice on one thread gives two distinct traces with the nodes parented to each run's root; a stale `trace_context` on the input is replaced; `continue_from` resumes the original trace; parallel nodes in one step do not conflict;
  - the environment-to-exporter mapping;
  - a **wire-level test** that runs a local OTLP/HTTP receiver and checks that Phoenix and LangSmith configurations each POST the span to the right path with the right headers (`authorization: Bearer …`, `x-api-key`, `langsmith-project`) and the project resource attribute.
- Each of the trace and update tests fails when its bug is put back (decorator writes `trace_context` again, `None` update not handled, `traced_run` not resetting the context).
- `ruff`, `ruff format --check`, `pyright` (strict) and `pytest` pass.
- **Smoke runs in a throwaway environment, not committed:**
  - A real LangGraph `StateGraph` with a `MemorySaver` checkpointer: two questions on one thread give two traces, each with a `graph.run` root and the three node spans as its children. A parallel step and a node returning `None` both run without error.
  - The same kind of graph exporting to a local Phoenix server: Phoenix accepted the export, listed the spans under the configured project, and showed the token, cost and latency attributes.
- LangSmith's endpoint and header names were checked against its OpenTelemetry documentation.
- **Not verified: export to the live LangSmith service.** It needs an API key. See the follow-up issue linked in the PR.

## Not in scope

- Auto-instrumenting LLM client calls (OpenInference or LangChain callbacks). Nodes report their own token counts.
- Decorating the CAN-22 to CAN-24 nodes and switching the graph's callers to `traced_run`. Each node's owner adds the decorator in their own PR.
- A pricing table per model.
