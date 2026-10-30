# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false
"""Durable, asynchronous SQLite checkpointer (AsyncSqliteSaver) for LangGraph multi-agent state.

Provides WAL-mode database persistence, thread/run isolation, deterministic state
serialization, and time-travel history rollback and conversation forking.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import uuid
from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any, Self

from candata_agent.state import (
    AgentMessage,
    AgentState,
    HITLInterrupt,
    InterruptType,
    MessageRole,
    PlanStep,
    QueryPlan,
    SQLArtifact,
    StepStatus,
    TokenBudget,
    TraceContext,
)
from candata_mcp.citation import (
    BilingualTitle,
    CitationEnvelope,
    CoreVerificationTuple,
    MetadataEnrichment,
)


def _serialize_state(state: AgentState) -> str:
    """Serialize AgentState to a deterministic JSON string."""
    raw = state.model_dump()
    # Serialize citations dataclasses cleanly
    raw["citations"] = [asdict(c) for c in state.citations]
    return json.dumps(raw, default=str)


def _rebuild_citation(raw: dict[str, Any]) -> CitationEnvelope:
    """Reconstruct CitationEnvelope dataclass from dictionary."""
    core_raw = raw.get("core") or {}
    enrichment_raw = raw.get("enrichment") or {}
    title_raw = enrichment_raw.get("bilingual_title") or {}

    bilingual_title = BilingualTitle(
        en=str(title_raw.get("en", "")),
        fr=str(title_raw["fr"]) if title_raw.get("fr") else None,
    )

    enrichment_kwargs: dict[str, Any] = {
        "coordinate": (
            str(enrichment_raw["coordinate"]) if enrichment_raw.get("coordinate") else None
        ),
        "release_or_revision_date": (
            str(enrichment_raw["release_or_revision_date"])
            if enrichment_raw.get("release_or_revision_date")
            else None
        ),
        "bilingual_title": bilingual_title,
        "canonical_url": str(enrichment_raw.get("canonical_url", "")),
    }

    if "license_url" in MetadataEnrichment.__dataclass_fields__:
        enrichment_kwargs["license_url"] = (
            str(enrichment_raw["license_url"]) if enrichment_raw.get("license_url") else None
        )

    return CitationEnvelope(
        publisher=str(raw.get("publisher", "Statistics Canada")),
        core=CoreVerificationTuple(
            table_id=str(core_raw.get("table_id", "")),
            vector_id=str(core_raw.get("vector_id", "")),
            reference_period=str(core_raw.get("reference_period", "")),
        ),
        enrichment=MetadataEnrichment(**enrichment_kwargs),
    )


def _deserialize_state(raw_json: str) -> AgentState:
    """Reconstruct AgentState from JSON string."""
    data = json.loads(raw_json)

    # Reconstruct messages
    msgs: list[AgentMessage] = []
    for m in data.get("messages", []):
        msgs.append(
            AgentMessage(
                id=m["id"],
                role=MessageRole(m["role"]),
                content=m["content"],
                name=m.get("name"),
                tool_calls=tuple(m.get("tool_calls", [])),
                timestamp=datetime.fromisoformat(m["timestamp"]),
            )
        )

    # Reconstruct plan
    plan: QueryPlan | None = None
    plan_raw = data.get("plan")
    if plan_raw:
        steps: list[PlanStep] = []
        for s in plan_raw.get("steps", []):
            steps.append(
                PlanStep(
                    step_id=s["step_id"],
                    description=s["description"],
                    assigned_agent=s["assigned_agent"],
                    status=StepStatus(s.get("status", "pending")),
                    tool_name=s.get("tool_name"),
                    tool_args=s.get("tool_args", {}),
                    result_summary=s.get("result_summary"),
                )
            )
        plan = QueryPlan(
            plan_id=plan_raw["plan_id"],
            objective=plan_raw["objective"],
            steps=tuple(steps),
            active_step_id=plan_raw.get("active_step_id"),
            completed=bool(plan_raw.get("completed", False)),
        )

    # Reconstruct SQL artifacts
    artifacts: list[SQLArtifact] = []
    for a in data.get("sql_artifacts", []):
        artifacts.append(
            SQLArtifact(
                artifact_id=a["artifact_id"],
                source_series_id=a["source_series_id"],
                sql_query=a["sql_query"],
                row_count=a["row_count"],
                rows=tuple(a.get("rows", [])),
                created_at=datetime.fromisoformat(a["created_at"]),
            )
        )

    # Reconstruct citations
    citations: list[CitationEnvelope] = [
        _rebuild_citation(c) for c in data.get("citations", []) if isinstance(c, dict)
    ]

    # Reconstruct HITL interrupt
    interrupt: HITLInterrupt | None = None
    int_raw = data.get("active_interrupt")
    if int_raw:
        interrupt = HITLInterrupt(
            interrupt_id=int_raw["interrupt_id"],
            interrupt_type=InterruptType(int_raw["interrupt_type"]),
            reason=int_raw["reason"],
            details=int_raw.get("details", {}),
            suggested_options=tuple(int_raw.get("suggested_options", ())),
            resolved=bool(int_raw.get("resolved", False)),
            resolution=int_raw.get("resolution"),
            resolved_at=(
                datetime.fromisoformat(int_raw["resolved_at"])
                if int_raw.get("resolved_at")
                else None
            ),
        )

    # Observability
    tc_raw = data.get("trace_context") or {}
    trace_context = TraceContext(
        traceparent=tc_raw.get("traceparent"),
        tracestate=tc_raw.get("tracestate"),
        span_id=tc_raw.get("span_id"),
        parent_span_id=tc_raw.get("parent_span_id"),
    )

    tb_raw = data.get("token_budget") or {}
    token_budget = TokenBudget(
        max_budget=int(tb_raw.get("max_budget", 128000)),
        prompt_tokens_used=int(tb_raw.get("prompt_tokens_used", 0)),
        completion_tokens_used=int(tb_raw.get("completion_tokens_used", 0)),
        total_tokens_used=int(tb_raw.get("total_tokens_used", 0)),
    )

    return AgentState(
        schema_version=int(data.get("schema_version", 1)),
        session_id=str(data["session_id"]),
        thread_id=str(data["thread_id"]),
        run_id=str(data.get("run_id", f"run_{uuid.uuid4().hex[:8]}")),
        messages=tuple(msgs),
        plan=plan,
        sql_artifacts=tuple(artifacts),
        citations=tuple(citations),
        active_interrupt=interrupt,
        trace_context=trace_context,
        token_budget=token_budget,
        scratchpad=dict(data.get("scratchpad", {})),
    )


class AsyncSqliteSaver:
    """Asynchronous, thread-safe SQLite checkpointer supporting WAL durability and time travel."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path: str = str(db_path)
        self._conn: sqlite3.Connection | None = None
        self._lock = asyncio.Lock()

    @classmethod
    def from_conn_string(cls, conn_string: str | Path) -> Self:
        """Create checkpointer from file path or URI."""
        return cls(db_path=conn_string)

    async def __aenter__(self) -> Self:
        await self.setup()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

    def _sync_setup(self) -> None:
        if self._conn is None:
            if self.db_path != ":memory:":
                Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                isolation_level=None,
            )
            self._conn.row_factory = sqlite3.Row

            cur = self._conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL;")
            cur.execute("PRAGMA synchronous=NORMAL;")
            cur.execute("PRAGMA busy_timeout=5000;")
            cur.execute("PRAGMA foreign_keys=ON;")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS checkpoints (
                    thread_id TEXT NOT NULL,
                    checkpoint_id TEXT NOT NULL,
                    parent_checkpoint_id TEXT,
                    run_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    schema_version INTEGER NOT NULL,
                    state_json TEXT NOT NULL,
                    PRIMARY KEY (thread_id, checkpoint_id)
                );
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS checkpoint_writes (
                    thread_id TEXT NOT NULL,
                    checkpoint_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (thread_id, checkpoint_id, task_id, channel),
                    FOREIGN KEY (thread_id, checkpoint_id)
                        REFERENCES checkpoints(thread_id, checkpoint_id)
                        ON DELETE CASCADE
                );
            """)
            self._conn.commit()

    async def setup(self) -> None:
        """Initialize tables and database connection asynchronously."""
        async with self._lock:
            await asyncio.to_thread(self._sync_setup)

    async def aput(self, config: dict[str, Any], state: AgentState) -> str:
        """Store state as a new checkpoint under the configured thread."""
        await self.setup()
        configurable = config.get("configurable", {})
        thread_id = str(configurable.get("thread_id", state.thread_id))
        checkpoint_id = str(configurable.get("checkpoint_id") or f"chk_{uuid.uuid4().hex[:12]}")
        parent_id = configurable.get("parent_checkpoint_id")
        created_at = datetime.now(UTC).isoformat()
        state_json = _serialize_state(state)

        def _do_put() -> None:
            assert self._conn is not None
            cur = self._conn.cursor()
            cur.execute(
                """
                INSERT OR REPLACE INTO checkpoints
                (thread_id, checkpoint_id, parent_checkpoint_id, run_id,
                 created_at, schema_version, state_json)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    thread_id,
                    checkpoint_id,
                    parent_id,
                    state.run_id,
                    created_at,
                    state.schema_version,
                    state_json,
                ),
            )
            self._conn.commit()

        async with self._lock:
            await asyncio.to_thread(_do_put)
        return checkpoint_id

    async def aget(self, config: dict[str, Any]) -> AgentState | None:
        """Retrieve state for a thread, optionally targeted by checkpoint_id."""
        await self.setup()
        configurable = config.get("configurable", {})
        thread_id = str(configurable.get("thread_id", ""))
        target_chk = configurable.get("checkpoint_id")

        def _do_get() -> str | None:
            assert self._conn is not None
            cur = self._conn.cursor()
            if target_chk:
                cur.execute(
                    """
                    SELECT state_json FROM checkpoints
                    WHERE thread_id = ? AND checkpoint_id = ?;
                    """,
                    (thread_id, str(target_chk)),
                )
            else:
                cur.execute(
                    """
                    SELECT state_json FROM checkpoints
                    WHERE thread_id = ?
                    ORDER BY rowid DESC LIMIT 1;
                    """,
                    (thread_id,),
                )
            row = cur.fetchone()
            return str(row["state_json"]) if row else None

        async with self._lock:
            raw_json = await asyncio.to_thread(_do_get)

        if not raw_json:
            return None
        return _deserialize_state(raw_json)

    async def alist(self, config: dict[str, Any], limit: int = 50) -> Sequence[dict[str, Any]]:
        """List chronological checkpoints recorded for a specific thread."""
        await self.setup()
        configurable = config.get("configurable", {})
        thread_id = str(configurable.get("thread_id", ""))

        def _do_list() -> list[dict[str, Any]]:
            assert self._conn is not None
            cur = self._conn.cursor()
            cur.execute(
                """
                SELECT checkpoint_id, parent_checkpoint_id, run_id, created_at, schema_version
                FROM checkpoints
                WHERE thread_id = ?
                ORDER BY rowid DESC
                LIMIT ?;
                """,
                (thread_id, limit),
            )
            rows = cur.fetchall()
            return [
                {
                    "checkpoint_id": str(r["checkpoint_id"]),
                    "parent_checkpoint_id": (
                        str(r["parent_checkpoint_id"]) if r["parent_checkpoint_id"] else None
                    ),
                    "run_id": str(r["run_id"]),
                    "created_at": str(r["created_at"]),
                    "schema_version": int(r["schema_version"]),
                }
                for r in rows
            ]

        async with self._lock:
            return await asyncio.to_thread(_do_list)

    async def arollback_to(
        self,
        thread_id: str,
        target_checkpoint_id: str,
        new_thread_id: str | None = None,
    ) -> AgentState:
        """Time-travel rewind: roll back to target checkpoint.

        Optionally forks history into a new thread.
        """
        state = await self.aget(
            {"configurable": {"thread_id": thread_id, "checkpoint_id": target_checkpoint_id}}
        )
        if state is None:
            raise KeyError(
                f"Checkpoint {target_checkpoint_id!r} not found for thread {thread_id!r}"
            )

        destination_thread = new_thread_id or thread_id
        new_state = state.model_copy(
            update={
                "thread_id": destination_thread,
                "session_id": destination_thread,
                "run_id": f"run_{uuid.uuid4().hex[:8]}",
            }
        )

        await self.aput(
            {
                "configurable": {
                    "thread_id": destination_thread,
                    "parent_checkpoint_id": target_checkpoint_id,
                }
            },
            new_state,
        )
        return new_state

    async def aclose(self) -> None:
        """Flush transactions and close the underlying SQLite database."""
        async with self._lock:

            def _do_close() -> None:
                if self._conn is not None:
                    self._conn.close()
                    self._conn = None

            await asyncio.to_thread(_do_close)
