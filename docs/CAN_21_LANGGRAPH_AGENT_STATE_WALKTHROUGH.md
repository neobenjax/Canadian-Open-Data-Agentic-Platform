# CAN-21 (BEN-16): Typed AgentState & AsyncSqliteSaver Checkpointer — Walkthrough & Verification Guide

**Issue Key:** `BEN-16` (`CAN-21`)  
**Branch:** `feat/CAN-21-langgraph-agent-state`  
**Milestone:** Milestone 2: LangGraph Multi-Agent Orchestration & Observability (Sprint 2)  
**Author:** Benjamin Sanchez Zebadua (`neobenjax`) — Solutions Architect & Lead  
**Peer Reviewer:** Samir Ibrahim (`samiromer2`) — Data Visualization & Agent Evals Lead  

---

## 1. Executive Summary & Architecture Overview

In multi-agent architectures (Supervisor, Catalog Specialist, Data Analyst, and Verifier), agents must collaborate asynchronously without losing track of:
1. What the user asked and what sub-agents have responded (`messages`).
2. The decomposed step-by-step execution roadmap (`plan`).
3. Mathematical calculations and exact SQL queries computed on local engines (`sql_artifacts`).
4. Two-Tier Citation Envelopes confirming data provenance (`citations`).
5. Human-in-the-Loop breakpoints when statistical ambiguities occur (`active_interrupt`).
6. Token budgets and distributed OpenTelemetry traces across agent nodes (`token_budget`, `trace_context`).

Furthermore, in high-stakes government and financial analytics, hallucinations or bad agent turns must never corrupt state irreversibly. **CAN-21** delivers an immutable, typed Pydantic v2 `AgentState` schema paired with an asynchronous SQLite checkpointer (`AsyncSqliteSaver`). This gives our system:
- **Zero Silent Type Drifts:** Strict validation across all channels with schema versioning (`schema_version=1`).
- **Production Durability:** SQLite in WAL mode (`PRAGMA journal_mode=WAL`) ensuring concurrent reads/writes and crash resilience.
- **Time-Travel Rewind & Conversation Forking:** The ability to roll back any conversation thread to an earlier checkpoint, inspect what happened, and branch into alternate hypothetical exploration paths (`arollback_to`).

---

## 2. Key Components & Implementation Details

### A. State Channels (`candata_agent.state`)
- **`AgentMessage` & `add_messages` Reducer:** Frozen message models supporting roles (`user`, `assistant`, `system`, `tool`), tool calls, and deterministic ID-based replacement or appending.
- **`QueryPlan` & `PlanStep`:** Supervisor planning roadmap tracking individual step lifecycle (`pending`, `in_progress`, `completed`, `failed`, `skipped`).
- **`SQLArtifact`:** Captures exact SQL queries executed in DuckDB along with resulting tabular rows and row counts, ensuring mathematical auditability.
- **`merge_citations` Reducer:** Deduplicates incoming Two-Tier Citation Envelopes by their Core Verification Tuple (`(table_id, vector_id, reference_period)`), ensuring no duplicate citations are recorded when multiple agents consult the same official table.
- **`HITLInterrupt`:** Breakpoint carrier for Human-in-the-Loop interruptions, categorizing events (`ambiguous_member`, `confidentiality_suppressed`, `policy_exception`, `user_confirmation`) with candidate choices for human operators.
- **`TokenBudget` & `TraceContext`:** Tracks token consumption (prompt, completion, total, and remaining capacity against a 128k context window) and carries W3C TraceContext headers (`traceparent`, `span_id`).

### B. Durable Checkpointer (`candata_agent.checkpoint.AsyncSqliteSaver`)
- **WAL-Mode Concurrency:** Executes `PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; PRAGMA foreign_keys=ON;` with `check_same_thread=False` and `asyncio.to_thread` for non-blocking I/O.
- **Relational Tables:**
  - `checkpoints`: Stores `(thread_id, checkpoint_id, parent_checkpoint_id, run_id, created_at, schema_version, state_json)`.
  - `checkpoint_writes`: Stores intermediate channel updates linked to checkpoints via cascading foreign keys.
- **Time-Travel Rollback API (`arollback_to`):**
  - **In-thread rewind:** Restores state to an earlier target checkpoint while preserving thread identity.
  - **Conversation forking:** Copies earlier state into a newly spawned `new_thread_id`, enabling what-if scenario branching without overwriting original history.

---

## 3. Deliverables Summary

