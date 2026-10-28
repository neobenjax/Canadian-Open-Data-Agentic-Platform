"""Tests for CAN-25 OpenTelemetry tracing of LangGraph sub-agent nodes."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Awaitable, Callable
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from candata_agent.state import AgentState, TokenBudget, TraceContext
from candata_agent.tracing import (
    LANGSMITH_API_URL,
    LANGSMITH_TRACES_PATH,
    TokenPricing,
    _exporter_configs,  # pyright: ignore[reportPrivateUsage]
    setup_tracing,
    traced_node,
    traced_run,
)


@pytest.fixture
def exporter() -> InMemorySpanExporter:
    return InMemorySpanExporter()


@pytest.fixture
def provider(exporter: InMemorySpanExporter) -> TracerProvider:
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(exporter))
    return tracer_provider


@pytest.fixture
def state() -> AgentState:
    return AgentState(
        session_id="s1",
        thread_id="t1",
        run_id="run_abc",
        token_budget=TokenBudget(prompt_tokens_used=100, completion_tokens_used=20),
    )


def _only_span(exporter: InMemorySpanExporter) -> ReadableSpan:
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    return spans[0]


async def test_span_records_agent_ids_and_latency(
    provider: TracerProvider, exporter: InMemorySpanExporter, state: AgentState
) -> None:
    @traced_node("supervisor", tracer_provider=provider)
    async def supervisor(state: AgentState) -> dict[str, Any]:
        return {}

    await supervisor(state)

    span = _only_span(exporter)
    attrs = span.attributes or {}
    assert span.name == "agent.supervisor"
    assert attrs["candata.agent"] == "supervisor"
    assert attrs["candata.run_id"] == "run_abc"
    assert attrs["candata.thread_id"] == "t1"
    assert attrs["candata.session_id"] == "s1"
    latency = attrs["candata.latency_ms"]
    assert isinstance(latency, float) and latency >= 0


async def test_update_is_returned_unchanged_without_a_trace_context_write(
    provider: TracerProvider, exporter: InMemorySpanExporter, state: AgentState
) -> None:
    @traced_node("data_analyst", tracer_provider=provider)
    async def analyst(state: AgentState) -> dict[str, Any]:
        return {"scratchpad": {"rows": 3}}

    update = await analyst(state)

    assert update == {"scratchpad": {"rows": 3}}
    assert _only_span(exporter).name == "agent.data_analyst"


async def test_none_update_is_treated_as_empty(
    provider: TracerProvider, exporter: InMemorySpanExporter, state: AgentState
) -> None:
    @traced_node("supervisor", pricing=TokenPricing(3.0, 15.0), tracer_provider=provider)
    async def node(state: AgentState) -> None:
        return None

    assert await node(state) == {}

    attrs = _only_span(exporter).attributes or {}
    assert not any(key.startswith("gen_ai.usage") for key in attrs)


async def test_non_mapping_update_is_passed_through(
    provider: TracerProvider, state: AgentState
) -> None:
    marker = object()

    @traced_node("supervisor", tracer_provider=provider)
    async def node(state: AgentState) -> object:
        return marker

    assert await node(state) is marker


class _StepConflictError(Exception):
    """Stands in for LangGraph's InvalidUpdateError: two writes to one key in one step."""


class _FakeGraph:
    """Checkpointed graph stand-in: runs steps in order, nodes in a step concurrently.

    State persists per ``thread_id``, and a dict input overlays only the keys it names, as a
    LangGraph checkpointer does. Two nodes of one step writing the same key is an error.
    """

    def __init__(self, *steps: list[Callable[..., Awaitable[Any]]]) -> None:
        self.steps = steps
        self.saved: dict[str, AgentState] = {}
        self.inputs: list[Any] = []

    async def ainvoke(self, input: Any, config: Any = None, **kwargs: Any) -> AgentState:
        self.inputs.append(input)
        thread_id = config["configurable"]["thread_id"]
        state = self.saved.get(thread_id) or AgentState(session_id="s1", thread_id=thread_id)
        state = state.model_copy(update=dict(input)) if isinstance(input, dict) else input
        for step in self.steps:
            updates = await asyncio.gather(*(node(state) for node in step))
            merged: dict[str, Any] = {}
            for update in updates:
                if clash := merged.keys() & update.keys():
                    raise _StepConflictError(f"Can receive only one value per step: {clash}")
                merged.update(update)
            state = state.model_copy(update=merged)
        self.saved[thread_id] = state
        return state


