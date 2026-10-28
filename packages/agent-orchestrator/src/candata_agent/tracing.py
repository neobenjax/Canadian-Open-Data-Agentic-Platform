"""OpenTelemetry tracing for LangGraph sub-agent nodes (CAN-25).

``traced_node`` wraps an async node in one span per run, recording step latency and token
usage per sub-agent, and writes the span context back into ``AgentState.trace_context``.
``setup_tracing`` configures OTLP/HTTP export to Arize Phoenix and LangSmith. Each backend
is enabled only when its environment variable is set, so tests and CI never touch a network.

Only ``opentelemetry-api`` is needed to import this module. The SDK and exporter live in the
optional ``tracing`` extra and are imported inside ``setup_tracing``.
"""

from __future__ import annotations

import functools
import os
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.trace import TracerProvider
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from candata_agent.state import TokenBudget, TraceContext

TRACER_NAME = "candata_agent"
DEFAULT_PHOENIX_ENDPOINT = "http://localhost:6006/v1/traces"
LANGSMITH_API_URL = "https://api.smith.langchain.com"
LANGSMITH_TRACES_PATH = "/otel/v1/traces"

NodeUpdate = dict[str, Any]
Node = Callable[..., Awaitable[NodeUpdate]]


@dataclass(frozen=True, slots=True)
class TokenPricing:
    """USD per million tokens, used to put a cost estimate on each sub-agent span."""

    input_per_million: float
    output_per_million: float

    def cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        return (
            prompt_tokens * self.input_per_million + completion_tokens * self.output_per_million
        ) / 1_000_000


def traced_node(
    agent: str,
    *,
    pricing: TokenPricing | None = None,
    tracer_provider: TracerProvider | None = None,
) -> Callable[[Node], Node]:
    """Wrap a LangGraph node so every run emits an ``agent.<agent>`` span.

    The span carries the run and thread IDs, latency in milliseconds and, when the node's
    update holds a ``token_budget``, the tokens it added over the incoming state. Exceptions
    are recorded and re-raised.

    One graph run is one trace. The first traced node starts the trace and writes its context
    into ``trace_context``; later nodes read that field and become its children, so a run shows
    up in Phoenix or LangSmith as a single tree. A node that sets its own ``trace_context``
    keeps it.
    """

    def decorate(node: Node) -> Node:
        @functools.wraps(node)
        async def wrapper(state: object, *args: Any, **kwargs: Any) -> NodeUpdate:
            tracer = (tracer_provider or trace.get_tracer_provider()).get_tracer(TRACER_NAME)
            incoming = _read(state, "trace_context")
            parent = _parent_context(incoming)
            with tracer.start_as_current_span(f"agent.{agent}", context=parent) as span:
                span.set_attribute("candata.agent", agent)
                for key in ("run_id", "thread_id", "session_id"):
                    value = _read(state, key)
                    if isinstance(value, str):
                        span.set_attribute(f"candata.{key}", value)

                started = time.perf_counter()
                try:
                    # The span context manager records the exception and sets ERROR status.
                    update = await node(state, *args, **kwargs)
                finally:
                    span.set_attribute("candata.latency_ms", (time.perf_counter() - started) * 1000)

                _record_tokens(span, state, update, pricing)
                if parent is None and "trace_context" not in update:
                    update = {**update, "trace_context": current_trace_context()}
                return update

        return wrapper

    return decorate


def _parent_context(carried: object) -> Context | None:
    """The span context a previous node stored in ``AgentState.trace_context``, if any."""
    if not isinstance(carried, TraceContext) or not carried.traceparent:
        return None
    carrier = {"traceparent": carried.traceparent}
    if carried.tracestate:
        carrier["tracestate"] = carried.tracestate
    return TraceContextTextMapPropagator().extract(carrier)


def current_trace_context() -> TraceContext:
    """Snapshot the active span as a W3C ``traceparent`` for ``AgentState.trace_context``."""
    carrier: dict[str, str] = {}
    TraceContextTextMapPropagator().inject(carrier)
    span_context = trace.get_current_span().get_span_context()
    if not span_context.is_valid:
        return TraceContext()
    return TraceContext(
        traceparent=carrier.get("traceparent"),
        tracestate=carrier.get("tracestate"),
        span_id=format(span_context.span_id, "016x"),
    )


def setup_tracing(
    env: Mapping[str, str] | None = None,
    *,
    service_name: str = "candata-agent",
    set_global: bool = True,
) -> TracerProvider | None:
    """Configure OTLP export from the environment. Returns ``None`` when no backend is set.

    - Phoenix: ``PHOENIX_COLLECTOR_ENDPOINT`` (full traces URL; ``http://localhost:6006/v1/traces``
      is the local default), optional ``PHOENIX_API_KEY`` and ``PHOENIX_PROJECT_NAME``.
    - LangSmith: ``LANGSMITH_API_KEY``, optional ``LANGSMITH_PROJECT``, and ``LANGSMITH_ENDPOINT``
      for the EU region (``https://eu.api.smith.langchain.com``) or a self-hosted base URL.
    """
    env = os.environ if env is None else env
    exporters = _exporter_configs(env)
    if not exporters:
        return None

    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider as SdkTracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    project = env.get("PHOENIX_PROJECT_NAME") or env.get("LANGSMITH_PROJECT") or "candata"
    provider = SdkTracerProvider(
        resource=Resource.create(
            {"service.name": service_name, "openinference.project.name": project}
        )
    )
    for endpoint, headers in exporters:
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, headers=headers))
        )
    if set_global:
        trace.set_tracer_provider(provider)
    return provider


def _exporter_configs(env: Mapping[str, str]) -> list[tuple[str, dict[str, str]]]:
    configs: list[tuple[str, dict[str, str]]] = []
    phoenix = env.get("PHOENIX_COLLECTOR_ENDPOINT")
    if phoenix:
        headers = (
            {"authorization": f"Bearer {env['PHOENIX_API_KEY']}"}
            if env.get("PHOENIX_API_KEY")
            else {}
        )
        configs.append((phoenix, headers))
    langsmith_key = env.get("LANGSMITH_API_KEY")
    if langsmith_key:
        headers = {"x-api-key": langsmith_key}
        if env.get("LANGSMITH_PROJECT"):
            headers["Langsmith-Project"] = env["LANGSMITH_PROJECT"]
        base = env.get("LANGSMITH_ENDPOINT") or LANGSMITH_API_URL
        configs.append((base.rstrip("/") + LANGSMITH_TRACES_PATH, headers))
    return configs


def _record_tokens(
    span: trace.Span, state: object, update: NodeUpdate, pricing: TokenPricing | None
) -> None:
    after = update.get("token_budget")
    if not isinstance(after, TokenBudget):
        return
    before = _read(state, "token_budget")
    base = before if isinstance(before, TokenBudget) else TokenBudget()
    prompt = after.prompt_tokens_used - base.prompt_tokens_used
    completion = after.completion_tokens_used - base.completion_tokens_used
    span.set_attribute("gen_ai.usage.input_tokens", prompt)
    span.set_attribute("gen_ai.usage.output_tokens", completion)
    span.set_attribute("candata.tokens_remaining", after.remaining_tokens)
    if pricing is not None:
        span.set_attribute("candata.cost_usd", pricing.cost(prompt, completion))


def _read(state: object, key: str) -> object:
    if isinstance(state, Mapping):
        return state.get(key)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    return getattr(state, key, None)
