"""Deterministic Mathematical and Economic Recipe Library for CanData-MCP Data Analyst.

Implements the 8 core Canadian macroeconomic and housing recipes verified against
the GTA Housing Ground-Truth Benchmark (gta_ground_truth_v1.md):
1. annual_inflation_rate (calendar-year average of monthly index values)
2. yoy_point_to_point (calendar temporal self-join for single months, annual or Dec-to-Dec)
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
    expected_periods: int = 12,
    allow_partial: bool = False,
) -> tuple[list[dict[str, Any]], str]:
    """Calculate annual inflation rate from monthly CPI by averaging 12 monthly index values.

    Directly powers GTA Ground-Truth GT-10 and GT-11.
    Handles data suppression (e.g. 9/12 observed months) by flagging incomplete years
    and omitting partial rates unless allow_partial is True.
    """
    view_name = "monthly_series"
    clean_date = date_col.replace('"', '""')
    clean_val = value_col.replace('"', '""')

    query = f"""
    WITH annual_agg AS (
        SELECT
            strftime(TRY_CAST(substr("{clean_date}" || '-01-01', 1, 10) AS DATE), '%Y') AS cal_year,
            AVG("{clean_val}") AS raw_avg_index,
            COUNT("{clean_val}") AS observed_months
        FROM {view_name}
        WHERE "{clean_val}" IS NOT NULL
        GROUP BY cal_year
        HAVING COUNT("{clean_val}") >= 1
    ),
    annual_valid AS (
        SELECT
            cal_year,
            observed_months,
            CASE
                WHEN observed_months >= ? OR ? THEN ROUND(raw_avg_index, 4)
                ELSE NULL
            END AS avg_index,
            CASE
                WHEN observed_months >= ? OR ? THEN TRUE
                ELSE FALSE
            END AS complete,
            CASE
                WHEN observed_months < ? AND NOT ? THEN
                    'Incomplete year (' || observed_months::VARCHAR || '/' || ?::VARCHAR
                    || ' periods observed); suppressed or partial data '
                    || 'declined to avoid hallucination'
                ELSE NULL
            END AS warning
        FROM annual_agg
    ),
    yoy_calc AS (
        SELECT
            cal_year,
            avg_index,
            observed_months,
            complete,
            warning,
            LAG(avg_index, 1) OVER (ORDER BY cal_year ASC) AS prev_year_avg,
            CASE
                WHEN avg_index IS NULL
                     OR LAG(avg_index, 1) OVER (ORDER BY cal_year ASC) IS NULL
                THEN NULL
                ELSE ROUND(
                    ((avg_index - LAG(avg_index, 1) OVER (ORDER BY cal_year ASC)) /
                     NULLIF(LAG(avg_index, 1) OVER (ORDER BY cal_year ASC), 0)) * 100.0,
                    4
                )
            END AS annual_inflation_pct
        FROM annual_valid
    )
    SELECT
        cal_year,
        avg_index,
        observed_months,
        complete,
        warning,
        ROUND(prev_year_avg, 4) AS prev_year_avg,
        annual_inflation_pct,
        TRUE AS derived_from_monthly
    FROM yoy_calc
    ORDER BY cal_year DESC
    """
    params = [
        expected_periods,
        allow_partial,
        expected_periods,
        allow_partial,
        expected_periods,
        allow_partial,
        expected_periods,
    ]
    with SandboxedDuckDB() as db:
        db.register_table(view_name, table)
        rows = db.execute_sync(query, params)
    return rows, query.strip()


def yoy_point_to_point(
    table: pa.Table,
    *,
    date_col: str = "date",
    value_col: str = "value",
    lag: int = 12,
    interval_years: int | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """Calculate point-to-point change using calendar temporal self-join.

    Directly powers GTA Ground-Truth GT-01, GT-06, and GT-12.
    Uses calendar temporal matching (INTERVAL) rather than physical row offset,
    preventing severe rate distortion when intermediate months are suppressed.
    Missing earlier periods evaluate to NULL rather than jumping across gaps.
    """
    view_name = "series_data"
    clean_date = date_col.replace('"', '""')
    clean_val = value_col.replace('"', '""')

    if interval_years is not None:
        interval_expr = f"{int(interval_years)} YEAR"
    elif lag >= 12 and lag % 12 == 0:
        interval_expr = f"{int(lag // 12)} YEAR"
    else:
        interval_expr = f"{int(lag)} MONTH"

    query = f"""
    WITH normalized_series AS (
        SELECT
            "{clean_date}" AS obs_date,
            TRY_CAST(CASE
                WHEN LENGTH("{clean_date}") = 4 THEN "{clean_date}" || '-01-01'
                WHEN LENGTH("{clean_date}") = 7 THEN "{clean_date}" || '-01'
                ELSE "{clean_date}"
            END AS DATE) AS date_norm,
            "{clean_val}" AS val
        FROM {view_name}
        WHERE "{clean_val}" IS NOT NULL
    )
    SELECT
        curr.obs_date AS obs_date,
        ROUND(curr.val, 4) AS current_value,
        ROUND(prior.val, 4) AS lag_value,
        ROUND(curr.val - prior.val, 4) AS change_absolute,
        CASE
            WHEN prior.val IS NULL OR prior.val = 0 THEN NULL
            ELSE ROUND(((curr.val - prior.val) / prior.val) * 100.0, 4)
        END AS change_pct
    FROM normalized_series curr
    LEFT JOIN normalized_series prior
        ON prior.date_norm = (
            CASE
                WHEN LENGTH(curr.obs_date) = 4 THEN (curr.date_norm - INTERVAL 1 YEAR)::DATE
                ELSE (curr.date_norm - INTERVAL {interval_expr})::DATE
            END
        )
    ORDER BY curr.date_norm DESC
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
    clean_date = date_col.replace('"', '""')
    clean_val = value_col.replace('"', '""')
    clean_a_name = series_a_name.replace('"', '""')
    clean_b_name = series_b_name.replace('"', '""')

    query = f"""
    SELECT
        a."{clean_date}" AS obs_date,
        ROUND(a."{clean_val}", 4) AS "{clean_a_name}",
        ROUND(b."{clean_val}", 4) AS "{clean_b_name}",
        ROUND(a."{clean_val}" - b."{clean_val}", 4) AS spread_pp,
        ROUND((a."{clean_val}" - b."{clean_val}") * 100.0, 1) AS spread_bps
    FROM {name_a} a
    JOIN {name_b} b ON a."{clean_date}" = b."{clean_date}"
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
    clean_r_date = rent_date_col.replace('"', '""')
    clean_r_val = rent_val_col.replace('"', '""')
    clean_i_date = income_date_col.replace('"', '""')
    clean_i_val = income_val_col.replace('"', '""')

    query = f"""
    SELECT
        r."{clean_r_date}" AS ref_period,
        ROUND(r."{clean_r_val}", 2) AS monthly_rent,
        ROUND(r."{clean_r_val}" * 12.0, 2) AS annual_rent,
        ROUND(i."{clean_i_val}", 2) AS annual_income,
        ROUND(
            ((r."{clean_r_val}" * 12.0) / NULLIF(i."{clean_i_val}", 0)) * 100.0,
            2
        ) AS rent_to_income_pct
    FROM {view_rent} r
    JOIN {view_income} i ON substr(r."{clean_r_date}", 1, 4) = substr(i."{clean_i_date}", 1, 4)
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
    Uses parameterized date binding and quoted identifier columns.
    """
    view_name = "cross_geo"
    clean_geo = geo_col.replace('"', '""')
    clean_val = value_col.replace('"', '""')

    where_sql = 'WHERE "date" = ?' if date_filter else ""
    params = [date_filter] if date_filter else None

    query = f"""
    WITH ranked AS (
        SELECT
            "{clean_geo}" AS geography,
            ROUND("{clean_val}", 4) AS value,
            RANK() OVER (ORDER BY "{clean_val}" DESC) AS ranking,
            FIRST_VALUE(ROUND("{clean_val}", 4)) OVER (ORDER BY "{clean_val}" DESC) AS leader_value
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
        rows = db.execute_sync(query, params)
    return rows, query.strip()


def calendar_year_aggregation(
    table: pa.Table,
    *,
    date_col: str = "date",
    value_col: str = "value",
    agg_func: str = "SUM",
    expected_periods: int = 12,
    allow_partial: bool = False,
) -> tuple[list[dict[str, Any]], str]:
    """Aggregate monthly flows (e.g. housing starts) into calendar-year totals.

    Directly powers GTA Ground-Truth GT-05.
    If observed periods are less than expected_periods (e.g. 9/12 due to StatCan suppression)
    and allow_partial is False, aggregated_total is set to None and an informative warning
    is attached, preventing miscalculated annual totals.
    """
    allowed_aggs = {"SUM", "AVG", "MIN", "MAX"}
    func = agg_func.upper()
    if func not in allowed_aggs:
        raise ValueError(f"agg_func must be one of {allowed_aggs}, got '{agg_func}'")

    view_name = "flow_data"
    clean_date = date_col.replace('"', '""')
    clean_val = value_col.replace('"', '""')

    query = f"""
    WITH raw_agg AS (
        SELECT
            strftime(TRY_CAST(substr("{clean_date}" || '-01-01', 1, 10) AS DATE), '%Y') AS cal_year,
            ROUND({func}("{clean_val}"), 2) AS raw_total,
            COUNT("{clean_val}") AS observed_months
        FROM {view_name}
        WHERE "{clean_val}" IS NOT NULL
        GROUP BY cal_year
    )
    SELECT
        cal_year,
        CASE
            WHEN observed_months >= ? OR ? THEN raw_total
            ELSE NULL
        END AS aggregated_total,
        observed_months,
        CASE
            WHEN observed_months >= ? OR ? THEN TRUE
            ELSE FALSE
        END AS complete,
        CASE
            WHEN observed_months < ? AND NOT ? THEN
                'Incomplete year (' || observed_months::VARCHAR || '/' || ?::VARCHAR
                || ' periods observed); suppressed or partial data '
                || 'declined to avoid hallucination'
            ELSE NULL
        END AS warning
    FROM raw_agg
    ORDER BY cal_year DESC
    """
    params = [
        expected_periods,
        allow_partial,
        expected_periods,
        allow_partial,
        expected_periods,
        allow_partial,
        expected_periods,
    ]
    with SandboxedDuckDB() as db:
        db.register_table(view_name, table)
        rows = db.execute_sync(query, params)
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
    clean_date = date_col.replace('"', '""')
    clean_val = value_col.replace('"', '""')

    query = f"""
    WITH year_slice AS (
        SELECT
            "{clean_date}" AS obs_date,
            "{clean_val}" AS rate_val,
            LAG("{clean_val}", 1) OVER (ORDER BY "{clean_date}" ASC) AS prev_val
        FROM {view_name}
        WHERE strftime(TRY_CAST(substr("{clean_date}" || '-01-01', 1, 10) AS DATE), '%Y') = ?
          AND "{clean_val}" IS NOT NULL
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
