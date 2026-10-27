# CAN-21 (BEN-16): Typed AgentState & AsyncSqliteSaver Checkpointer — Task Activities

**Owner:** Benjamin Sanchez Zebadua (Solutions Architect & Lead) / Samir Ibrahim (Co-Lead)  
**Milestone:** Milestone 2: LangGraph Multi-Agent Orchestration & Observability (Sprint 2)  
**Linear Task:** `BEN-16` (`CAN-21`)  
**Branch:** `feat/CAN-21-langgraph-agent-state`

---

## 🎯 Objective
Define a typed, schema-versioned Pydantic v2 `AgentState` and an asynchronous SQLite checkpointer (`AsyncSqliteSaver`) for the LangGraph 0.2+ multi-agent orchestrator. The state provides structured channels for multi-agent messages, query decomposition plans, SQL math artifacts, Two-Tier Citation Envelopes, distributed OpenTelemetry trace contexts, and Human-in-the-Loop interruption payloads, with WAL-mode durability and time-travel rewind capabilities.

---

## 📋 Activities Breakdown

### Phase 1: Environment & Package Scaffolding
- [x] **Activity 21.1:** Scaffold `packages/agent-orchestrator/src/candata_agent` package with `__init__.py`.
- [x] **Activity 21.2:** Configure `pyproject.toml` to register `packages/agent-orchestrator/src` in `pythonpath`, `ruff.src`, and `pyright` strict analysis paths.

### Phase 2: Typed Pydantic v2 AgentState Schemas (`state.py`)
- [x] **Activity 21.3:** Define `AgentMessage` with role (`MessageRole`), content, tool call envelopes, and frozen immutability.
- [x] **Activity 21.4:** Define `QueryPlan` and `PlanStep` models with lifecycle status (`StepStatus`) for supervisor query decomposition.
- [x] **Activity 21.5:** Define `TokenBudget` (remaining capacity calculation) and `TraceContext` (OTel `traceparent` and `span_id`) for distributed observability.
- [x] **Activity 21.6:** Define `HITLInterrupt` model with `InterruptType` for geographic and statistical ambiguity breakpoints.
- [x] **Activity 21.7:** Define `AgentState` with `schema_version`, message reducer (`add_messages`), citation deduplicator (`merge_citations`), and ephemeral vs. persistent channels.

### Phase 3: Durable Time-Travel Checkpointer (`checkpoint.py`)
- [x] **Activity 21.8:** Implement `AsyncSqliteSaver` checkpointer using asynchronous SQLite with WAL mode (`PRAGMA journal_mode=WAL`), foreign keys, and synchronous NORMAL.
- [x] **Activity 21.9:** Implement thread, run, and checkpoint storage with deterministic primary keys and Pydantic JSON serialization.
- [x] **Activity 21.10:** Implement time-travel rollback API (`aget`, `alist`, `aget_history`, `arollback_to`) enabling conversation forking.

### Phase 4: Unit Testing & Verification
- [x] **Activity 21.11:** Build comprehensive test suite in `tests/test_agent_state.py` asserting Pydantic validation, multi-turn accumulation, citation deduplication, and time-travel checkpointing.
- [x] **Activity 21.12:** Run `python scripts/verify.py` and ensure zero Ruff, Pyright, or Pytest regressions (196 passing tests).

### Phase 5: User Manual Deliverables & Walkthrough
- [x] **Activity 21.13:** Build interactive time-travel CLI verification tool `scripts/demo_agent_state_timetravel.py`.
- [x] **Activity 21.14:** Produce comprehensive walkthrough guide `docs/CAN_21_LANGGRAPH_AGENT_STATE_WALKTHROUGH.md`.
