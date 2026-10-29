# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false
"""LangGraph 0.2+ Data Analyst Node implementation.

Executes exact DuckDB SQL math over in-memory Arrow tables without LLM mental math.
Produces typed SQLArtifacts with Two-Tier Citation Envelopes and data quality warnings,
appends verified AgentMessages, and advances QueryPlan steps.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pyarrow as pa

from candata_agent.analyst import recipes
from candata_agent.analyst.sandbox import SandboxedDuckDB
from candata_agent.state import (
    AgentMessage,
    AgentState,
    MessageRole,
    PlanStep,
    SQLArtifact,
    StepStatus,
)
from candata_mcp.citation import CitationEnvelope

KNOWN_RECIPES = {
    "annual_inflation_rate",
    "yoy_point_to_point",
    "percentage_point_spread",
    "affordability_burden_ratio",
    "multi_year_cagr",
    "cross_geography_ranking",
    "calendar_year_aggregation",
    "discrete_regime_change_counter",
}


def _convert_to_arrow_table(data: Any) -> pa.Table:
    """Convert input data (pa.Table, list of dicts, or dict of lists) into a PyArrow Table."""
    if isinstance(data, pa.Table):
        return data
    if isinstance(data, list) and all(isinstance(item, dict) for item in data):
        return pa.Table.from_pylist(data)
    if isinstance(data, dict):
        return pa.Table.from_pydict(data)
    raise TypeError(f"Cannot convert data of type {type(data)} to PyArrow Table.")


def _resolve_table(
    tool_args: dict[str, Any],
    scratchpad: dict[str, Any],
    key: str = "table",
    fallback_key: str = "series_table",
) -> pa.Table:
    """Resolve and convert table argument with explicit None checks."""
    raw = tool_args.get(key)
    if raw is None:
        raw = scratchpad.get(fallback_key)
    if raw is None:
        raise ValueError(f"Required data table '{key}' (or fallback '{fallback_key}') not found.")
    return _convert_to_arrow_table(raw)


def _inspect_data_quality(table: pa.Table | None) -> list[str]:
    """Inspect Arrow table columns for data quality/suppression flags."""
    warnings: list[str] = []
    if table is None:
        return warnings

    if "status_code" in table.column_names:
        col = table["status_code"]
        suppressed = False
        for val in col:
            v_str = str(val.as_py()) if val.is_valid else ""
            if v_str in ("1", "suppressed", "x", "X"):
                suppressed = True
                break
        if suppressed:
            warnings.append(
                "StatCan data suppression flag: status_code=1 (suppressed data encountered)"
            )

    if "symbol_code" in table.column_names:
        col = table["symbol_code"]
        caution = False
        for val in col:
            v_str = str(val.as_py()) if val.is_valid else ""
            if v_str in ("2", "B", "E", "use with caution"):
                caution = True
                break
        if caution:
            warnings.append(
                "StatCan data quality flag: symbol_code=2 "
                "(use with caution: high sampling variability)"
            )

    return warnings


def _extract_series_id(
    tool_args: dict[str, Any],
    table: pa.Table | None,
    citation: CitationEnvelope | None,
) -> str:
    """Extract and strictly validate series or vector ID adhering to Guardrail 6."""
    candidate = tool_args.get("series_id") or tool_args.get("vector_id")
    if not candidate and table is not None and table.schema.metadata:
        meta = table.schema.metadata
        for key in (b"vector_id", b"series_id", b"seriesId", b"vectorId"):
            if key in meta:
                candidate = meta[key].decode("utf-8")
                break
    if not candidate and citation is not None:
        candidate = citation.core.vector_id

    candidate_str = str(candidate).strip() if candidate else ""
    if not candidate_str or candidate_str in ("series_primary", "v0", "0", "None"):
        raise ValueError(
            "Missing or invalid series/vector identifier. Strict identifier validation is "
            "mandatory per Guardrail 6 (bogus defaults like 'series_primary' or 'v0' are rejected)."
        )
    return candidate_str


def _resolve_citation(
    tool_args: dict[str, Any],
    state: AgentState,
    candidate_id: str | None = None,
) -> CitationEnvelope | None:
    """Resolve Two-Tier Citation Envelope from arguments or state."""
    raw_cit = tool_args.get("citation") or state.scratchpad.get("citation")
    if isinstance(raw_cit, CitationEnvelope):
        return raw_cit
    if candidate_id:
        for c in state.citations:
            if c.core.vector_id == candidate_id or c.core.table_id == candidate_id:
                return c
    if len(state.citations) == 1:
        return state.citations[0]
    return None


def _format_analyst_message(
    recipe_name: str,
    source_series_id: str,
    rows: list[dict[str, Any]],
    query: str,
    warnings: Sequence[str] = (),
) -> str:
    """Format a truthful, markdown-structured assistant summary of the analytical output."""
    header = (
        f"### 🧮 Data Analyst Execution: `{recipe_name}`\n"
        f"**Source Series / Identifier:** `{source_series_id}`\n\n"
    )

    warn_block = ""
    if warnings:
        warn_lines = "\n".join(f"> - {w}" for w in warnings)
        warn_block = f"> [!WARNING]\n{warn_lines}\n\n"

    if not rows:
        return header + warn_block + "_Calculation returned zero rows._\n"

    # Display preview table (up to 5 rows)
    preview = rows[:5]
    columns = list(preview[0].keys())
    col_headers = " | ".join(columns)
    col_divider = " | ".join(["---"] * len(columns))

    table_lines = [f"| {col_headers} |", f"| {col_divider} |"]
    for r in preview:
        vals = [str(r.get(c, "")) for c in columns]
        table_lines.append(f"| {' | '.join(vals)} |")

    table_md = "\n".join(table_lines)
    footer = f"\n\n_Computed via exact DuckDB SQL math ({len(rows)} total rows). Zero mental math._"
    return header + warn_block + table_md + footer


async def data_analyst_node(state: AgentState) -> dict[str, Any]:
    """LangGraph node executing deterministic DuckDB analytical recipes.

    Inspects active step in state.plan, retrieves target data from scratchpad,
    executes mathematical calculations without LLM mental math, emits SQLArtifact,
    and returns state update dictionary.
    """
    # 1. Resolve active step or fallback to scratchpad instruction
    active_step: PlanStep | None = None
    if state.plan and state.plan.active_step_id is not None:
        for s in state.plan.steps:
            if s.step_id == state.plan.active_step_id:
                active_step = s
                break

    tool_name = (
        active_step.tool_name
        if active_step and active_step.tool_name
        else state.scratchpad.get("tool_name", "custom_sql")
    )
    tool_args: dict[str, Any] = (
        active_step.tool_args
        if active_step and active_step.tool_args
        else state.scratchpad.get("tool_args", {})
    )

    # 2. Execute calculation based on recipe or raw sandboxed SQL
    rows: list[dict[str, Any]] = []
    executed_sql: str = ""
    warnings: list[str] = []
    metadata: dict[str, Any] = {}
    source_series_id: str = ""
    input_citation: CitationEnvelope | None = None

    try:
        if tool_name not in KNOWN_RECIPES and tool_name not in ("custom_sql", "sql_query"):
            raise ValueError(
                f"Unknown data analyst recipe or tool '{tool_name}'. "
                f"Must be one of {sorted(KNOWN_RECIPES)} or 'custom_sql'."
            )

        # Pre-resolve citation if available
        raw_id = tool_args.get("series_id") or tool_args.get("vector_id")
        input_citation = _resolve_citation(tool_args, state, str(raw_id) if raw_id else None)

        if tool_name == "annual_inflation_rate":
            table_data = _resolve_table(tool_args, state.scratchpad)
            warnings.extend(_inspect_data_quality(table_data))
            source_series_id = _extract_series_id(tool_args, table_data, input_citation)
            expected = int(tool_args.get("expected_periods", 12))
            allow_part = bool(tool_args.get("allow_partial", False))
            rows, executed_sql = recipes.annual_inflation_rate(
                table_data,
                date_col=str(tool_args.get("date_col", "date")),
                value_col=str(tool_args.get("value_col", "value")),
                expected_periods=expected,
                allow_partial=allow_part,
            )
            metadata["derived_from_monthly"] = True

        elif tool_name == "yoy_point_to_point":
            table_data = _resolve_table(tool_args, state.scratchpad)
            warnings.extend(_inspect_data_quality(table_data))
            source_series_id = _extract_series_id(tool_args, table_data, input_citation)
            int_years = tool_args.get("interval_years")
            rows, executed_sql = recipes.yoy_point_to_point(
                table_data,
                date_col=str(tool_args.get("date_col", "date")),
                value_col=str(tool_args.get("value_col", "value")),
                lag=int(tool_args.get("lag", 12)),
                interval_years=int(int_years) if int_years is not None else None,
            )

        elif tool_name == "percentage_point_spread":
            table_a = _resolve_table(
                tool_args, state.scratchpad, key="table_a", fallback_key="table_a"
            )
            table_b = _resolve_table(
                tool_args, state.scratchpad, key="table_b", fallback_key="table_b"
            )
            warnings.extend(_inspect_data_quality(table_a))
            warnings.extend(_inspect_data_quality(table_b))
            source_series_id = _extract_series_id(tool_args, table_a, input_citation)
            rows, executed_sql = recipes.percentage_point_spread(
                table_a,
                table_b,
                date_col=str(tool_args.get("date_col", "date")),
                value_col=str(tool_args.get("value_col", "value")),
                series_a_name=str(tool_args.get("series_a_name", "series_a")),
                series_b_name=str(tool_args.get("series_b_name", "series_b")),
            )

        elif tool_name == "affordability_burden_ratio":
            rent_tbl = _resolve_table(
                tool_args, state.scratchpad, key="rent_table", fallback_key="rent_table"
            )
            inc_tbl = _resolve_table(
                tool_args, state.scratchpad, key="income_table", fallback_key="income_table"
            )
            warnings.extend(_inspect_data_quality(rent_tbl))
            warnings.extend(_inspect_data_quality(inc_tbl))
            source_series_id = _extract_series_id(tool_args, rent_tbl, input_citation)
            rows, executed_sql = recipes.affordability_burden_ratio(
                rent_tbl,
                inc_tbl,
                rent_date_col=str(tool_args.get("rent_date_col", "date")),
                rent_val_col=str(tool_args.get("rent_val_col", "value")),
                income_date_col=str(tool_args.get("income_date_col", "date")),
                income_val_col=str(tool_args.get("income_val_col", "value")),
            )

        elif tool_name == "multi_year_cagr":
            source_series_id = _extract_series_id(tool_args, None, input_citation)
            cagr_res, executed_sql = recipes.multi_year_cagr(
                start_val=float(tool_args["start_val"]),
                end_val=float(tool_args["end_val"]),
                num_years=float(tool_args["num_years"]),
                start_date=tool_args.get("start_date"),
                end_date=tool_args.get("end_date"),
            )
            rows = [cagr_res]

        elif tool_name == "cross_geography_ranking":
            table_data = _resolve_table(tool_args, state.scratchpad)
            warnings.extend(_inspect_data_quality(table_data))
            source_series_id = _extract_series_id(tool_args, table_data, input_citation)
            rows, executed_sql = recipes.cross_geography_ranking(
                table_data,
                geo_col=str(tool_args.get("geo_col", "geography")),
                value_col=str(tool_args.get("value_col", "value")),
                date_filter=tool_args.get("date_filter"),
            )

        elif tool_name == "calendar_year_aggregation":
            table_data = _resolve_table(tool_args, state.scratchpad)
            warnings.extend(_inspect_data_quality(table_data))
            source_series_id = _extract_series_id(tool_args, table_data, input_citation)
            expected = int(tool_args.get("expected_periods", 12))
            allow_part = bool(tool_args.get("allow_partial", False))
            rows, executed_sql = recipes.calendar_year_aggregation(
                table_data,
                date_col=str(tool_args.get("date_col", "date")),
                value_col=str(tool_args.get("value_col", "value")),
                agg_func=str(tool_args.get("agg_func", "SUM")),
                expected_periods=expected,
                allow_partial=allow_part,
            )

        elif tool_name == "discrete_regime_change_counter":
            table_data = _resolve_table(tool_args, state.scratchpad)
            warnings.extend(_inspect_data_quality(table_data))
            source_series_id = _extract_series_id(tool_args, table_data, input_citation)
            regime_res, executed_sql = recipes.discrete_regime_change_counter(
                table_data,
                date_col=str(tool_args.get("date_col", "date")),
                value_col=str(tool_args.get("value_col", "value")),
                year=tool_args["year"],
            )
            rows = [regime_res]

        else:
            # Custom / Free-form SQL query executed in sandbox
            custom_query = str(tool_args.get("query") or state.scratchpad.get("query", ""))
            raw_table = (
                tool_args.get("table")
                if tool_args.get("table") is not None
                else state.scratchpad.get("series_table")
            )
            table_name = str(tool_args.get("table_name", "series_table"))
            table_data = None
            if raw_table is not None:
                table_data = _convert_to_arrow_table(raw_table)
                warnings.extend(_inspect_data_quality(table_data))
            source_series_id = _extract_series_id(tool_args, table_data, input_citation)
            with SandboxedDuckDB() as db:
                if table_data is not None:
                    db.register_table(table_name, table_data)
                rows = db.execute_sync(custom_query)
            executed_sql = custom_query

        # If any row in calculation contains warnings, bubble them up
        for r in rows:
            w = r.get("warning")
            if w and str(w) not in warnings:
                warnings.append(str(w))

    except Exception as exc:
        error_msg = f"Data Analyst Execution Failed on '{tool_name}': {exc}"
        failed_message = AgentMessage(
            role=MessageRole.ASSISTANT,
            content=f"❌ {error_msg}",
            name="data_analyst",
        )

        updated_plan = state.plan
        if state.plan and active_step:
            new_steps: list[PlanStep] = []
            for s in state.plan.steps:
                if s.step_id == active_step.step_id:
                    new_steps.append(
                        s.model_copy(
                            update={
                                "status": StepStatus.FAILED,
                                "result_summary": error_msg,
                            }
                        )
                    )
                else:
                    new_steps.append(s)
            updated_plan = state.plan.model_copy(update={"steps": tuple(new_steps)})

        return {
            "messages": (*state.messages, failed_message),
            "plan": updated_plan,
            "scratchpad": {**state.scratchpad, "last_analyst_error": error_msg},
        }

    # 3. Build immutable SQLArtifact with citation lineage & quality warnings
    artifact = SQLArtifact(
        source_series_id=source_series_id,
        sql_query=executed_sql,
        row_count=len(rows),
        rows=tuple(rows),
        citation=input_citation,
        warnings=tuple(warnings),
        metadata=metadata,
    )

    # 4. Synthesize structured message
    summary_text = _format_analyst_message(
        tool_name, source_series_id, rows, executed_sql, warnings
    )
    analyst_message = AgentMessage(
        role=MessageRole.ASSISTANT,
        content=summary_text,
        name="data_analyst",
    )

    # 5. Advance Plan if present
    updated_plan = state.plan
    if state.plan and active_step:
        new_steps: list[PlanStep] = []
        next_step_id: int | None = None
        current_idx = -1

        for i, s in enumerate(state.plan.steps):
            if s.step_id == active_step.step_id:
                current_idx = i
                new_steps.append(
                    s.model_copy(
                        update={
                            "status": StepStatus.COMPLETED,
                            "result_summary": f"Calculated {len(rows)} records via {tool_name}",
                        }
                    )
                )
            else:
                new_steps.append(s)

        if current_idx != -1 and current_idx + 1 < len(state.plan.steps):
            next_step_id = state.plan.steps[current_idx + 1].step_id

        all_completed = all(s.status == StepStatus.COMPLETED for s in new_steps)
        updated_plan = state.plan.model_copy(
            update={
                "steps": tuple(new_steps),
                "active_step_id": next_step_id,
                "completed": all_completed,
            }
        )

    # 6. Return state delta
    return {
        "sql_artifacts": (*state.sql_artifacts, artifact),
        "messages": (*state.messages, analyst_message),
        "plan": updated_plan,
        "scratchpad": {
            **state.scratchpad,
            "last_analysis_rows": rows,
            "last_analysis_recipe": tool_name,
        },
    }