def _nodes(provider: TracerProvider) -> tuple[Callable[..., Awaitable[Any]], ...]:
    @traced_node("supervisor", tracer_provider=provider)
    async def supervisor(state: AgentState) -> dict[str, Any]:
        return {}

    @traced_node("data_analyst", tracer_provider=provider)
    async def analyst(state: AgentState) -> dict[str, Any]:
        return {"scratchpad": {"rows": 1}}

    return supervisor, analyst


def _spans(exporter: InMemorySpanExporter, name: str) -> list[ReadableSpan]:
    return [s for s in exporter.get_finished_spans() if s.name == name]


async def test_each_invocation_on_a_thread_is_its_own_trace(
    provider: TracerProvider, exporter: InMemorySpanExporter
) -> None:
    supervisor, analyst = _nodes(provider)
    graph = _FakeGraph([supervisor], [analyst])
    config = {"configurable": {"thread_id": "t1"}}

    await traced_run(graph, {"run_id": "run_1"}, config, tracer_provider=provider)
    await traced_run(graph, {"run_id": "run_2"}, config, tracer_provider=provider)

    first_run, second_run = _spans(exporter, "graph.run")
    assert first_run.context is not None and second_run.context is not None
    assert first_run.context.trace_id != second_run.context.trace_id
    for run in (first_run, second_run):
        assert run.context is not None
        children = [s for s in exporter.get_finished_spans() if s.parent is not None]
        in_run = [c for c in children if c.context and c.context.trace_id == run.context.trace_id]
        assert sorted(c.name for c in in_run) == ["agent.data_analyst", "agent.supervisor"]
        assert all(c.parent and c.parent.span_id == run.context.span_id for c in in_run)
    # The checkpointed context points at the latest run, not the first question's trace.
    saved = graph.saved["t1"].trace_context.traceparent
    assert saved is not None and format(second_run.context.trace_id, "032x") in saved


async def test_run_span_has_ids_and_covers_its_nodes(
    provider: TracerProvider, exporter: InMemorySpanExporter
) -> None:
    supervisor, analyst = _nodes(provider)
    graph = _FakeGraph([supervisor], [analyst])
    state = AgentState(session_id="s1", thread_id="t1", run_id="run_abc")

    await traced_run(graph, state, {"configurable": {"thread_id": "t1"}}, tracer_provider=provider)

    (run,) = _spans(exporter, "graph.run")
    attrs = run.attributes or {}
    assert attrs["candata.run_id"] == "run_abc"
    assert attrs["candata.thread_id"] == "t1"
    assert attrs["candata.session_id"] == "s1"
    for node_span in exporter.get_finished_spans():
        if node_span is not run:
            assert run.start_time is not None and node_span.start_time is not None
            assert run.end_time is not None and node_span.end_time is not None
            assert run.start_time <= node_span.start_time <= node_span.end_time <= run.end_time


async def test_stale_trace_context_on_an_agent_state_input_is_replaced(
    provider: TracerProvider, exporter: InMemorySpanExporter
) -> None:
    stale = TraceContext(traceparent="00-" + "a" * 32 + "-" + "b" * 16 + "-01")
    state = AgentState(session_id="s1", thread_id="t1", trace_context=stale)
    graph = _FakeGraph()

    await traced_run(graph, state, {"configurable": {"thread_id": "t1"}}, tracer_provider=provider)

    (run,) = _spans(exporter, "graph.run")
    assert run.context is not None and run.parent is None
    (sent,) = graph.inputs
    assert sent.trace_context.traceparent != stale.traceparent
    assert format(run.context.trace_id, "032x") in sent.trace_context.traceparent
    assert state.trace_context is stale  # the caller's object is not mutated


async def test_continue_from_resumes_the_original_trace(
    provider: TracerProvider, exporter: InMemorySpanExporter
) -> None:
    supervisor, analyst = _nodes(provider)
    graph = _FakeGraph([supervisor], [analyst])
    config = {"configurable": {"thread_id": "t1"}}
    await traced_run(graph, {}, config, tracer_provider=provider)
    stored = graph.saved["t1"].trace_context

    await traced_run(graph, {}, config, continue_from=stored, tracer_provider=provider)

    original, replay = _spans(exporter, "graph.run")
    assert original.context is not None and replay.context is not None
    assert replay.context.trace_id == original.context.trace_id
    assert replay.parent is not None and replay.parent.span_id == original.context.span_id


async def test_nodes_in_one_step_do_not_conflict_on_trace_context(
    provider: TracerProvider, exporter: InMemorySpanExporter
) -> None:
    supervisor, analyst = _nodes(provider)
    graph = _FakeGraph([supervisor, analyst])  # a parallel first step

    await traced_run(graph, {}, {"configurable": {"thread_id": "t1"}}, tracer_provider=provider)

    (run,) = _spans(exporter, "graph.run")
    nodes = [s for s in exporter.get_finished_spans() if s is not run]
    assert sorted(s.name for s in nodes) == ["agent.data_analyst", "agent.supervisor"]
    assert run.context is not None
    assert all(s.parent and s.parent.span_id == run.context.span_id for s in nodes)


