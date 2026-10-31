# Task Activities: CAN-21 Edge Cases Resolution (PR #34)

**Feature Branch:** `feat/CAN-21-langgraph-agent-state`  
**Linear Task:** `CAN-21` (`BEN-16`)  
**Target Pull Request:** [PR #34](https://github.com/neobenjax/Canadian-Open-Data-Agentic-Platform/pull/34)  
**Lead Solutions Architect:** Benjamin Sanchez Zebadua (`neobenjax`)  
**Reviewer:** Samir Ibrahim (`samiromer2`)

---

## Activities Checklist

- [x] **Activity 21.1: Eliminate Hand-Written Deserialization & Bogus Defaults**
  - [x] Replace `_rebuild_citation` in `packages/agent-orchestrator/src/candata_agent/checkpoint.py` with Pydantic v2 `TypeAdapter[list[CitationEnvelope]]` (Guardrail 6).
  - [x] Eliminate `""` and `"Statistics Canada"` fallback defaults that risk creating unverified citations.
  - [x] Use native `AgentState.model_validate()` with custom type decoding.

- [x] **Activity 21.2: Protect Mutable State Dictionaries**
  - [x] Deepcopy mutable state dictionaries (`scratchpad`, `tool_args`, `details`) on `aput` (`model_copy(deep=True)`) so that in-place mutations in graph nodes cannot mutate previously saved checkpoint snapshots.

- [x] **Activity 21.3: Deterministic `writes_sort_key` Ordering**
  - [x] Sort pending writes explicitly by `task_path ASC, task_id ASC, idx ASC` when fetching from `checkpoint_writes` in `aget_tuple` matching LangGraph specification.

- [x] **Activity 21.4: Non-Negative Validation on TokenBudget**
  - [x] Enforce `Field(ge=0)` on `prompt_tokens_used`, `completion_tokens_used`, and `total_tokens_used` in `TokenBudget`.
  - [x] Enforce `Field(ge=1)` on `max_budget`.

- [x] **Activity 21.5: Verification & Pre-Flight**
  - [x] Unit test: Assert mutating `scratchpad` after `aput` does not alter stored checkpoint.
  - [x] Unit test: Verify `TypeAdapter[CitationEnvelope]` strict deserialization without bogus defaults.
  - [x] Unit test: Verify `TokenBudget` validation and synchronized totals.
  - [x] Run full pre-flight verification: `python scripts/verify.py` (226 passed, 3 deselected).
