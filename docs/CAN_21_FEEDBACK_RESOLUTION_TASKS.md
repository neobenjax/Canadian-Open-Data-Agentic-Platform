# Task Activities: CAN-21 Feedback Resolution (PR #34)

**Feature Branch:** `feat/CAN-21-langgraph-agent-state`  
**Linear Task:** `CAN-21` (`BEN-16`)  
**Target Milestone:** Milestone 2 (Sprint 2)  
**Lead Architect:** Benjamin Sanchez Zebadua (`neobenjax`)  
**Reviewer:** Samir Ibrahim (`samiromer2`)

---

## Activities Checklist

- [x] **Activity 34.1: Annotated Channel Reducers & TokenBudget Validator**
  - [x] Add `typing.Annotated` imports to `packages/agent-orchestrator/src/candata_agent/state.py`.
  - [x] Attach `add_messages` reducer to `AgentState.messages: Annotated[tuple[AgentMessage, ...], add_messages]`.
  - [x] Attach `merge_citations` reducer to `AgentState.citations: Annotated[tuple[CitationEnvelope, ...], merge_citations]`.
  - [x] Add Pydantic model validator to `TokenBudget` calculating or validating `total_tokens_used == prompt_tokens_used + completion_tokens_used`.

- [x] **Activity 34.2: LangGraph BaseCheckpointSaver Compliance**
  - [x] Inherit `AsyncSqliteSaver` from `langgraph.checkpoint.base.BaseCheckpointSaver`.
  - [x] Implement `aput(self, config, checkpoint, metadata, new_versions)` matching LangGraph specification.
  - [x] Implement `aget_tuple(self, config)` returning `CheckpointTuple | None`.
  - [x] Implement `alist(self, config, ...)` yielding `CheckpointTuple`.
  - [x] Implement `aput_writes(self, config, writes, task_id, task_path)` for graph channel writes.
  - [x] Provide typed `aput` and `aget_state` for direct typed `AgentState` persistence.

- [x] **Activity 34.3: Exact Decimal and Date Serialization Fidelity**
  - [x] Implement type-safe JSON serialization (`_encode_type_preserving` / `_decode_type_preserving`) preserving `Decimal` and `datetime.date` objects in `SQLArtifact.rows`.
  - [x] Ensure deserialization restores exact `Decimal` and `datetime.date` instances rather than plain strings.

- [x] **Activity 34.4: Session ID Preservation in Time-Travel Rollback**
  - [x] Update `arollback_to`: preserve `session_id = state.session_id`.
  - [x] Only update `thread_id` to `new_thread_id or thread_id`, create a fresh `run_id`, and record `parent_checkpoint_id`.

- [x] **Activity 34.5: Decouple Scope Hygiene (Chore PR)**
  - [x] Decouple commit `c70c2ac` (`pr_triage.py` REST API) to `chore/pr-triage-rest-api` (PR #44).
  - [x] Clean and rebase `feat/CAN-21-langgraph-agent-state` onto latest `main`.

- [x] **Activity 34.6: Verification & Stress Testing**
  - [x] Unit test: `StateGraph(AgentState).compile(checkpointer=saver)` compiles cleanly.
  - [x] Unit test: Verify channel reducers register as `BinaryOperatorAggregate`.
  - [x] Unit test: Verify `Decimal` and `date` round-trip equality in `SQLArtifact.rows`.
  - [x] Unit test: Verify `session_id` is preserved during `arollback_to`.
  - [x] Run full pre-flight verification: `python scripts/verify.py` (223 passing tests, 0 Ruff errors, 0 Pyright errors).

- [ ] **Activity 34.7: Walkthrough Guide & Peer Review Response**
  - [x] Write detailed walkthrough guide `docs/CAN_21_FEEDBACK_RESOLUTION_WALKTHROUGH.md`.
  - [ ] Await user approval to commit, push to `feat/CAN-21-langgraph-agent-state`, and comment to Samir on PR #34.