async def test_parallel_traced_nodes_work_without_a_run_span(
    provider: TracerProvider, exporter: InMemorySpanExporter
) -> None:
    supervisor, analyst = _nodes(provider)
    graph = _FakeGraph([supervisor, analyst])

    await graph.ainvoke({}, {"configurable": {"thread_id": "t1"}})

    assert sorted(s.name for s in exporter.get_finished_spans()) == [
        "agent.data_analyst",
        "agent.supervisor",
    ]


async def test_traced_run_accepts_a_missing_config_and_extra_keyword_arguments(
    provider: TracerProvider, exporter: InMemorySpanExporter
) -> None:
    seen: dict[str, Any] = {}

    class Recorder:
        async def ainvoke(self, input: Any, config: Any = None, **kwargs: Any) -> str:
            seen.update(input=input, config=config, **kwargs)
            return "done"

    result = await traced_run(Recorder(), {"q": 1}, stream_mode="values", tracer_provider=provider)

    assert result == "done"
    assert seen["config"] is None and seen["stream_mode"] == "values"
    assert seen["input"]["q"] == 1 and seen["input"]["trace_context"].traceparent
    assert _only_span(exporter).name == "graph.run"


async def test_node_supplied_trace_context_is_kept(
    provider: TracerProvider, state: AgentState
) -> None:
    own = TraceContext(traceparent="00-" + "a" * 32 + "-" + "b" * 16 + "-01")

    @traced_node("supervisor", tracer_provider=provider)
    async def node(state: AgentState) -> dict[str, Any]:
        return {"trace_context": own}

    assert (await node(state))["trace_context"] is own


async def test_token_usage_is_the_delta_over_incoming_state(
    provider: TracerProvider, exporter: InMemorySpanExporter, state: AgentState
) -> None:
    pricing = TokenPricing(input_per_million=3.0, output_per_million=15.0)

    @traced_node("supervisor", pricing=pricing, tracer_provider=provider)
    async def node(state: AgentState) -> dict[str, Any]:
        used = TokenBudget(
            prompt_tokens_used=1_100,
            completion_tokens_used=520,
            total_tokens_used=1_620,
        )
        return {"token_budget": used}

    await node(state)

    attrs = _only_span(exporter).attributes or {}
    assert attrs["gen_ai.usage.input_tokens"] == 1_000
    assert attrs["gen_ai.usage.output_tokens"] == 500
    assert attrs["candata.tokens_remaining"] == 128_000 - 1_620
    assert attrs["candata.cost_usd"] == pytest.approx(0.003 + 0.0075)


async def test_node_without_token_budget_has_no_token_attributes(
    provider: TracerProvider, exporter: InMemorySpanExporter, state: AgentState
) -> None:
    @traced_node("citation_verifier", tracer_provider=provider)
    async def node(state: AgentState) -> dict[str, Any]:
        return {}

    await node(state)

    attrs = _only_span(exporter).attributes or {}
    assert not any(key.startswith("gen_ai.usage") for key in attrs)
    assert "candata.cost_usd" not in attrs


async def test_exception_is_recorded_and_reraised(
    provider: TracerProvider, exporter: InMemorySpanExporter, state: AgentState
) -> None:
    @traced_node("data_analyst", tracer_provider=provider)
    async def node(state: AgentState) -> dict[str, Any]:
        raise RuntimeError("duckdb exploded")

    with pytest.raises(RuntimeError, match="duckdb exploded"):
        await node(state)

    span = _only_span(exporter)
    assert span.status.status_code is StatusCode.ERROR
    assert [event.name for event in span.events] == ["exception"]
    assert "candata.latency_ms" in (span.attributes or {})


