"""Deterministic Mathematical and Economic Recipe Library for CanData-MCP Data Analyst.

Implements the 8 core Canadian macroeconomic and housing recipes verified against
the GTA Housing Ground-Truth Benchmark (gta_ground_truth_v1.md):
1. annual_inflation_rate (calendar-year average of monthly index values)
2. yoy_point_to_point (12-month lagged change for single months or Dec-to-Dec)
3. percentage_point_spread (rate difference in 'pp' and 'bps')
4. affordability_burden_ratio (annual shelter rent vs annual median income)
5. multi_year_cagr (compound annual growth rate)
6. cross_geography_ranking (ranking and gap analysis across CMAs/provinces)
7. calendar_year_aggregation (calendar-year flow sum from monthly series)
8. discrete_regime_change_counter (discrete policy rate change count and range)
"""

from __future__ import annotations

from typing import Any

import pyarrow as pa

from candata_agent.analyst.sandbox import SandboxedDuckDB


def annual_inflation_rate(
    table: pa.Table,
    *,
    date_col: str = "date",
    value_col: str = "value",
) -> tuple[list[dict[str, Any]], str]:
    """Calculate annual inflation rate from monthly CPI by averaging 12 monthly index values.

    Directly powers GTA Ground-Truth GT-10 and GT-11.
    """
    view_name = "monthly_series"
    query = f"""
    WITH annual_agg AS (
        SELECT
            strftime(TRY_CAST(substr({date_col} || '-01-01', 1, 10) AS DATE), '%Y') AS cal_year,
            AVG({value_col}) AS avg_index,
            COUNT({value_col}) AS observed_months
        FROM {view_name}
        WHERE {value_col} IS NOT NULL
        GROUP BY cal_year
        HAVING COUNT({value_col}) >= 1
    ),
    yoy_calc AS (
        SELECT
            cal_year,
            ROUND(avg_index, 4) AS avg_index,
            observed_months,
            LAG(avg_index, 1) OVER (ORDER BY cal_year ASC) AS prev_year_avg,
            ROUND(
                ((avg_index - LAG(avg_index, 1) OVER (ORDER BY cal_year ASC)) /
                 NULLIF(LAG(avg_index, 1) OVER (ORDER BY cal_year ASC), 0)) * 100.0,
                4
            ) AS annual_inflation_pct
        FROM annual_agg
    )
    SELECT
        cal_year,
        avg_index,
        observed_months,
        ROUND(prev_year_avg, 4) AS prev_year_avg,
        annual_inflation_pct
    FROM yoy_calc
    ORDER BY cal_year DESC
    """
    with SandboxedDuckDB() as db:
        db.register_table(view_name, table)
        rows = db.execute_sync(query)
    return rows, query.strip()


def yoy_point_to_point(
    table: pa.Table,
    *,
    date_col: str = "date",
    value_col: str = "value",
    lag: int = 12,
) -> tuple[list[dict[str, Any]], str]:
    """Calculate point-to-point change with arbitrary lag (default 12 months for YoY).

    Directly powers GTA Ground-Truth GT-01, GT-06, and GT-12.
    """
    view_name = "series_data"
    query = f"""
    WITH ordered_series AS (
        SELECT
            {date_col} AS obs_date,
            {value_col} AS current_value,
            LAG({value_col}, {lag}) OVER (ORDER BY {date_col} ASC) AS lag_value
        FROM {view_name}
        WHERE {value_col} IS NOT NULL
    )
    SELECT
        obs_date,
        ROUND(current_value, 4) AS current_value,
        ROUND(lag_value, 4) AS lag_value,
        ROUND(current_value - lag_value, 4) AS change_absolute,
        ROUND(
            ((current_value - lag_value) / NULLIF(lag_value, 0)) * 100.0,
            4
        ) AS change_pct
    FROM ordered_series
    ORDER BY obs_date DESC
    """
    with SandboxedDuckDB() as db:
        db.register_table(view_name, table)
        rows = db.execute_sync(query)
    return rows, query.strip()


