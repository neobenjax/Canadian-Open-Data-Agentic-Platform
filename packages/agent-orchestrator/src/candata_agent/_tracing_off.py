"""No-op stand-ins for ``candata_agent.tracing`` when OpenTelemetry is not installed.

``opentelemetry-api`` ships in the optional ``tracing`` extra so that the standalone MCP server,
which has no use for it, installs without it. A graph built without the extra still runs: nodes
decorated with ``traced_node`` are returned unchanged and ``traced_run`` just awaits ``ainvoke``.
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from candata_agent.state import TraceContext

Node = Callable[..., Awaitable[Any]]
_BACKEND_VARIABLES = (
    "PHOENIX_COLLECTOR_ENDPOINT",
    "LANGSMITH_API_KEY",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
)


async def traced_run(
    app: Any,
    input: Any,
    config: Any = None,
    *,
    name: str = "graph.run",
    continue_from: TraceContext | None = None,
    tracer_provider: object | None = None,
    **kwargs: Any,
) -> Any:
    return await app.ainvoke(input, config, **kwargs)


def traced_node(
    agent: str,
    *,
    pricing: object | None = None,
    tracer_provider: object | None = None,
) -> Callable[[Node], Node]:
    def decorate(node: Node) -> Node:
        return node

    return decorate


def current_trace_context() -> TraceContext:
    return TraceContext()


def setup_tracing(
    env: Mapping[str, str] | None = None,
    *,
    service_name: str = "candata-agent",
    set_global: bool = True,
) -> None:
    """Return ``None`` as the real function does for an empty environment.

    A configured backend with no OpenTelemetry installed is an error rather than a silent
    no-op, so a missing extra is noticed instead of producing an empty dashboard.
    """
    env = os.environ if env is None else env
    if any(env.get(name) for name in _BACKEND_VARIABLES):
        raise ImportError(
            "Tracing is configured but OpenTelemetry is not installed. "
            "Install it with: pip install 'candata-mcp[tracing]'"
        )
    return None