| File Path | Description |
|:---|:---|
| [`packages/agent-orchestrator/src/candata_agent/__init__.py`](file:///d:/AI/PARTY%20PROJECTS/AI%20Engineer%20-%20Collaboration/packages/agent-orchestrator/src/candata_agent/__init__.py) | Package initialization exposing `AgentState` and `AsyncSqliteSaver`. |
| [`packages/agent-orchestrator/src/candata_agent/state.py`](file:///d:/AI/PARTY%20PROJECTS/AI%20Engineer%20-%20Collaboration/packages/agent-orchestrator/src/candata_agent/state.py) | Typed Pydantic v2 state schemas, reducers, and enums. |
| [`packages/agent-orchestrator/src/candata_agent/checkpoint.py`](file:///d:/AI/PARTY%20PROJECTS/AI%20Engineer%20-%20Collaboration/packages/agent-orchestrator/src/candata_agent/checkpoint.py) | `AsyncSqliteSaver` implementing WAL persistence, history retrieval, and time travel. |
| [`pyproject.toml`](file:///d:/AI/PARTY%20PROJECTS/AI%20Engineer%20-%20Collaboration/pyproject.toml) | Added `packages/agent-orchestrator/src` to pythonpath, ruff, and pyright strict paths. |
| [`tests/test_agent_state.py`](file:///d:/AI/PARTY%20PROJECTS/AI%20Engineer%20-%20Collaboration/tests/test_agent_state.py) | 9 unit and integration tests verifying schema validation, reducers, persistence, and rollback. |
| [`scripts/demo_agent_state_timetravel.py`](file:///d:/AI/PARTY%20PROJECTS/AI%20Engineer%20-%20Collaboration/scripts/demo_agent_state_timetravel.py) | Interactive CLI verification tool demonstrating multi-turn simulation, HITL pause, and time-travel forking. |
| [`docs/CAN_21_LANGGRAPH_AGENT_STATE_TASKS.md`](file:///d:/AI/PARTY%20PROJECTS/AI%20Engineer%20-%20Collaboration/docs/CAN_21_LANGGRAPH_AGENT_STATE_TASKS.md) | Activity task tracking file with all checkboxes completed. |

---

## 4. Verification & Testing

### 1. Automated Unit Tests
Run the CAN-21 test suite:
```bash
uv run pytest tests/test_agent_state.py -v
```
**Result:** 9 passed in 0.32s
- `test_agent_state_defaults`: Canonical field defaults and schema version validation.
- `test_agent_state_frozen_immutability`: In-place mutation protection.
- `test_token_budget_remaining`: Token tracking and non-negative capacity calculation.
- `test_add_messages_reducer`: Append and ID-based message updates.
- `test_merge_citations_reducer`: Deduplication on Core Verification Tuple.
- `test_checkpointer_persistence_roundtrip`: Complete serialization/deserialization across SQLite.
- `test_checkpointer_thread_isolation`: Cross-thread data isolation.
- `test_time_travel_rollback_and_forking`: In-thread rewind and conversation branch forking.
- `test_time_travel_keyerror_on_unknown_checkpoint`: Defensive error handling for nonexistent checkpoints.

### 2. Full Regression Suite
Run all repository tests:
```bash
uv run pytest
```
**Result:** 196 passed, 2 deselected (live API tests) in 32.5s. Zero regressions across connectors, server, engine, and benchmarks.

### 3. Pre-Flight Code Quality
Run Ruff and Pyright via unified fast verifier:
```bash
python scripts/verify.py --fast
```
**Result:**
```
==========================================================================
 🍁 CANDATA PRE-FLIGHT VERIFICATION: ALL CHECKS PASSED
==========================================================================
 ✅ [0.1s]  Ruff Linter
 ✅ [0.1s]  Ruff Formatter
 ✅ [5.3s]  Pyright Type Checker
--------------------------------------------------------------------------
✨ Codebase clean and ready for commit & PR!
```

---

## 5. Manual Verification & User Walkthrough

To verify CAN-21 as a developer or user:

### Step 1: Run the Interactive Demo
Run the standalone simulation script:
```bash
uv run python scripts/demo_agent_state_timetravel.py
```

### Step 2: What to Observe in the Output
1. **Phase 1 (User Query Ingestion):**
   - User message is added and checkpointed (`chk_...`).
   - W3C Traceparent and initial token budget (128k remaining) are recorded.
2. **Phase 2 (Supervisor Decomposition):**
   - 3-step query plan is formulated and committed to checkpoint history.
3. **Phase 3 (Analyst Execution):**
   - DuckDB SQL query artifact and Two-Tier Citation Envelope (`18-10-0004-01`, `v41690973`) are saved to state.
4. **Phase 4 (HITL Interruption):**
   - An ambiguous geography breakpoint (`AMBIGUOUS_MEMBER`) pauses the agent pipeline, recording candidate options for human intervention.
5. **Phase 5 (Time-Travel Rollback & Conversation Forking):**
   - The checkpointer inspects history and rolls back to Phase 2 (pre-interruption). The active interrupt and subsequent SQL artifacts vanish cleanly from active memory.
   - The conversation is forked from Checkpoint 1 into a new thread `thread_cpi_alt_ontario_only`, proving hypothetical branch execution.

---

## 6. Review & Approval Protocol

In accordance with our user rules and repository guardrails:
1. PR #33 (`CAN-17`) remains open awaiting peer review from Samir Ibrahim (`@samiromer2`).
2. This walkthrough presents all changes and verification for **CAN-21** (`BEN-16`).
3. Once you review and approve these deliverables:
   - We will bundle the task checkbox (`- [x] **CAN-21:**`) in `TASKS.md`.
   - We will commit: `[CAN-21] feat: typed AgentState schema and AsyncSqliteSaver checkpointer with time-travel`.
   - We will push to `origin feat/CAN-21-langgraph-agent-state`.
   - We will open the Pull Request with dual auto-closing keys: `Closes BEN-16` / `Closes CAN-21`.
