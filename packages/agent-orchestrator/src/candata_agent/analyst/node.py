# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false
"""LangGraph 0.2+ Data Analyst Node implementation.

Executes exact DuckDB SQL math over in-memory Arrow tables without LLM mental math.
Produces typed SQLArtifacts, appends verified AgentMessages, and advances QueryPlan steps.
"""

from __future__ import annotations

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


def _convert_to_arrow_table(data: Any) -> pa.Table:
    """Convert input data (pa.Table, list of dicts, or dict of lists) into a PyArrow Table."""
    if isinstance(data, pa.Table):
        return data
    if isinstance(data, list) and all(isinstance(item, dict) for item in data):
        return pa.Table.from_pylist(data)
    if isinstance(data, dict):
        return pa.Table.from_pydict(data)
    raise TypeError(f"Cannot convert data of type {type(data)} to PyArrow Table.")


def _format_analyst_message(
    recipe_name: str,
    source_series_id: str,
    rows: list[dict[str, Any]],
    query: str,
) -> str:
    """Format a truthful, markdown-structured assistant summary of the analytical output."""
    header = (
        f"### 🧮 Data Analyst Execution: `{recipe_name}`\n"
        f"**Source Series / Identifier:** `{source_series_id}`\n\n"
    )

    if not rows:
        return header + "_Calculation returned zero rows._\n"

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
    return header + table_md + footer


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

    source_series_id = str(tool_args.get("series_id", "series_primary"))

    # 2. Execute calculation based on recipe or raw sandboxed SQL
    rows: list[dict[str, Any]] = []
    executed_sql: str = ""

    try:
        if tool_name == "annual_inflation_rate":
            table_data = _convert_to_arrow_table(
                tool_args.get("table") or state.scratchpad.get("series_table")
            )
            rows, executed_sql = recipes.annual_inflation_rate(
                table_data,
                date_col=tool_args.get("date_col", "date"),
                value_col=tool_args.get("value_col", "value"),
            )

        elif tool_name == "yoy_point_to_point":
            table_data = _convert_to_arrow_table(
                tool_args.get("table") or state.scratchpad.get("series_table")
            )
            rows, executed_sql = recipes.yoy_point_to_point(
                table_data,
                date_col=tool_args.get("date_col", "date"),
                value_col=tool_args.get("value_col", "value"),
                lag=int(tool_args.get("lag", 12)),
            )

        elif tool_name == "percentage_point_spread":
            table_a = _convert_to_arrow_table(
                tool_args.get("table_a") or state.scratchpad.get("table_a")
            )
            table_b = _convert_to_arrow_table(
                tool_args.get("table_b") or state.scratchpad.get("table_b")
            )
            rows, executed_sql = recipes.percentage_point_spread(
                table_a,
                table_b,
                date_col=tool_args.get("date_col", "date"),
                value_col=tool_args.get("value_col", "value"),
                series_a_name=tool_args.get("series_a_name", "series_a"),
                series_b_name=tool_args.get("series_b_name", "series_b"),
            )

        elif tool_name == "affordability_burden_ratio":
            rent_tbl = _convert_to_arrow_table(
                tool_args.get("rent_table") or state.scratchpad.get("rent_table")
            )
            inc_tbl = _convert_to_arrow_table(
                tool_args.get("income_table") or state.scratchpad.get("income_table")
            )
            rows, executed_sql = recipes.affordability_burden_ratio(
                rent_tbl,
                inc_tbl,
                rent_date_col=tool_args.get("rent_date_col", "date"),
                rent_val_col=tool_args.get("rent_val_col", "value"),
                income_date_col=tool_args.get("income_date_col", "date"),
                income_val_col=tool_args.get("income_val_col", "value"),
            )

        elif tool_name == "multi_year_cagr":
            cagr_res, executed_sql = recipes.multi_year_cagr(
                start_val=float(tool_args["start_val"]),
                end_val=float(tool_args["end_val"]),
                num_years=float(tool_args["num_years"]),
                start_date=tool_args.get("start_date"),
                end_date=tool_args.get("end_date"),
            )
            rows = [cagr_res]

        elif tool_name == "cross_geography_ranking":
            table_data = _convert_to_arrow_table(
                tool_args.get("table") or state.scratchpad.get("series_table")
            )
            rows, executed_sql = recipes.cross_geography_ranking(
                table_data,
                geo_col=tool_args.get("geo_col", "geography"),
                value_col=tool_args.get("value_col", "value"),
                date_filter=tool_args.get("date_filter"),
            )

        elif tool_name == "calendar_year_aggregation":
            table_data = _convert_to_arrow_table(
                tool_args.get("table") or state.scratchpad.get("series_table")
            )
            rows, executed_sql = recipes.calendar_year_aggregation(
                table_data,
                date_col=tool_args.get("date_col", "date"),
                value_col=tool_args.get("value_col", "value"),
                agg_func=tool_args.get("agg_func", "SUM"),
            )

        elif tool_name == "discrete_regime_change_counter":
            table_data = _convert_to_arrow_table(
                tool_args.get("table") or state.scratchpad.get("series_table")
            )
            regime_res, executed_sql = recipes.discrete_regime_change_counter(
                table_data,
                date_col=tool_args.get("date_col", "date"),
                value_col=tool_args.get("value_col", "value"),
                year=tool_args["year"],
            )
            rows = [regime_res]

        else:
            # Custom / Free-form SQL query executed in sandbox
            custom_query = str(tool_args.get("query") or state.scratchpad.get("query", ""))
            raw_table = tool_args.get("table") or state.scratchpad.get("series_table")
            table_name = str(tool_args.get("table_name", "series_table"))
            with SandboxedDuckDB() as db:
                if raw_table is not None:
                    table_data = _convert_to_arrow_table(raw_table)
                    db.register_table(table_name, table_data)
                rows = db.execute_sync(custom_query)
            executed_sql = custom_query

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

    # 3. Build immutable SQLArtifact
    artifact = SQLArtifact(
        source_series_id=source_series_id,
        sql_query=executed_sql,
        row_count=len(rows),
        rows=tuple(rows),
    )

    # 4. Synthesize structured message
    summary_text = _format_analyst_message(tool_name, source_series_id, rows, executed_sql)
    analyst_message = AgentMessage(
        role=MessageRole.ASSISTANT,
        content=summary_text,
        name="data_analyst",
    )

    # 5. Advance Plan if present
    updated_plan = state.plan
    if state.plan and active_step:
        new_steps = []
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