def percentage_point_spread(
    table_a: pa.Table,
    table_b: pa.Table,
    *,
    date_col: str = "date",
    value_col: str = "value",
    series_a_name: str = "series_a",
    series_b_name: str = "series_b",
) -> tuple[list[dict[str, Any]], str]:
    """Calculate rate spread in percentage points (pp) and basis points (bps).

    Directly powers GTA Ground-Truth GT-02 and BoC policy rate spreads.
    """
    name_a = "tab_a"
    name_b = "tab_b"
    query = f"""
    SELECT
        a.{date_col} AS obs_date,
        ROUND(a.{value_col}, 4) AS {series_a_name},
        ROUND(b.{value_col}, 4) AS {series_b_name},
        ROUND(a.{value_col} - b.{value_col}, 4) AS spread_pp,
        ROUND((a.{value_col} - b.{value_col}) * 100.0, 1) AS spread_bps
    FROM {name_a} a
    JOIN {name_b} b ON a.{date_col} = b.{date_col}
    ORDER BY obs_date DESC
    """
    with SandboxedDuckDB() as db:
        db.register_table(name_a, table_a)
        db.register_table(name_b, table_b)
        rows = db.execute_sync(query)
    return rows, query.strip()


def affordability_burden_ratio(
    rent_table: pa.Table,
    income_table: pa.Table,
    *,
    rent_date_col: str = "date",
    rent_val_col: str = "value",
    income_date_col: str = "date",
    income_val_col: str = "value",
) -> tuple[list[dict[str, Any]], str]:
    """Calculate shelter cost as percentage of median after-tax income.

    Directly powers GTA Ground-Truth GT-07.
    """
    view_rent = "rent_series"
    view_income = "income_series"
    query = f"""
    SELECT
        r.{rent_date_col} AS ref_period,
        ROUND(r.{rent_val_col}, 2) AS monthly_rent,
        ROUND(r.{rent_val_col} * 12.0, 2) AS annual_rent,
        ROUND(i.{income_val_col}, 2) AS annual_income,
        ROUND(
            ((r.{rent_val_col} * 12.0) / NULLIF(i.{income_val_col}, 0)) * 100.0,
            2
        ) AS rent_to_income_pct
    FROM {view_rent} r
    JOIN {view_income} i ON substr(r.{rent_date_col}, 1, 4) = substr(i.{income_date_col}, 1, 4)
    ORDER BY ref_period DESC
    """
    with SandboxedDuckDB() as db:
        db.register_table(view_rent, rent_table)
        db.register_table(view_income, income_table)
        rows = db.execute_sync(query)
    return rows, query.strip()