async def test_dict_state_and_extra_arguments(
    provider: TracerProvider, exporter: InMemorySpanExporter
) -> None:
    @traced_node("supervisor", tracer_provider=provider)
    async def node(state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        return {"seen": config["tag"]}

    update = await node({"run_id": "run_x", "thread_id": "t9"}, {"tag": "ok"})

    assert update["seen"] == "ok"
    attrs = _only_span(exporter).attributes or {}
    assert attrs["candata.run_id"] == "run_x"
    assert "candata.session_id" not in attrs


async def test_nested_node_spans_share_a_trace(
    provider: TracerProvider, exporter: InMemorySpanExporter, state: AgentState
) -> None:
    @traced_node("data_analyst", tracer_provider=provider)
    async def inner(state: AgentState) -> dict[str, Any]:
        return {}

    @traced_node("supervisor", tracer_provider=provider)
    async def outer(state: AgentState) -> dict[str, Any]:
        return await inner(state)

    await outer(state)

    child, parent = exporter.get_finished_spans()
    assert child.context is not None and parent.context is not None
    assert child.context.trace_id == parent.context.trace_id
    assert child.parent is not None and child.parent.span_id == parent.context.span_id


def test_pricing_cost() -> None:
    assert TokenPricing(3.0, 15.0).cost(2_000_000, 1_000_000) == pytest.approx(21.0)


def test_no_backend_configured_means_no_provider() -> None:
    assert setup_tracing({}, set_global=False) is None


def test_phoenix_and_langsmith_configs_from_env() -> None:
    configs = _exporter_configs(
        {
            "PHOENIX_COLLECTOR_ENDPOINT": "http://phoenix:6006/v1/traces",
            "PHOENIX_API_KEY": "px-key",
            "LANGSMITH_API_KEY": "ls-key",
            "LANGSMITH_PROJECT": "candata-dev",
        }
    )

    assert configs == [
        ("http://phoenix:6006/v1/traces", {"authorization": "Bearer px-key"}),
        (
            LANGSMITH_API_URL + LANGSMITH_TRACES_PATH,
            {"x-api-key": "ls-key", "Langsmith-Project": "candata-dev"},
        ),
    ]


def test_local_phoenix_needs_no_key() -> None:
    configs = _exporter_configs({"PHOENIX_COLLECTOR_ENDPOINT": "http://localhost:6006/v1/traces"})

    assert configs == [("http://localhost:6006/v1/traces", {})]


def test_setup_tracing_builds_a_provider_per_configured_env() -> None:
    provider = setup_tracing(
        {"PHOENIX_COLLECTOR_ENDPOINT": "http://localhost:6006/v1/traces", "LANGSMITH_API_KEY": "k"},
        set_global=False,
    )

    assert isinstance(provider, TracerProvider)
    attrs = provider.resource.attributes
    assert attrs["service.name"] == "candata-agent"
    assert attrs["openinference.project.name"] == "candata"
    provider.shutdown()


class _Receiver:
    """Local OTLP/HTTP endpoint that records every POST it gets."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, dict[str, str], bytes]] = []
        received = self.requests

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 - http.server API
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                received.append((self.path, {k.lower(): v for k, v in self.headers.items()}, body))
                self.send_response(200)
                self.send_header("Content-Type", "application/x-protobuf")
                self.end_headers()

            def log_message(self, format: str, *args: Any) -> None:
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> _Receiver:
        self.thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.server.shutdown()
        self.server.server_close()


async def test_spans_reach_phoenix_and_langsmith_endpoints_with_expected_headers(
    state: AgentState,
) -> None:
    with _Receiver() as phoenix, _Receiver() as langsmith:
        provider = setup_tracing(
            {
                "PHOENIX_COLLECTOR_ENDPOINT": f"{phoenix.url}/v1/traces",
                "PHOENIX_API_KEY": "px-key",
                "PHOENIX_PROJECT_NAME": "candata-test",
                "LANGSMITH_API_KEY": "ls-key",
                "LANGSMITH_PROJECT": "candata-ls",
                "LANGSMITH_ENDPOINT": langsmith.url,
            },
            set_global=False,
        )
        assert isinstance(provider, TracerProvider)

        @traced_node("supervisor", tracer_provider=provider)
        async def supervisor(state: AgentState) -> dict[str, Any]:
            return {}

        await supervisor(state)
        assert provider.force_flush()
        provider.shutdown()

    ((px_path, px_headers, px_body),) = phoenix.requests
    assert px_path == "/v1/traces"
    assert px_headers["authorization"] == "Bearer px-key"
    assert b"agent.supervisor" in px_body
    assert b"candata-test" in px_body

    ((ls_path, ls_headers, ls_body),) = langsmith.requests
    assert ls_path == "/otel/v1/traces"
    assert ls_headers["x-api-key"] == "ls-key"
    assert ls_headers["langsmith-project"] == "candata-ls"
    assert b"agent.supervisor" in ls_body


def test_langsmith_base_url_override_for_other_regions() -> None:
    configs = _exporter_configs(
        {"LANGSMITH_API_KEY": "k", "LANGSMITH_ENDPOINT": "https://eu.api.smith.langchain.com/"}
    )

    assert configs[0][0] == "https://eu.api.smith.langchain.com/otel/v1/traces"
