# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false
"""Durable, asynchronous SQLite checkpointer (AsyncSqliteSaver) for LangGraph multi-agent state.

Implements LangGraph's BaseCheckpointSaver protocol while providing WAL-mode database persistence,
thread/run isolation, type-preserving serialization (Decimal, date), and time-travel rollback.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import uuid
from collections.abc import AsyncIterator, Iterator, Sequence
from dataclasses import asdict
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import TracebackType
from typing import Any, Self, cast

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)
from langgraph.checkpoint.serde.base import SerializerProtocol

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


def _encode_type_preserving(obj: Any) -> Any:
    """Recursively encode Decimal and datetime.date into tagged dictionaries for JSON roundtrip."""
    if isinstance(obj, Decimal):
        return {"__type__": "decimal", "value": str(obj)}
    if isinstance(obj, date) and not isinstance(obj, datetime):
        return {"__type__": "date", "value": obj.isoformat()}
    if isinstance(obj, dict):
        return {k: _encode_type_preserving(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_encode_type_preserving(v) for v in obj]
    return obj


def _decode_type_preserving(obj: Any) -> Any:
    """Recursively decode tagged dictionaries back into Decimal and datetime.date instances."""
    if isinstance(obj, dict):
        if "__type__" in obj and "value" in obj and len(obj) == 2:
            if obj["__type__"] == "decimal":
                return Decimal(str(obj["value"]))
            if obj["__type__"] == "date":
                return date.fromisoformat(str(obj["value"]))
        return {k: _decode_type_preserving(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decode_type_preserving(v) for v in obj]
    return obj


def _serialize_state(state: AgentState) -> str:
    """Serialize AgentState to JSON with Decimal and date type preservation."""
    raw = state.model_dump()
    raw["citations"] = [asdict(c) for c in state.citations]
    raw_artifacts = []
    for a in state.sql_artifacts:
        a_dict = a.model_dump()
        if a.citation is not None:
            a_dict["citation"] = asdict(a.citation)
        raw_artifacts.append(a_dict)
    raw["sql_artifacts"] = raw_artifacts
    encoded = _encode_type_preserving(raw)
    return json.dumps(encoded, default=str)


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
    """Reconstruct AgentState from JSON string, preserving exact Decimal and date instances."""
    data = json.loads(raw_json)
    decoded = _decode_type_preserving(data)

    # Reconstruct messages
    msgs: list[AgentMessage] = []
    for m in decoded.get("messages", []):
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
    plan_raw = decoded.get("plan")
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

    # Reconstruct SQL artifacts with exact Decimal and date objects
    artifacts: list[SQLArtifact] = []
    for a in decoded.get("sql_artifacts", []):
        cit_raw = a.get("citation")
        citation_obj = _rebuild_citation(cit_raw) if cit_raw and isinstance(cit_raw, dict) else None
        artifacts.append(
            SQLArtifact(
                artifact_id=a["artifact_id"],
                source_series_id=a["source_series_id"],
                sql_query=a["sql_query"],
                row_count=a["row_count"],
                rows=tuple(a.get("rows", [])),
                citation=citation_obj,
                warnings=tuple(a.get("warnings", ())),
                metadata=dict(a.get("metadata", {})),
                created_at=datetime.fromisoformat(a["created_at"]),
            )
        )

    # Reconstruct citations
    citations: list[CitationEnvelope] = [
        _rebuild_citation(c) for c in decoded.get("citations", []) if isinstance(c, dict)
    ]

    # Reconstruct HITL interrupt
    interrupt: HITLInterrupt | None = None
    int_raw = decoded.get("active_interrupt")
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
    tc_raw = decoded.get("trace_context") or {}
    trace_context = TraceContext(
        traceparent=tc_raw.get("traceparent"),
        tracestate=tc_raw.get("tracestate"),
        span_id=tc_raw.get("span_id"),
        parent_span_id=tc_raw.get("parent_span_id"),
    )

    tb_raw = decoded.get("token_budget") or {}
    token_budget = TokenBudget(
        max_budget=int(tb_raw.get("max_budget", 128000)),
        prompt_tokens_used=int(tb_raw.get("prompt_tokens_used", 0)),
        completion_tokens_used=int(tb_raw.get("completion_tokens_used", 0)),
        total_tokens_used=int(tb_raw.get("total_tokens_used", 0)),
    )

    return AgentState(
        schema_version=int(decoded.get("schema_version", 1)),
        session_id=str(decoded["session_id"]),
        thread_id=str(decoded["thread_id"]),
        run_id=str(decoded.get("run_id", f"run_{uuid.uuid4().hex[:8]}")),
        messages=tuple(msgs),
        plan=plan,
        sql_artifacts=tuple(artifacts),
        citations=tuple(citations),
        active_interrupt=interrupt,
        trace_context=trace_context,
        token_budget=token_budget,
        scratchpad=dict(decoded.get("scratchpad", {})),
    )


class AsyncSqliteSaver(BaseCheckpointSaver[Any]):
    """Durable, asynchronous SQLite checkpointer implementing LangGraph's BaseCheckpointSaver.

    Supports native LangGraph StateGraph execution, WAL mode durability, exact Decimal and
    date type persistence, and conversation time-travel rollback without session ID erasure.
    """

    def __init__(
        self,
        db_path: str | Path = ":memory:",
        *,
        serde: SerializerProtocol | None = None,
    ) -> None:
        super().__init__(serde=serde)
        self.db_path: str = str(db_path)
        self._conn: sqlite3.Connection | None = None
        self._lock = asyncio.Lock()

    @classmethod
    def from_conn_string(cls, conn_string: str | Path) -> Self:
        """Create checkpointer from database file path or connection URI."""
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
            if self.db_path != ":memory:":
                cur.execute("PRAGMA journal_mode=WAL;")
            cur.execute("PRAGMA synchronous=NORMAL;")
            cur.execute("PRAGMA busy_timeout=5000;")
            cur.execute("PRAGMA foreign_keys=ON;")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS checkpoints (
                    thread_id TEXT NOT NULL,
                    checkpoint_ns TEXT NOT NULL DEFAULT '',
                    checkpoint_id TEXT NOT NULL,
                    parent_checkpoint_id TEXT,
                    type TEXT,
                    checkpoint BLOB,
                    metadata BLOB,
                    state_json TEXT,
                    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
                );
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS checkpoint_writes (
                    thread_id TEXT NOT NULL,
                    checkpoint_ns TEXT NOT NULL DEFAULT '',
                    checkpoint_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    task_path TEXT NOT NULL DEFAULT '',
                    idx INTEGER NOT NULL,
                    channel TEXT NOT NULL,
                    type TEXT,
                    value BLOB,
                    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx),
                    FOREIGN KEY (thread_id, checkpoint_ns, checkpoint_id)
                        REFERENCES checkpoints(thread_id, checkpoint_ns, checkpoint_id)
                        ON DELETE CASCADE
                );
            """)
            self._conn.commit()

    async def setup(self) -> None:
        """Initialize database connection and tables asynchronously."""
        async with self._lock:
            await asyncio.to_thread(self._sync_setup)

    def _get_connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._sync_setup()
        assert self._conn is not None
        return self._conn

    # --------------------------------------------------------------------------
    # LangGraph BaseCheckpointSaver Async Protocol Methods
    # --------------------------------------------------------------------------

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint | AgentState,  # type: ignore[override]
        metadata: CheckpointMetadata | None = None,
        new_versions: ChannelVersions | None = None,
    ) -> RunnableConfig:
        """Store a checkpoint tuple or typed AgentState under the configured thread."""
        await self.setup()
        configurable: dict[str, Any] = config.get("configurable", {})
        thread_id = str(configurable.get("thread_id", ""))
        checkpoint_ns = str(configurable.get("checkpoint_ns", ""))

        # Support direct AgentState persistence
        if isinstance(checkpoint, AgentState):
            chk_thread = thread_id or checkpoint.thread_id
            chk_id = str(configurable.get("checkpoint_id") or f"chk_{uuid.uuid4().hex[:12]}")
            parent_id = configurable.get("parent_checkpoint_id")
            state_json = _serialize_state(checkpoint)

            def _put_agent_state() -> None:
                conn = self._get_connection()
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT OR REPLACE INTO checkpoints
                    (thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id,
                     type, checkpoint, metadata, state_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        chk_thread,
                        checkpoint_ns,
                        chk_id,
                        parent_id,
                        "agent_state",
                        None,
                        None,
                        state_json,
                    ),
                )
                conn.commit()

            async with self._lock:
                await asyncio.to_thread(_put_agent_state)
            return cast(
                RunnableConfig,
                {
                    "configurable": {
                        "thread_id": chk_thread,
                        "checkpoint_ns": checkpoint_ns,
                        "checkpoint_id": chk_id,
                    }
                },
            )

        # Native LangGraph Checkpoint dict persistence
        chk_id = str(checkpoint["id"])
        parent_id = configurable.get("checkpoint_id")
        type_str, chk_blob = self.serde.dumps_typed(checkpoint)
        _, meta_blob = self.serde.dumps_typed(metadata or {})

        def _put_langgraph() -> None:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute(
                """
                INSERT OR REPLACE INTO checkpoints
                (thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id,
                 type, checkpoint, metadata, state_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    thread_id,
                    checkpoint_ns,
                    chk_id,
                    parent_id,
                    type_str,
                    chk_blob,
                    meta_blob,
                    None,
                ),
            )
            conn.commit()

        async with self._lock:
            await asyncio.to_thread(_put_langgraph)

        return cast(
            RunnableConfig,
            {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": chk_id,
                }
            },
        )

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        """Asynchronously retrieve CheckpointTuple matching configuration."""
        await self.setup()
        configurable: dict[str, Any] = config.get("configurable", {})
        thread_id = str(configurable.get("thread_id", ""))
        checkpoint_ns = str(configurable.get("checkpoint_ns", ""))
        target_chk = configurable.get("checkpoint_id")

        def _do_get() -> CheckpointTuple | None:
            conn = self._get_connection()
            cur = conn.cursor()
            if target_chk:
                cur.execute(
                    """
                    SELECT checkpoint_id, parent_checkpoint_id, type, checkpoint,
                           metadata, state_json
                    FROM checkpoints
                    WHERE thread_id = ? AND checkpoint_ns = ? AND checkpoint_id = ?;
                    """,
                    (thread_id, checkpoint_ns, str(target_chk)),
                )
            else:
                cur.execute(
                    """
                    SELECT checkpoint_id, parent_checkpoint_id, type, checkpoint,
                           metadata, state_json
                    FROM checkpoints
                    WHERE thread_id = ? AND checkpoint_ns = ?
                    ORDER BY rowid DESC LIMIT 1;
                    """,
                    (thread_id, checkpoint_ns),
                )
            row = cur.fetchone()
            if not row:
                return None

            chk_id = str(row["checkpoint_id"])
            parent_id = str(row["parent_checkpoint_id"]) if row["parent_checkpoint_id"] else None

            # Retrieve checkpoint payload
            if row["checkpoint"] is not None:
                type_str = str(row["type"] or "json")
                chk_data: Checkpoint = self.serde.loads_typed((type_str, row["checkpoint"]))
                meta_data: CheckpointMetadata = (
                    self.serde.loads_typed(("json", row["metadata"]))
                    if row["metadata"]
                    else cast(CheckpointMetadata, {"source": "loop", "step": 1, "writes": {}})
                )
            elif row["state_json"] is not None:
                # Synthesize LangGraph Checkpoint from stored AgentState JSON
                state = _deserialize_state(row["state_json"])
                chk_data = cast(
                    Checkpoint,
                    {
                        "v": 1,
                        "id": chk_id,
                        "ts": datetime.now(UTC).isoformat(),
                        "channel_values": state.model_dump(),
                        "channel_versions": {},
                        "versions_seen": {},
                        "updated_channels": None,
                    },
                )
                meta_data = cast(
                    CheckpointMetadata,
                    {
                        "source": "update",
                        "step": 1,
                        "writes": {},
                    },
                )
            else:
                return None

            # Retrieve pending writes
            cur.execute(
                """
                SELECT task_id, channel, type, value
                FROM checkpoint_writes
                WHERE thread_id = ? AND checkpoint_ns = ? AND checkpoint_id = ?
                ORDER BY idx ASC;
                """,
                (thread_id, checkpoint_ns, chk_id),
            )
            write_rows = cur.fetchall()
            pending_writes: list[tuple[str, str, Any]] = [
                (
                    str(wr["task_id"]),
                    str(wr["channel"]),
                    self.serde.loads_typed((str(wr["type"]), wr["value"])),
                )
                for wr in write_rows
            ]

            parent_config: RunnableConfig | None = (
                cast(
                    RunnableConfig,
                    {
                        "configurable": {
                            "thread_id": thread_id,
                            "checkpoint_ns": checkpoint_ns,
                            "checkpoint_id": parent_id,
                        }
                    },
                )
                if parent_id
                else None
            )

            return CheckpointTuple(
                config=cast(
                    RunnableConfig,
                    {
                        "configurable": {
                            "thread_id": thread_id,
                            "checkpoint_ns": checkpoint_ns,
                            "checkpoint_id": chk_id,
                        }
                    },
                ),
                checkpoint=chk_data,
                metadata=meta_data,
                parent_config=parent_config,
                pending_writes=pending_writes,
            )

        async with self._lock:
            return await asyncio.to_thread(_do_get)

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        """Stream chronological checkpoints for the configured thread."""
        await self.setup()
        configurable: dict[str, Any] = config.get("configurable", {}) if config else {}
        thread_id = str(configurable.get("thread_id", ""))
        checkpoint_ns = str(configurable.get("checkpoint_ns", ""))
        max_items = limit or 50

        def _fetch_all() -> list[CheckpointTuple]:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute(
                """
                SELECT checkpoint_id
                FROM checkpoints
                WHERE thread_id = ? AND checkpoint_ns = ?
                ORDER BY rowid DESC
                LIMIT ?;
                """,
                (thread_id, checkpoint_ns, max_items),
            )
            rows = cur.fetchall()
            tuples: list[CheckpointTuple] = []
            for r in rows:
                chk_cfg = cast(
                    RunnableConfig,
                    {
                        "configurable": {
                            "thread_id": thread_id,
                            "checkpoint_ns": checkpoint_ns,
                            "checkpoint_id": str(r["checkpoint_id"]),
                        }
                    },
                )
                item = self._sync_get_tuple(chk_cfg)
                if item:
                    tuples.append(item)
            return tuples

        async with self._lock:
            items = await asyncio.to_thread(_fetch_all)

        for item in items:
            yield item

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        """Asynchronously store pending channel writes from graph execution steps."""
        await self.setup()
        configurable: dict[str, Any] = config.get("configurable", {})
        thread_id = str(configurable.get("thread_id", ""))
        checkpoint_ns = str(configurable.get("checkpoint_ns", ""))
        checkpoint_id = str(configurable.get("checkpoint_id", ""))

        def _do_writes() -> None:
            conn = self._get_connection()
            cur = conn.cursor()
            for idx, (channel, val) in enumerate(writes):
                type_str, val_blob = self.serde.dumps_typed(val)
                cur.execute(
                    """
                    INSERT OR REPLACE INTO checkpoint_writes
                    (thread_id, checkpoint_ns, checkpoint_id, task_id,
                     task_path, idx, channel, type, value)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        thread_id,
                        checkpoint_ns,
                        checkpoint_id,
                        task_id,
                        task_path,
                        idx,
                        channel,
                        type_str,
                        val_blob,
                    ),
                )
            conn.commit()

        async with self._lock:
            await asyncio.to_thread(_do_writes)

    # --------------------------------------------------------------------------
    # Sync Protocol Implementations
    # --------------------------------------------------------------------------

    def _sync_get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        configurable: dict[str, Any] = config.get("configurable", {})
        thread_id = str(configurable.get("thread_id", ""))
        checkpoint_ns = str(configurable.get("checkpoint_ns", ""))
        target_chk = configurable.get("checkpoint_id")

        conn = self._get_connection()
        cur = conn.cursor()
        if target_chk:
            cur.execute(
                """
                SELECT checkpoint_id, parent_checkpoint_id, type, checkpoint,
                       metadata, state_json
                FROM checkpoints
                WHERE thread_id = ? AND checkpoint_ns = ? AND checkpoint_id = ?;
                """,
                (thread_id, checkpoint_ns, str(target_chk)),
            )
        else:
            cur.execute(
                """
                SELECT checkpoint_id, parent_checkpoint_id, type, checkpoint,
                       metadata, state_json
                FROM checkpoints
                WHERE thread_id = ? AND checkpoint_ns = ?
                ORDER BY rowid DESC LIMIT 1;
                """,
                (thread_id, checkpoint_ns),
            )
        row = cur.fetchone()
        if not row:
            return None

        chk_id = str(row["checkpoint_id"])
        parent_id = str(row["parent_checkpoint_id"]) if row["parent_checkpoint_id"] else None

        if row["checkpoint"] is not None:
            type_str = str(row["type"] or "json")
            chk_data: Checkpoint = self.serde.loads_typed((type_str, row["checkpoint"]))
            meta_data: CheckpointMetadata = (
                self.serde.loads_typed(("json", row["metadata"]))
                if row["metadata"]
                else cast(CheckpointMetadata, {"source": "loop", "step": 1, "writes": {}})
            )
        elif row["state_json"] is not None:
            state = _deserialize_state(row["state_json"])
            chk_data = cast(
                Checkpoint,
                {
                    "v": 1,
                    "id": chk_id,
                    "ts": datetime.now(UTC).isoformat(),
                    "channel_values": state.model_dump(),
                    "channel_versions": {},
                    "versions_seen": {},
                    "updated_channels": None,
                },
            )
            meta_data = cast(
                CheckpointMetadata,
                {
                    "source": "update",
                    "step": 1,
                    "writes": {},
                },
            )
        else:
            return None

        return CheckpointTuple(
            config=cast(
                RunnableConfig,
                {
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_ns": checkpoint_ns,
                        "checkpoint_id": chk_id,
                    }
                },
            ),
            checkpoint=chk_data,
            metadata=meta_data,
            parent_config=(
                cast(
                    RunnableConfig,
                    {
                        "configurable": {
                            "thread_id": thread_id,
                            "checkpoint_ns": checkpoint_ns,
                            "checkpoint_id": parent_id,
                        }
                    },
                )
                if parent_id
                else None
            ),
            pending_writes=[],
        )

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        """Synchronously retrieve CheckpointTuple matching configuration."""
        self._sync_setup()
        return self._sync_get_tuple(config)

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        """Synchronously store a Checkpoint."""
        self._sync_setup()
        configurable: dict[str, Any] = config.get("configurable", {})
        thread_id = str(configurable.get("thread_id", ""))
        checkpoint_ns = str(configurable.get("checkpoint_ns", ""))
        chk_id = str(checkpoint["id"])
        parent_id = configurable.get("checkpoint_id")
        type_str, chk_blob = self.serde.dumps_typed(checkpoint)
        _, meta_blob = self.serde.dumps_typed(metadata or {})

        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT OR REPLACE INTO checkpoints
            (thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id,
             type, checkpoint, metadata, state_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (thread_id, checkpoint_ns, chk_id, parent_id, type_str, chk_blob, meta_blob, None),
        )
        conn.commit()
        return cast(
            RunnableConfig,
            {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": chk_id,
                }
            },
        )

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        """Synchronously iterate over checkpoints."""
        self._sync_setup()
        configurable: dict[str, Any] = config.get("configurable", {}) if config else {}
        thread_id = str(configurable.get("thread_id", ""))
        checkpoint_ns = str(configurable.get("checkpoint_ns", ""))
        max_items = limit or 50

        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT checkpoint_id FROM checkpoints
            WHERE thread_id = ? AND checkpoint_ns = ?
            ORDER BY rowid DESC LIMIT ?;
            """,
            (thread_id, checkpoint_ns, max_items),
        )
        for r in cur.fetchall():
            item = self._sync_get_tuple(
                cast(
                    RunnableConfig,
                    {
                        "configurable": {
                            "thread_id": thread_id,
                            "checkpoint_ns": checkpoint_ns,
                            "checkpoint_id": str(r["checkpoint_id"]),
                        }
                    },
                )
            )
            if item:
                yield item

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        """Synchronously store pending channel writes."""
        self._sync_setup()
        configurable: dict[str, Any] = config.get("configurable", {})
        thread_id = str(configurable.get("thread_id", ""))
        checkpoint_ns = str(configurable.get("checkpoint_ns", ""))
        checkpoint_id = str(configurable.get("checkpoint_id", ""))

        conn = self._get_connection()
        cur = conn.cursor()
        for idx, (channel, val) in enumerate(writes):
            type_str, val_blob = self.serde.dumps_typed(val)
            cur.execute(
                """
                INSERT OR REPLACE INTO checkpoint_writes
                (thread_id, checkpoint_ns, checkpoint_id, task_id,
                 task_path, idx, channel, type, value)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    thread_id,
                    checkpoint_ns,
                    checkpoint_id,
                    task_id,
                    task_path,
                    idx,
                    channel,
                    type_str,
                    val_blob,
                ),
            )
        conn.commit()

    # --------------------------------------------------------------------------
    # Typed AgentState Helpers & Time-Travel History
    # --------------------------------------------------------------------------

    async def aget_state(self, config: RunnableConfig | dict[str, Any]) -> AgentState | None:
        """Retrieve state for a thread, returning typed AgentState with exact types."""
        await self.setup()
        configurable: dict[str, Any] = config.get("configurable", {})
        thread_id = str(configurable.get("thread_id", ""))
        target_chk = configurable.get("checkpoint_id")

        def _do_get() -> str | None:
            conn = self._get_connection()
            cur = conn.cursor()
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
            return str(row["state_json"]) if row and row["state_json"] else None

        async with self._lock:
            raw_json = await asyncio.to_thread(_do_get)

        if not raw_json:
            tup = await self.aget_tuple(cast(RunnableConfig, config))
            if tup and "channel_values" in tup.checkpoint:
                vals = tup.checkpoint["channel_values"]
                try:
                    return AgentState.model_validate(vals)
                except Exception:
                    pass
            return None

        return _deserialize_state(raw_json)

    async def arollback_to(
        self,
        thread_id: str,
        target_checkpoint_id: str | dict[str, Any],
        new_thread_id: str | None = None,
    ) -> AgentState:
        """Time-travel rewind: roll back to target checkpoint, preserving original session_id.

        Optionally forks history into a new thread without erasing user session lineage.
        """
        chk_id = (
            str(target_checkpoint_id.get("configurable", {}).get("checkpoint_id", ""))
            if isinstance(target_checkpoint_id, dict)
            else str(target_checkpoint_id)
        )
        state = await self.aget_state(
            {"configurable": {"thread_id": thread_id, "checkpoint_id": chk_id}}
        )
        if state is None:
            raise KeyError(f"Checkpoint {chk_id!r} not found for thread {thread_id!r}")

        destination_thread = new_thread_id or thread_id

        # CRITICAL FIX (Samir Observation 4): Preserve state.session_id!
        new_state = state.model_copy(
            update={
                "thread_id": destination_thread,
                "session_id": state.session_id,
                "run_id": f"run_{uuid.uuid4().hex[:8]}",
            }
        )

        await self.aput(
            cast(
                RunnableConfig,
                {
                    "configurable": {
                        "thread_id": destination_thread,
                        "parent_checkpoint_id": chk_id,
                    }
                },
            ),
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
