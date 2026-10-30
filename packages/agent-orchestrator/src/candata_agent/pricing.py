"""Token pricing for the per-sub-agent cost estimate (CAN-25).

Kept apart from ``tracing`` so it imports without OpenTelemetry installed.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TokenPricing:
    """USD per million tokens, used to put a cost estimate on each sub-agent span."""

    input_per_million: float
    output_per_million: float

    def cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        return (
            prompt_tokens * self.input_per_million + completion_tokens * self.output_per_million
        ) / 1_000_000
