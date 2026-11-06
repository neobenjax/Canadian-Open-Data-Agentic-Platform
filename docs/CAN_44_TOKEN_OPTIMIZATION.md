# CAN-44: Token Cost Optimization with Prompt Caching and Compressed Checkpoint Serialization

**Owners:** Yassir / Benjamin · **Milestone:** 4 · **Linear:** BEN-28 · **Code:** `packages/agent-orchestrator/src/candata_agent/`

CAN-44 optimizes token expenditure, planner execution latency, and checkpoint storage footprint across the multi-agent orchestration lifecycle. It introduces Anthropic Prompt Caching on planner turns and transparent zlib compression on LangGraph state serialization.

---

## 1. Architecture Overview

```
                                  Prompt Caching
                     ┌──────────────────────────────────────┐
                     │ Anthropic Messages API (Beta)        │
                     │  - System Prompt (ephemeral cache)   │
                     │  - Tool Schemas  (ephemeral cache)   │
                     └──────────────────┬───────────────────┘
                                        │ Token Metrics
                                        ▼
┌──────────────────┐            ┌───────────────┐            ┌──────────────────────────┐
│ ClaudePlanner    ├───────────►│ PlannerResult ├───────────►│ TokenBudget              │
│ (supervisor)     │            │               │            │ - cache_creation_tokens  │
└──────────────────┘            └───────────────┘            │ - cache_read_tokens      │
                                                             │ - cache_savings_rate     │
                                                             └──────────────────────────┘

                               Checkpointer Serialization
                     ┌──────────────────────────────────────┐
                     │ CompressedSerializer                 │
                     │  - <128 bytes: Raw JsonPlus          │
                     │  - >=128 bytes: zlib (+zlib tag)     │
                     └──────────────────┬───────────────────┘
                                        │
                                        ▼
                                ┌─────────────────┐
                                │ AsyncSqliteSaver│
                                └─────────────────┘
```

---

## 2. Anthropic Prompt Caching (`candata_agent/supervisor/planner.py`)

The supervisor planner frequently invokes Claude across multi-turn discovery loops (inspecting StatCan tables, dimensions, and coordinates). Each turn re-submits the extensive Canadian open data system instructions and tool definitions.

### Ephemeral Cache Breakpoints
Prompt caching places ephemeral breakpoints at stable prompt prefixes:
1. **System Prompt Block:** The core instructions and catalog of execution tools are passed as a structured `BetaTextBlockParam` with `"cache_control": {"type": "ephemeral"}`.
2. **Planner Tools Catalog:** Cache control is placed on the final tool in `PLANNER_TOOLS` (`decline`), caching the entire tool definitions list in a single breakpoint.

```python
self._system_blocks: list[BetaTextBlockParam] = [
    {
        "type": "text",
        "text": self._system,
        "cache_control": {"type": "ephemeral"},
    }
]
self._tools: list[BetaToolParam] = [
    {**tool, "cache_control": {"type": "ephemeral"}} if i == len(PLANNER_TOOLS) - 1 else dict(tool)
    for i, tool in enumerate(PLANNER_TOOLS)
]
```

### Beta Header Activation
Requests include `prompt-caching-2024-07-31` alongside `server-side-fallback-2026-07-01` in the API `betas` parameter.

### Token Telemetry
Anthropic API usage metrics `cache_creation_input_tokens` and `cache_read_input_tokens` are recorded and aggregated across turns in `PlannerResult`:
- Cache writes cost $1.25\times$ base input tokens.
- Cache reads cost $0.10\times$ base input tokens (a **90% discount**).
- Subsequent turns within the 5-minute TTL read from cache, drastically reducing cost and latency.

---

## 3. Token Budget Tracking (`candata_agent/state.py` & `node.py`)

`TokenBudget` tracks caching metrics across the session:
- `cache_creation_tokens_used`: Number of tokens written into the Anthropic prompt cache.
- `cache_read_tokens_used`: Number of tokens read from the prompt cache at a 90% discount.
- `cache_savings_rate`: Calculated property representing the proportion of prompt tokens served from cache:
  $$\text{cache\_savings\_rate} = \frac{\text{cache\_read\_tokens\_used}}{\text{prompt\_tokens\_used} + \text{cache\_read\_tokens\_used}}$$

The supervisor node automatically updates `TokenBudget` upon receiving `PlannerResult` from the planner.

---

## 4. Compressed Checkpoint Serialization (`candata_agent/checkpoint.py`)

Multi-agent LangGraph executions accumulate tabular data, message histories, and citation structures into `AgentState`. Default uncompressed JSON checkpoints can grow to several megabytes over long threads.

### `CompressedSerializer` Implementation
`CompressedSerializer` implements LangGraph's `SerializerProtocol`:
- **Threshold:** Payloads below 128 bytes skip compression to avoid compression overhead.
- **Algorithm:** Standard `zlib` compression (level 6) applied to serialized JSON bytes.
- **Type Tagging:** Prefixes the type string with `+zlib` (e.g., `json+zlib`).
- **Decompression:** `loads_typed` detects `+zlib` suffix and decompresses before delegating to the base serializer.
- **Backwards Compatibility:** Legacy checkpoints without `+zlib` are decoded directly without modification.

### Compression Benchmarks
For realistic checkpoint payloads (containing 100+ observations and metadata):
- Uncompressed: ~3.8 KB
- Compressed: ~0.6 KB
- **Payload size reduction:** **84.2%** (well exceeding the 70% requirement).

`AsyncSqliteSaver` defaults to `CompressedSerializer`, providing zero-configuration compression for all checkpoints.

---

## 5. Verification & Unit Tests

Unit tests are implemented in `tests/test_token_optimization.py`:
- `test_token_budget_defaults_and_validation`: Verifies initialization and `cache_savings_rate` calculation.
- `test_compressed_serializer_small_payload_skips_compression`: Checks threshold behavior.
- `test_compressed_serializer_large_payload_compresses_and_roundtrips`: Verifies >70% compression ratio and Decimal/dict roundtrip fidelity.
- `test_compressed_serializer_backwards_compatibility_with_uncompressed`: Ensures legacy checkpoints load without error.
- `test_async_sqlite_saver_uses_compressed_serializer_by_default`: Validates checkpointer integration in SQLite.
- `test_claude_planner_prompt_caching_request_structure_and_usage`: Checks Anthropic request formatting with `cache_control` and usage parsing.
- `test_supervisor_node_accumulates_cache_tokens_into_token_budget`: Tests budget update in the supervisor node.