def multi_year_cagr(
    start_val: float,
    end_val: float,
    num_years: float,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> tuple[dict[str, Any], str]:
    """Calculate Compound Annual Growth Rate (CAGR) and total cumulative percentage change.

    Directly powers GTA Ground-Truth GT-08.
    """
    if num_years <= 0:
        raise ValueError(f"num_years must be strictly positive, got {num_years}")

    query = """
    SELECT
        ? AS start_date,
        ? AS end_date,
        ROUND(?::DOUBLE, 4) AS start_val,
        ROUND(?::DOUBLE, 4) AS end_val,
        ROUND(?::DOUBLE, 2) AS num_years,
        ROUND(
            ((POW(?::DOUBLE / NULLIF(?::DOUBLE, 0), 1.0 / ?::DOUBLE)) - 1.0) * 100.0,
            4
        ) AS cagr_pct,
        ROUND(
            ((?::DOUBLE - ?::DOUBLE) / NULLIF(?::DOUBLE, 0)) * 100.0,
            4
        ) AS cumulative_growth_pct
    """
    params = [
        start_date or "start",
        end_date or "end",
        start_val,
        end_val,
        num_years,
        end_val,
        start_val,
        num_years,
        end_val,
        start_val,
        start_val,
    ]
    with SandboxedDuckDB() as db:
        rows = db.execute_sync(query, params)
    return (rows[0] if rows else {}), query.strip()


def cross_geography_ranking(
    table: pa.Table,
    *,
    geo_col: str = "geography",
    value_col: str = "value",
    date_filter: str | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """Rank regions and compute gap to highest region.

    Directly powers GTA Ground-Truth GT-03 and GT-04.
    """
    view_name = "cross_geo"
    where_sql = f"WHERE date = '{date_filter}'" if date_filter else ""
    query = f"""
    WITH ranked AS (
        SELECT
            {geo_col} AS geography,
            ROUND({value_col}, 4) AS value,
            RANK() OVER (ORDER BY {value_col} DESC) AS ranking,
            FIRST_VALUE(ROUND({value_col}, 4)) OVER (ORDER BY {value_col} DESC) AS leader_value
        FROM {view_name}
        {where_sql}
    )
    SELECT
        geography,
        value,
        ranking,
        ROUND(leader_value - value, 4) AS gap_to_leader_pp
    FROM ranked
    ORDER BY ranking ASC
    """
    with SandboxedDuckDB() as db:
        db.register_table(view_name, table)
        rows = db.execute_sync(query)
    return rows, query.strip()


def calendar_year_aggregation(
    table: pa.Table,
    *,
    date_col: str = "date",
    value_col: str = "value",
    agg_func: str = "SUM",
) -> tuple[list[dict[str, Any]], str]:
    """Aggregate monthly flows (e.g. housing starts) into calendar-year totals.

    Directly powers GTA Ground-Truth GT-05.
    """
    allowed_aggs = {"SUM", "AVG", "MIN", "MAX"}
    func = agg_func.upper()
    if func not in allowed_aggs:
        raise ValueError(f"agg_func must be one of {allowed_aggs}, got '{agg_func}'")

    view_name = "flow_data"
    query = f"""
    SELECT
        strftime(TRY_CAST(substr({date_col} || '-01-01', 1, 10) AS DATE), '%Y') AS cal_year,
        ROUND({func}({value_col}), 2) AS aggregated_total,
        COUNT({value_col}) AS observed_months
    FROM {view_name}
    WHERE {value_col} IS NOT NULL
    GROUP BY cal_year
    ORDER BY cal_year DESC
    """
    with SandboxedDuckDB() as db:
        db.register_table(view_name, table)
        rows = db.execute_sync(query)
    return rows, query.strip()


def discrete_regime_change_counter(
    table: pa.Table,
    *,
    date_col: str = "date",
    value_col: str = "value",
    year: str | int,
) -> tuple[dict[str, Any], str]:
    """Count rate changes and retrieve starting, ending, min, and max levels in a given year.

    Directly powers GTA Ground-Truth GT-13.
    """
    target_year = str(year)
    view_name = "policy_rate_series"
    query = f"""
    WITH year_slice AS (
        SELECT
            {date_col} AS obs_date,
            {value_col} AS rate_val,
            LAG({value_col}, 1) OVER (ORDER BY {date_col} ASC) AS prev_val
        FROM {view_name}
        WHERE strftime(TRY_CAST(substr({date_col} || '-01-01', 1, 10) AS DATE), '%Y') = ?
          AND {value_col} IS NOT NULL
    ),
    metrics AS (
        SELECT
            rate_val,
            prev_val,
            FIRST_VALUE(rate_val) OVER (ORDER BY obs_date ASC) AS start_rate,
            LAST_VALUE(rate_val) OVER (
                ORDER BY obs_date ASC
                ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
            ) AS end_rate,
            MIN(rate_val) OVER () AS min_r,
            MAX(rate_val) OVER () AS max_r
        FROM year_slice
    )
    SELECT
        ? AS calendar_year,
        COUNT(*) FILTER (WHERE prev_val IS NOT NULL AND rate_val != prev_val) AS rate_change_count,
        ROUND(ANY_VALUE(start_rate), 4) AS year_start_rate,
        ROUND(ANY_VALUE(end_rate), 4) AS year_end_rate,
        ROUND(ANY_VALUE(min_r), 4) AS min_rate,
        ROUND(ANY_VALUE(max_r), 4) AS max_rate
    FROM metrics
    """
    with SandboxedDuckDB() as db:
        db.register_table(view_name, table)
        rows = db.execute_sync(query, [target_year, target_year])
    return (rows[0] if rows else {}), query.strip()
