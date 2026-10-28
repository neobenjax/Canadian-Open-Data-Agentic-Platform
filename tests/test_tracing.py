"""Tests for CAN-25 OpenTelemetry tracing of LangGraph sub-agent nodes."""

from __future__ import annotations

from typing import Any

import pytest
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from candata_agent.state import AgentState, TokenBudget, TraceContext
from candata_agent.tracing import (
    LANGSMITH_ENDPOINT,
    TokenPricing,
    _exporter_configs,  # pyright: ignore[reportPrivateUsage]
    setup_tracing,
    traced_node,
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


async def test_update_gains_trace_context_of_the_node_span(
    provider: TracerProvider, exporter: InMemorySpanExporter, state: AgentState
) -> None:
    @traced_node("data_analyst", tracer_provider=provider)
    async def analyst(state: AgentState) -> dict[str, Any]:
        return {"scratchpad": {"rows": 3}}

    update = await analyst(state)

    span = _only_span(exporter)
    context = update["trace_context"]
    assert isinstance(context, TraceContext)
    assert update["scratchpad"] == {"rows": 3}
    assert span.context is not None
    assert context.span_id == format(span.context.span_id, "016x")
    assert context.traceparent is not None
    version, trace_id, span_id, flags = context.traceparent.split("-")
    assert (version, trace_id, span_id) == (
        "00",
        format(span.context.trace_id, "032x"),
        format(span.context.span_id, "016x"),
    )
    assert int(flags, 16) & 1  # sampled


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
        (LANGSMITH_ENDPOINT, {"x-api-key": "ls-key", "Langsmith-Project": "candata-dev"}),
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
