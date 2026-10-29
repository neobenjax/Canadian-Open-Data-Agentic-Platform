"""OpenTelemetry tracing for LangGraph sub-agent nodes (CAN-25).

``traced_run`` opens one root span per graph invocation and ``traced_node`` wraps each node in a
child span, recording step latency and token usage per sub-agent. ``setup_tracing`` configures
OTLP/HTTP export to Arize Phoenix and LangSmith. Each backend is enabled only when its
environment variable is set, so tests and CI never touch a network.

Spans are parented through OpenTelemetry's own context, not through ``AgentState``, so a
checkpointed ``trace_context`` from an earlier question can never attach a new run to an old
trace, and tracing never adds a write to a graph channel.

Importing this module needs ``opentelemetry-api`` from the optional ``tracing`` extra, which
also carries the SDK and exporter (imported inside ``setup_tracing``). Without it,
``candata_agent`` falls back to no-op versions of these functions (see ``_tracing_off``).
"""

from __future__ import annotations

import functools
import os
import time
from collections.abc import Awaitable, Callable, Mapping
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import unquote

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.trace import TracerProvider
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from pydantic import BaseModel

from candata_agent.pricing import TokenPricing
from candata_agent.state import TokenBudget, TraceContext

__all__ = [
    "TokenPricing",
    "current_trace_context",
    "setup_tracing",
    "traced_node",
    "traced_run",
]

TRACER_NAME = "candata_agent"
DEFAULT_PHOENIX_ENDPOINT = "http://localhost:6006/v1/traces"
LANGSMITH_API_URL = "https://api.smith.langchain.com"
LANGSMITH_TRACES_PATH = "/otel/v1/traces"
RUN_SPAN_NAME = "graph.run"
_ID_KEYS = ("run_id", "thread_id", "session_id")

Node = Callable[..., Awaitable[Any]]


class Invokable(Protocol):
    """The part of a compiled LangGraph graph that ``traced_run`` uses."""

    async def ainvoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any: ...


@dataclass(slots=True)
class _RunTotals:
    """What the nodes of one ``traced_run`` added: summed onto the ``graph.run`` root span."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float | None = None  # stays None until a node with pricing reports


_RUN_TOTALS: ContextVar[_RunTotals | None] = ContextVar("candata_run_totals", default=None)


async def traced_run(
    app: Invokable,
    input: Any,
    config: Any = None,
    *,
    name: str = RUN_SPAN_NAME,
    continue_from: TraceContext | None = None,
    tracer_provider: TracerProvider | None = None,
    **kwargs: Any,
) -> Any:
    """Invoke a compiled graph inside a ``graph.run`` root span: one invocation, one trace.

    The nodes' ``agent.*`` spans become its children, and the root span gives the run its
    end-to-end latency. ``input.trace_context`` is replaced with the new root's context, so a
    checkpoint can be tied back to its trace and a stale context from an earlier question on the
    same thread is dropped. Pass ``continue_from`` (a stored ``TraceContext``) to resume the
    original trace instead, for example when replaying a checkpoint.

    The root span also records ``candata.latency_ms`` (even when the run raises) and the tokens
    and cost the run's nodes added: ``gen_ai.usage.input_tokens``, ``output_tokens`` and
    ``total_tokens``, plus ``candata.cost_usd`` once a node with pricing has reported. These are
    the sum of the nodes' own deltas, not the final ``token_budget``, because a checkpointed
    budget is cumulative over the thread and would count earlier questions again.
    """
    tracer = (tracer_provider or trace.get_tracer_provider()).get_tracer(TRACER_NAME)
    with tracer.start_as_current_span(name, context=_parent_context(continue_from)) as span:
        for key in _ID_KEYS:
            value = _read(input, key)
            if isinstance(value, str):
                span.set_attribute(f"candata.{key}", value)
        thread_id = _configured_thread_id(config)
        if thread_id is not None:
            span.set_attribute("candata.thread_id", thread_id)

        totals = _RunTotals()
        reset_token = _RUN_TOTALS.set(totals)
        started = time.perf_counter()
        try:
            return await app.ainvoke(
                _with_trace_context(input, current_trace_context()), config, **kwargs
            )
        finally:
            _RUN_TOTALS.reset(reset_token)
            span.set_attribute("candata.latency_ms", (time.perf_counter() - started) * 1000)
            _set_token_attributes(span, totals.prompt_tokens, totals.completion_tokens)
            if totals.cost_usd is not None:
                span.set_attribute("candata.cost_usd", totals.cost_usd)


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

    The span is a child of whichever span is active, normally the ``graph.run`` root from
    ``traced_run``; without one it is a trace root of its own. The node's update is returned
    exactly as the node produced it, ``None`` included: the decorator never writes a state
    channel, so nodes running in the same step cannot conflict on it.
    """

    def decorate(node: Node) -> Node:
        @functools.wraps(node)
        async def wrapper(state: object, *args: Any, **kwargs: Any) -> Any:
            tracer = (tracer_provider or trace.get_tracer_provider()).get_tracer(TRACER_NAME)
            with tracer.start_as_current_span(f"agent.{agent}") as span:
                span.set_attribute("candata.agent", agent)
                for key in _ID_KEYS:
                    value = _read(state, key)
                    if isinstance(value, str):
                        span.set_attribute(f"candata.{key}", value)

                started = time.perf_counter()
                try:
                    # The span context manager records the exception and sets ERROR status.
                    update = await node(state, *args, **kwargs)
                finally:
                    span.set_attribute("candata.latency_ms", (time.perf_counter() - started) * 1000)

                if update is not None:
                    _record_tokens(span, state, update, pricing)
                return update

        return wrapper

    return decorate


