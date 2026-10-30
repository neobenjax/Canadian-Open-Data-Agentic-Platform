"""Data Analyst package for LangGraph multi-agent orchestration.

Provides:
- SandboxedDuckDB: Zero-trust, 5-layer sandboxed in-memory DuckDB query runner
- SecurityValidationError & ExecutionTimeoutError: Custom security exceptions
- validate_sql_security: Static query analyzer
- recipes: Pre-compiled deterministic mathematical recipes (inflation, CAGR, spreads, etc.)
- data_analyst_node: LangGraph 0.2+ async state graph node
"""

from candata_agent.analyst.node import data_analyst_node
from candata_agent.analyst.recipes import (
    affordability_burden_ratio,
    annual_inflation_rate,
    calendar_year_aggregation,
    cross_geography_ranking,
    discrete_regime_change_counter,
    multi_year_cagr,
    percentage_point_spread,
    yoy_point_to_point,
)
from candata_agent.analyst.sandbox import (
    ExecutionTimeoutError,
    SandboxedDuckDB,
    SecurityValidationError,
    validate_sql_security,
)

__all__ = [
    "ExecutionTimeoutError",
    "SandboxedDuckDB",
    "SecurityValidationError",
    "affordability_burden_ratio",
    "annual_inflation_rate",
    "calendar_year_aggregation",
    "cross_geography_ranking",
    "data_analyst_node",
    "discrete_regime_change_counter",
    "multi_year_cagr",
    "percentage_point_spread",
    "validate_sql_security",
    "yoy_point_to_point",
]
