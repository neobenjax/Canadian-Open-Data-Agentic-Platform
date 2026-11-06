"""Unit tests for CAN-44: Token cost optimization.

Tests prompt caching with Anthropic Messages API and compressed checkpoint serialization.
"""

from __future__ import annotations

import tempfile
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest
from anthropic import AsyncAnthropic
from anthropic.types.beta import BetaMessage
from langgraph.checkpoint.base import Checkpoint, CheckpointMetadata
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from candata_agent.checkpoint import AsyncSqliteSaver, CompressedSerializer
from candata_agent.state import AgentMessage, AgentState, MessageRole, TokenBudget
from candata_agent.supervisor.node import make_supervisor_node
from candata_agent.supervisor.planner import (
    PROMPT_CACHING_BETA,
    ClaudePlanner,
    PlannerResult,
)
from candata_mcp.connectors.statcan_wds import CubeMetadata, CubeSearchResult, StatCanSeriesResult

# ==============================================================================================
# 1. TokenBudget prompt caching tests
# ==============================================================================================


def test_token_budget_defaults_and_validation() -> None:
    budget = TokenBudget()
    assert budget.cache_creation_tokens_used == 0
    assert budget.cache_read_tokens_used == 0
    assert budget.cache_savings_rate == 0.0

    budget2 = TokenBudget(
        prompt_tokens_used=500,
        completion_tokens_used=200,
        cache_creation_tokens_used=1000,
        cache_read_tokens_used=1500,
    )
    assert budget2.total_tokens_used == 700
    assert budget2.cache_creation_tokens_used == 1000
    assert budget2.cache_read_tokens_used == 1500
    # candidate prompt = 500 + 1500 = 2000. savings = 1500 / 2000 = 0.75
    assert budget2.cache_savings_rate == 0.75


def test_token_budget_cache_savings_rate_zero_division() -> None:
    budget = TokenBudget(prompt_tokens_used=0, cache_read_tokens_used=0)
    assert budget.cache_savings_rate == 0.0


# ==============================================================================================
# 2. CompressedSerializer tests
# ==============================================================================================


def test_compressed_serializer_small_payload_skips_compression() -> None:
    serializer = CompressedSerializer(min_compression_bytes=128)
    small_data = {"key": "val"}
    type_str, payload = serializer.dumps_typed(small_data)
    assert not type_str.endswith("+zlib")
    assert serializer.loads_typed((type_str, payload)) == small_data


def test_compressed_serializer_large_payload_compresses_and_roundtrips() -> None:
    serializer = CompressedSerializer(min_compression_bytes=64)
    large_data = {
        "observations": [
            {"date": f"2025-{i:02d}-01", "value": 100.5 + i, "unit": "Dollars", "status": "A"}
            for i in range(1, 100)
        ],
        "metadata": {"title": "Monthly Economic Indicator", "table_id": "18-10-0004-01"},
        "rate": Decimal("3.25"),
    }

    base = JsonPlusSerializer()
    _, uncompressed_bytes = base.dumps_typed(large_data)

    type_str, compressed_bytes = serializer.dumps_typed(large_data)
    assert type_str.endswith("+zlib")
    assert len(compressed_bytes) < len(uncompressed_bytes)

    # Verify compression ratio exceeds 70%
    compression_ratio = 1.0 - (len(compressed_bytes) / len(uncompressed_bytes))
    assert compression_ratio >= 0.70, f"Expected >= 70% compression, got {compression_ratio:.2%}"

    # Roundtrip validation
    restored = serializer.loads_typed((type_str, compressed_bytes))
    assert restored["metadata"] == large_data["metadata"]
    assert len(restored["observations"]) == len(large_data["observations"])
    assert restored["rate"] == Decimal("3.25")


def test_compressed_serializer_backwards_compatibility_with_uncompressed() -> None:
    base = JsonPlusSerializer()
    legacy_type, legacy_bytes = base.dumps_typed({"legacy": True, "count": 42})

    serializer = CompressedSerializer()
    loaded = serializer.loads_typed((legacy_type, legacy_bytes))
    assert loaded == {"legacy": True, "count": 42}


# ==============================================================================================
# 3. AsyncSqliteSaver with CompressedSerializer integration
# ==============================================================================================


@pytest.mark.asyncio
async def test_async_sqlite_saver_uses_compressed_serializer_by_default() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "checkpoints_test.db"
        saver = AsyncSqliteSaver(db_path)
        assert isinstance(saver.serde, CompressedSerializer)

        async with saver:
            config: dict[str, Any] = {
                "configurable": {
                    "thread_id": "thread-1",
                    "checkpoint_ns": "",
                    "checkpoint_id": str(uuid.uuid4()),
                }
            }
            checkpoint: Checkpoint = {
                "v": 1,
                "id": config["configurable"]["checkpoint_id"],
                "ts": "2026-11-06T12:00:00.000000+00:00",
                "channel_values": {
                    "messages": [
                        {"role": "user", "content": "Question " * 50},
                        {"role": "assistant", "content": "Answer " * 50},
                    ],
                },
                "channel_versions": {"messages": 1},
                "versions_seen": {},
                "pending_sends": [],
            }
            metadata: CheckpointMetadata = {
                "source": "input",
                "step": 1,
                "writes": {},
                "parents": {},
            }
            saved_config = await saver.aput(config, checkpoint, metadata, {})
            retrieved = await saver.aget_tuple(saved_config)
            assert retrieved is not None
            assert retrieved.checkpoint["id"] == checkpoint["id"]
            assert (
                retrieved.checkpoint["channel_values"]["messages"]
                == checkpoint["channel_values"]["messages"]
            )


