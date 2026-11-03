# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false, reportUnknownVariableType=false
"""Plotly figures for one run's fetched series and computed results (CAN-32).

Rules the figures follow:

- One y-axis per unit. Series that share a unit are drawn on one axis; series with different
  units are stacked as small multiples on a shared time axis, never on a second y-axis.
- Colour follows the series' position in the plan (fetch order), from the Okabe-Ito palette,
  which stays distinguishable under the common colour-vision deficiencies.
- Observations StatCan flags with a status or symbol code, and missing values, are marked and
  named in the hover text, so a "use with caution" figure never looks like a clean one.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Final

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from candata_agent.ui.stream import AnalysisResult, FetchedSeries

# Okabe-Ito, in fixed order (black omitted: it reads as an axis, not a series).
PALETTE: Final = ("#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9", "#D55E00", "#F0E442")
FLAG_COLOUR: Final = "#D55E00"
MAX_SERIES: Final = len(PALETTE)


@dataclass(frozen=True, slots=True)
class ResultMetric:
    """The column a recipe's headline figure lives in, and the time column it runs along."""

    x: str
    y: str
    title: str


# Recipes whose output is a time series of one metric. The others (CAGR, ranking, regime-change
# counts, affordability) are single rows or categories and are shown as tables.
RESULT_METRICS: Final = {
    "yoy_point_to_point": ResultMetric("obs_date", "change_pct", "Year-over-year change (%)"),
    "annual_inflation_rate": ResultMetric(
        "cal_year", "annual_inflation_pct", "Annual inflation (%)"
    ),
    "calendar_year_aggregation": ResultMetric(
        "cal_year", "aggregated_total", "Calendar-year total"
    ),
    "percentage_point_spread": ResultMetric("obs_date", "spread_pp", "Spread (percentage points)"),
}


def flag_text(row: dict[str, Any]) -> str | None:
    """Why an observation needs care, or None for a clean, published value."""
    reasons: list[str] = []
    if row.get("value") is None:
        reasons.append("value not available")
    if row.get("status_code"):
        reasons.append(f"StatCan status code {row['status_code']}")
    if row.get("symbol_code"):
        reasons.append(f"StatCan symbol code {row['symbol_code']}")
    return "; ".join(reasons) or None


def series_figure(series: Sequence[FetchedSeries]) -> go.Figure | None:
    """Line chart of the fetched series, or None when there is nothing to draw."""
    drawn = [s for s in series if s.rows][:MAX_SERIES]
    if not drawn:
        return None
    units = list(dict.fromkeys(s.unit or "" for s in drawn))
    shared = len(units) == 1
    fig = (
        go.Figure()
        if shared
        else make_subplots(
            rows=len(units), cols=1, shared_xaxes=True, vertical_spacing=0.08,
            subplot_titles=[u or "unitless" for u in units],
        )
    )  # fmt: skip

    for index, item in enumerate(drawn):
        colour = PALETTE[index]
        dates = [r.get("date") for r in item.rows]
        values = [r.get("value") for r in item.rows]
        panel = None if shared else units.index(item.unit or "") + 1
        _add(
            fig,
            go.Scatter(
                x=dates,
                y=values,
                name=item.name,
                mode="lines+markers",
                line={"width": 2, "color": colour},
                marker={"size": 6, "color": colour},
                hovertemplate=f"%{{x}}<br>%{{y}} {item.unit or ''}<extra>{item.name}</extra>",
                legendgroup=item.name,
            ),
            panel,
        )
        flagged = [(r, flag_text(r)) for r in item.rows]
        flagged = [(r, why) for r, why in flagged if why and r.get("value") is not None]
        if flagged:
            _add(
                fig,
                go.Scatter(
                    x=[r.get("date") for r, _ in flagged],
                    y=[r.get("value") for r, _ in flagged],
                    name=f"{item.name}: flagged",
                    mode="markers",
                    marker={
                        "size": 11, "symbol": "diamond-open", "color": FLAG_COLOUR,
                        "line": {"width": 2},
                    },
                    text=[why for _, why in flagged],
                    hovertemplate="%{x}<br>%{y}<br>%{text}<extra>flagged</extra>",
                    legendgroup=item.name,
                ),
                panel,
            )  # fmt: skip

    if shared and units[0]:
        fig.update_yaxes(title_text=units[0])
    _style(fig, height=380 if shared else 260 * len(units))
    return fig


def result_figure(analyses: Sequence[AnalysisResult]) -> go.Figure | None:
    """One chart of the headline metric when every analysis is the same time-series recipe.

    A comparison (GT-12: the same recipe on two series) becomes grouped bars, one colour per
    series in plan order; mixed recipes or non-time-series recipes return None.
    """
    recipes = {a.recipe for a in analyses}
    if len(recipes) != 1:
        return None
    metric = RESULT_METRICS.get(recipes.pop())
    if metric is None:
        return None
    fig = go.Figure()
    for index, analysis in enumerate(analyses[:MAX_SERIES]):
        rows = sorted(
            (r for r in analysis.artifact.rows if r.get(metric.y) is not None),
            key=lambda r: str(r.get(metric.x)),
        )
        if not rows:
            continue
        fig.add_trace(
            go.Bar(
                x=[_period(r.get(metric.x)) for r in rows],
                y=[r[metric.y] for r in rows],
                name=analysis.name,
                marker={"color": PALETTE[index]},
                hovertemplate=f"%{{x}}<br>%{{y}}<extra>{analysis.name}</extra>",
                text=[r[metric.y] for r in rows],
                texttemplate="%{text:,.2~f}",
                textposition="outside",
                cliponaxis=False,
            )
        )
    if not fig.data:
        return None
    fig.update_layout(barmode="group", bargap=0.45, bargroupgap=0.08)
    fig.update_xaxes(type="category")
    fig.update_yaxes(title_text=metric.title, zeroline=True, zerolinewidth=1)
    _style(fig, height=340)
    return fig


def _period(value: object) -> str:
    """``2026-08-01`` as ``2026-08``: monthly results are labelled by month, not by a day."""
    text = str(value)
    return text[:7] if len(text) == 10 and text.endswith("-01") else text


def _add(fig: go.Figure, trace: go.Scatter, panel: int | None) -> None:
    if panel is None:
        fig.add_trace(trace)
    else:
        fig.add_trace(trace, row=panel, col=1)


def _style(fig: go.Figure, *, height: int) -> None:
    fig.update_layout(
        height=height,
        margin={"l": 8, "r": 8, "t": 36, "b": 8},
        hovermode="x unified",
        showlegend=True,  # name the series even when there is only one
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0},
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.18)")