def _parent_context(carried: object) -> Context | None:
    """The OTel context for a stored ``TraceContext``, or ``None`` if it carries no trace."""
    if not isinstance(carried, TraceContext) or not carried.traceparent:
        return None
    carrier = {"traceparent": carried.traceparent}
    if carried.tracestate:
        carrier["tracestate"] = carried.tracestate
    return TraceContextTextMapPropagator().extract(carrier)


def _with_trace_context(input: object, context: TraceContext) -> Any:
    if isinstance(input, Mapping):
        return {**input, "trace_context": context}  # pyright: ignore[reportUnknownVariableType]
    if isinstance(input, BaseModel) and "trace_context" in type(input).model_fields:
        return input.model_copy(update={"trace_context": context})
    return input


def _configured_thread_id(config: object) -> str | None:
    if not isinstance(config, Mapping):
        return None
    configurable = config.get("configurable")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    if not isinstance(configurable, Mapping):
        return None
    thread_id = configurable.get("thread_id")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    return thread_id if isinstance(thread_id, str) else None


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
    - Any other OTLP/HTTP backend: ``OTEL_EXPORTER_OTLP_ENDPOINT`` (or
      ``OTEL_EXPORTER_OTLP_TRACES_ENDPOINT``) and ``OTEL_EXPORTER_OTLP_HEADERS``. These are the
      fallback and apply only when neither Phoenix nor LangSmith is configured.
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
    if not configs:
        generic = _generic_otlp_config(env)
        if generic is not None:
            configs.append(generic)
    return configs


def _generic_otlp_config(env: Mapping[str, str]) -> tuple[str, dict[str, str]] | None:
    """The vendor-neutral OTLP settings, used when no Phoenix or LangSmith variable is set.

    ``OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`` is a full URL; ``OTEL_EXPORTER_OTLP_ENDPOINT`` is a
    base URL that gets ``/v1/traces`` appended, as the OTLP/HTTP spec says. Headers come from
    ``OTEL_EXPORTER_OTLP_TRACES_HEADERS`` or ``OTEL_EXPORTER_OTLP_HEADERS`` (``k=v,k2=v2``).
    """
    endpoint = env.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
    if not endpoint:
        base = env.get("OTEL_EXPORTER_OTLP_ENDPOINT")
        if not base:
            return None
        endpoint = base.rstrip("/") + "/v1/traces"
    raw = env.get("OTEL_EXPORTER_OTLP_TRACES_HEADERS") or env.get("OTEL_EXPORTER_OTLP_HEADERS", "")
    headers: dict[str, str] = {}
    for pair in raw.split(","):
        name, separator, value = pair.partition("=")
        if separator and name.strip():
            headers[name.strip()] = unquote(value.strip())
    return endpoint, headers


def _set_token_attributes(span: trace.Span, prompt: int, completion: int) -> None:
    span.set_attribute("gen_ai.usage.input_tokens", prompt)
    span.set_attribute("gen_ai.usage.output_tokens", completion)
    span.set_attribute("gen_ai.usage.total_tokens", prompt + completion)


def _record_tokens(
    span: trace.Span, state: object, update: object, pricing: TokenPricing | None
) -> None:
    after = _read(update, "token_budget")
    if not isinstance(after, TokenBudget):
        return
    before = _read(state, "token_budget")
    base = before if isinstance(before, TokenBudget) else TokenBudget()
    # A budget that goes down (a branch or merge resetting it) must not report negative usage.
    prompt = max(0, after.prompt_tokens_used - base.prompt_tokens_used)
    completion = max(0, after.completion_tokens_used - base.completion_tokens_used)
    _set_token_attributes(span, prompt, completion)
    span.set_attribute("candata.tokens_remaining", after.remaining_tokens)
    cost = pricing.cost(prompt, completion) if pricing is not None else None
    if cost is not None:
        span.set_attribute("candata.cost_usd", cost)
    totals = _RUN_TOTALS.get()
    if totals is not None:
        totals.prompt_tokens += prompt
        totals.completion_tokens += completion
        if cost is not None:
            totals.cost_usd = (totals.cost_usd or 0.0) + cost


def _read(state: object, key: str) -> object:
    if isinstance(state, Mapping):
        return state.get(key)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    return getattr(state, key, None)
