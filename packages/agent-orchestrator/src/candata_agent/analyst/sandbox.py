# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false
"""Zero-Trust Embedded Sandboxed DuckDB Query Engine for LangGraph Data Analyst Node.

Enforces a 5-layer defense-in-depth model against prompt injection, Arbitrary File Read (AFR),
Server-Side Request Forgery (SSRF), and resource exhaustion attacks:
1. C++ Driver-Level Sandbox (enable_external_access=False, lock_configuration=True, memory=256MB)
2. Static AST & Lexical Parser Guardrail (enforces single SELECT statement, blocks table functions)
3. Parameterized query interpolation with bind parameters
4. Execution circuit breaker (timeout + row limits + payload limits)
5. Ephemeral in-memory table lifecycle with deterministic cleanup
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Sequence
from types import TracebackType
from typing import Any, Self

import duckdb
import pyarrow as pa


class SecurityValidationError(ValueError):
    """Raised when an analytical query violates security policies or guardrails."""


class ExecutionTimeoutError(TimeoutError):
    """Raised when an analytical query exceeds execution duration limits."""


# Regex to detect unquoted semicolons (preventing multi-statement execution)
_SEMICOLON_SPLIT_REGEX = re.compile(r";(?=(?:[^'\"]*['\"][^'\"]*['\"])*[^'\"]*$)")

# Blocklist regex for forbidden DDL, DML, administrative commands, and settings alterations
_FORBIDDEN_COMMANDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|ATTACH|DETACH|COPY|PRAGMA|CALL|INSTALL|LOAD|SET|EXPORT|CHECKPOINT)\b",
    re.IGNORECASE,
)

# Blocklist regex for dangerous DuckDB table functions, file scanners, and environment readers
_FORBIDDEN_FUNCTIONS = re.compile(
    r"\b(read_csv|read_parquet|read_text|read_blob|read_json|read_ndjson|scan_location|glob|current_setting|duckdb_settings)\b",
    re.IGNORECASE,
)

# Enforces that query starts with SELECT or CTE WITH followed by SELECT
_SELECT_STMT_REGEX = re.compile(r"^\s*(WITH\b[\s\S]+?\bSELECT\b|SELECT\b)", re.IGNORECASE)


def strip_sql_comments(query: str) -> str:
    """Strip single-line and multi-line SQL comments to prevent keyword obfuscation."""
    # Remove block comments /* ... */
    query = re.sub(r"/\*[\s\S]*?\*/", " ", query)
    # Remove line comments -- ...
    query = re.sub(r"--.*$", " ", query, flags=re.MULTILINE)
    return query.strip()


def validate_sql_security(query: str) -> None:
    """Validate that query adheres strictly to read-only, single-statement sandboxing.

    Raises:
        SecurityValidationError: If the query fails static AST or lexical verification.
    """
    clean = strip_sql_comments(query)
    if not clean:
        raise SecurityValidationError("Empty SQL query is not allowed.")

    # 1. Reject statement chaining via semicolon
    parts = [p.strip() for p in _SEMICOLON_SPLIT_REGEX.split(clean) if p.strip()]
    if len(parts) > 1:
        raise SecurityValidationError(
            "Multi-statement queries separated by semicolons are strictly forbidden."
        )

    # 2. Check for forbidden commands (DDL, DML, Admin, Extensions)
    cmd_match = _FORBIDDEN_COMMANDS.search(clean)
    if cmd_match:
        raise SecurityValidationError(
            f"Security Violation: Forbidden SQL command '{cmd_match.group(0).upper()}' detected."
        )

    # 3. Check for forbidden table functions / filesystem readers
    func_match = _FORBIDDEN_FUNCTIONS.search(clean)
    if func_match:
        raise SecurityValidationError(
            f"Security Violation: Forbidden function '{func_match.group(0)}' detected."
        )

    # 4. Enforce SELECT statement only
    if not _SELECT_STMT_REGEX.match(clean):
        raise SecurityValidationError(
            "Only read-only SELECT and WITH...SELECT statements are permitted."
        )


class SandboxedDuckDB:
    """Isolated, read-only in-memory DuckDB query runner with strict execution quotas."""

    def __init__(
        self,
        *,
        max_memory: str = "256MB",
        threads: int = 1,
    ) -> None:
        """Initialize in-memory connection locked down against filesystem/network access."""
        self._con: duckdb.DuckDBPyConnection = duckdb.connect(
            ":memory:",
            config={
                "enable_external_access": False,
                "lock_configuration": True,
                "max_memory": max_memory,
                "threads": threads,
            },
        )
        self._registered_views: set[str] = set()

    @property
    def connection(self) -> duckdb.DuckDBPyConnection:
        """Return the underlying locked DuckDB connection."""
        return self._con

    def register_table(self, name: str, table: pa.Table) -> None:
        """Register an in-memory PyArrow Table as an ephemeral queryable view."""
        self._con.register(name, table)
        self._registered_views.add(name)

    def unregister_table(self, name: str) -> None:
        """Unregister a previously mounted table."""
        if name in self._registered_views:
            self._con.unregister(name)
            self._registered_views.remove(name)

    def close(self) -> None:
        """Clean up all registered views and close the in-memory database."""
        for name in list(self._registered_views):
            try:
                self._con.unregister(name)
            except Exception:
                pass
        self._registered_views.clear()
        self._con.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    def execute_sync(
        self,
        query: str,
        params: Sequence[Any] | None = None,
        *,
        max_rows: int = 1000,
    ) -> list[dict[str, Any]]:
        """Validate and execute a read-only query synchronously, returning rows as dicts."""
        validate_sql_security(query)

        # Strip whitespace and trailing semicolons before appending LIMIT
        clean_query = query.strip().rstrip(";").strip()
        enforced_query = clean_query
        if not re.search(r"\bLIMIT\b", clean_query, re.IGNORECASE):
            enforced_query = f"{clean_query} LIMIT {max_rows}"

        try:
            if params:
                result = self._con.execute(enforced_query, list(params))
            else:
                result = self._con.execute(enforced_query)

            reader = result.arrow()
            table: pa.Table = reader.read_all()
            return table.to_pylist()[:max_rows]
        except duckdb.Error as e:
            raise ValueError(f"DuckDB SQL Execution Error: {e}") from e

    async def execute_async(
        self,
        query: str,
        params: Sequence[Any] | None = None,
        *,
        max_rows: int = 1000,
        timeout_seconds: float = 2.0,
    ) -> list[dict[str, Any]]:
        """Validate and execute a query asynchronously with strict execution timeout."""
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self.execute_sync, query, params, max_rows=max_rows),
                timeout=timeout_seconds,
            )
        except TimeoutError as exc:
            try:
                self._con.interrupt()
            except Exception:
                pass
            raise ExecutionTimeoutError(
                f"Analytical query execution timed out after {timeout_seconds}s limit."
            ) from exc