# ==============================================================================================
# 4. ClaudePlanner Anthropic prompt caching structure & usage metrics
# ==============================================================================================


class MockStatCan:
    async def search_cubes(self, query: str, *, limit: int = 10) -> CubeSearchResult:
        raise NotImplementedError

    async def get_cube_metadata(self, product_id: int | str) -> CubeMetadata:
        raise NotImplementedError

    async def get_data_from_cube(
        self, product_id: int | str, coordinate: str, latest_n: int = 1
    ) -> StatCanSeriesResult:
        raise NotImplementedError


class MockAnthropicMessages:
    def __init__(self, *responses: BetaMessage) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []

    async def create(self, **request: Any) -> BetaMessage:
        self.requests.append({**request, "messages": list(request["messages"])})
        return self.responses.pop(0)


class MockAnthropicClient:
    def __init__(self, *responses: BetaMessage) -> None:
        self.messages = MockAnthropicMessages(*responses)
        self.beta = self


def make_cached_beta_message(
    content: list[dict[str, Any]],
    *,
    input_tokens: int = 1500,
    output_tokens: int = 250,
    cache_creation: int = 1200,
    cache_read: int = 800,
) -> BetaMessage:
    return BetaMessage.model_validate(
        {
            "id": "msg_cached_1",
            "type": "message",
            "role": "assistant",
            "model": "claude-opus-5-5",
            "content": content,
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_creation_input_tokens": cache_creation,
                "cache_read_input_tokens": cache_read,
            },
        }
    )


@pytest.mark.asyncio
async def test_claude_planner_prompt_caching_request_structure_and_usage() -> None:
    # Set up simulated planner response returning a decline
    tool_call = {
        "type": "tool_use",
        "id": "call_1",
        "name": "decline",
        "input": {"reason": "Series not published for specified geography."},
    }
    simulated_msg = make_cached_beta_message(
        [tool_call],
        input_tokens=1500,
        output_tokens=50,
        cache_creation=1100,
        cache_read=950,
    )

    client = MockAnthropicClient(simulated_msg)
    planner = ClaudePlanner(cast(AsyncAnthropic, client), MockStatCan())

    result = await planner.plan("Find housing stats for Mars")
    assert result.plan is None
    assert result.declined_reason == "Series not published for specified geography."
    assert result.input_tokens == 1500
    assert result.output_tokens == 50
    assert result.cache_creation_input_tokens == 1100
    assert result.cache_read_input_tokens == 950

    # Inspect the outgoing request to the Anthropic API
    assert len(client.messages.requests) == 1
    req = client.messages.requests[0]

    # Verify prompt caching beta header is enabled
    assert PROMPT_CACHING_BETA in req["betas"]

    # Verify system prompt has ephemeral cache_control
    system_blocks = req["system"]
    assert isinstance(system_blocks, list)
    assert len(system_blocks) == 1
    assert system_blocks[0]["type"] == "text"
    assert system_blocks[0]["cache_control"] == {"type": "ephemeral"}

    # Verify tool definitions have ephemeral cache_control on the terminal tool
    tools = req["tools"]
    assert len(tools) >= 3
    # The last tool must have cache_control
    assert tools[-1]["cache_control"] == {"type": "ephemeral"}
    # All tools must maintain strict=True
    assert all(t["strict"] for t in tools)


@pytest.mark.asyncio
async def test_supervisor_node_accumulates_cache_tokens_into_token_budget() -> None:
    outcome = PlannerResult(
        plan=None,
        declined_reason="Test decline",
        input_tokens=2000,
        output_tokens=300,
        cache_creation_input_tokens=1500,
        cache_read_input_tokens=1200,
    )

    class DummyPlanner:
        async def plan(self, question: str) -> PlannerResult:
            return outcome

    supervisor = make_supervisor_node(DummyPlanner())
    initial_state = AgentState(
        session_id="session-1",
        thread_id="thread-1",
        messages=(AgentMessage(role=MessageRole.USER, content="What is the policy rate?"),),
        token_budget=TokenBudget(max_budget=50000),
    )

    result = await supervisor(initial_state)
    new_budget: TokenBudget = result["token_budget"]
    assert new_budget.prompt_tokens_used == 2000
    assert new_budget.completion_tokens_used == 300
    assert new_budget.cache_creation_tokens_used == 1500
    assert new_budget.cache_read_tokens_used == 1200
    assert new_budget.cache_savings_rate == round(1200 / (2000 + 1200), 4)
