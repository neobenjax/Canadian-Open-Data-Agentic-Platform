# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false
"""Durable, asynchronous SQLite checkpointer (AsyncSqliteSaver) for LangGraph multi-agent state.

Wraps LangGraph's official `AsyncSqliteSaver` from `langgraph-checkpoint-sqlite` while providing
direct `AgentState` persistence, thread/run isolation, exact type preservation (Decimal, date),
and conversation time-travel rollback with session lineage preservation.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any, Self, cast

import aiosqlite
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)
from langgraph.checkpoint.serde.base import SerializerProtocol
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver as _BaseAsyncSqliteSaver

from candata_agent.state import AgentState


class AsyncSqliteSaver(_BaseAsyncSqliteSaver):
    """Durable, asynchronous SQLite checkpointer extending LangGraph's official AsyncSqliteSaver.

    Supports native LangGraph StateGraph multi-agent execution, WAL mode durability, exact
    Decimal/date persistence, and time-travel rollback without session ID erasure.
    """

    def __init__(
        self,
        conn_or_path: aiosqlite.Connection | str | Path = ":memory:",
        *,
        serde: SerializerProtocol | None = None,
    ) -> None:
        self._owned_conn: bool = False
        self._conn_or_path = conn_or_path
        self._provided_serde = serde
        if isinstance(conn_or_path, aiosqlite.Connection):
            super().__init__(conn=conn_or_path, serde=serde)
        else:
            BaseCheckpointSaver.__init__(self, serde=serde)
            self.conn = None  # type: ignore[assignment]
            self._owned_conn = True
            self.is_setup = False

    @classmethod
    @asynccontextmanager
    async def from_conn_string(
        cls, conn_string: str | Path, *, serde: SerializerProtocol | None = None
    ) -> AsyncGenerator[AsyncSqliteSaver, None]:
        """Create a new AsyncSqliteSaver instance from a connection string or path."""
        async with aiosqlite.connect(str(conn_string)) as conn:
            saver = cls(conn, serde=serde)
            await saver.setup()
            yield saver

    async def __aenter__(self) -> Self:
        if self._owned_conn and self.conn is None:
            db_path = str(self._conn_or_path)
            if db_path != ":memory:":
                Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            conn = await aiosqlite.connect(db_path)
            super().__init__(conn=conn, serde=self._provided_serde)
        await self.setup()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        conn = cast(aiosqlite.Connection | None, self.conn)
        if self._owned_conn and conn is not None:
            await conn.close()

    async def aclose(self) -> None:
        """Close managed database connection."""
        conn = cast(aiosqlite.Connection | None, self.conn)
        if self._owned_conn and conn is not None:
            await conn.close()

    @staticmethod
    def _normalize_config(config: RunnableConfig | dict[str, Any] | None) -> RunnableConfig:
        cfg: dict[str, Any] = dict(config or {})
        raw_configurable = cfg.get("configurable")
        configurable: dict[str, Any] = dict(raw_configurable) if raw_configurable else {}
        if "checkpoint_ns" not in configurable:
            configurable["checkpoint_ns"] = ""
        cfg["configurable"] = configurable
        return cast(RunnableConfig, cfg)

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint | AgentState,  # type: ignore[override]
        metadata: CheckpointMetadata | None = None,
        new_versions: ChannelVersions | None = None,
    ) -> RunnableConfig:
        """Store a checkpoint tuple or typed AgentState under the configured thread."""
        cfg = self._normalize_config(config)
        raw_configurable = cfg.get("configurable")
        configurable: dict[str, Any] = (
            dict(raw_configurable) if raw_configurable is not None else {}
        )
        cfg["configurable"] = configurable

        if isinstance(checkpoint, AgentState):
            chk_id = str(configurable.get("checkpoint_id") or f"chk_{uuid.uuid4().hex[:12]}")
            configurable["checkpoint_id"] = chk_id
            thread_id = str(configurable.get("thread_id") or checkpoint.thread_id)
            configurable["thread_id"] = thread_id

            # Deep copy model dump so in-place scratchpad changes do not corrupt saved state
            state_dict = deepcopy(checkpoint.model_dump())

            chk_dict: Checkpoint = {
                "v": 1,
                "id": chk_id,
                "ts": datetime.now(UTC).isoformat(),
                "channel_values": state_dict,
                "channel_versions": {},
                "versions_seen": {},
                "updated_channels": None,
            }
            res = await super().aput(cfg, chk_dict, metadata or {}, new_versions or {})
            return res

        return await super().aput(cfg, checkpoint, metadata or {}, new_versions or {})

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        """Asynchronously retrieve CheckpointTuple matching configuration."""
        cfg = self._normalize_config(config)
        return await super().aget_tuple(cfg)

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        """Stream chronological checkpoints for the configured thread."""
        cfg = self._normalize_config(config) if config else None
        before_cfg = self._normalize_config(before) if before else None
        async for item in super().alist(cfg, filter=filter, before=before_cfg, limit=limit):
            yield item

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Any,
        task_id: str,
        task_path: str = "",
    ) -> None:
        """Asynchronously store pending channel writes from graph execution steps."""
        cfg = self._normalize_config(config)
        await super().aput_writes(cfg, writes, task_id, task_path)

    async def aget_state(self, config: RunnableConfig | dict[str, Any]) -> AgentState | None:
        """Retrieve latest state for a thread as a validated, immutable AgentState instance."""
        tup = await self.aget_tuple(cast(RunnableConfig, config))
        if tup is None:
            return None
        values = tup.checkpoint.get("channel_values", {})
        if not values:
            return None
        return AgentState.model_validate(values)

    async def arollback_to(
        self,
        thread_id: str,
        target_checkpoint_id: str,
        new_thread_id: str | None = None,
    ) -> AgentState:
        """Roll back a thread to a checkpoint, preserving session_id across rewind and forks."""
        cfg = self._normalize_config(
            {"configurable": {"thread_id": thread_id, "checkpoint_id": target_checkpoint_id}}
        )
        tup = await self.aget_tuple(cfg)
        if tup is None:
            raise KeyError(f"Checkpoint '{target_checkpoint_id}' not found in thread '{thread_id}'")

        values = tup.checkpoint.get("channel_values", {})
        state = AgentState.model_validate(values)

        if new_thread_id:
            # Fork into new branch thread while strictly preserving original session_id
            forked_state = state.model_copy(update={"thread_id": new_thread_id}, deep=True)
            fork_cfg = self._normalize_config(
                {
                    "configurable": {
                        "thread_id": new_thread_id,
                        "checkpoint_id": f"chk_fork_{uuid.uuid4().hex[:8]}",
                        "parent_checkpoint_id": target_checkpoint_id,
                    }
                }
            )
            await self.aput(fork_cfg, forked_state)
            return forked_state

        return state
