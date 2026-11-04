"""Typed tool registry and plan validator for the Supervisor (CAN-22).

The planner proposes steps; nothing runs until ``validate_plan`` has checked every one against
this registry. Fetch steps load an official series into a named data slot. Analyst steps run a
Data Analyst (CAN-23) recipe over slots that earlier fetch steps filled. Identifiers the model
could get wrong are not taken from the model: an analyst step's ``series_id`` is copied from the
fetch step that filled its slot, and a planner can require every StatCan vector to be one its
discovery calls confirmed.

Recipes that would need the model to type numbers (``multi_year_cagr``), free-form SQL, or
inputs a fetch step cannot produce (``cross_geography_ranking``) are deliberately not exposed.
"""

from __future__ import annotations

import calendar
import json
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Annotated, Any, Final, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, ValidationError, model_validator

from candata_agent.state import PlanStep, QueryPlan
from candata_agent.supervisor.guardrails import Objective, StepDescription

DATA_FETCHER: Final = "data_fetcher"
DATA_ANALYST: Final = "data_analyst"
MAX_STEPS: Final = 12

DataSlot = Literal["series_table", "table_a", "table_b", "rent_table", "income_table"]


def _real_date(period: str) -> str:
    if len(period) == 10:
        try:
            date.fromisoformat(period)
        except ValueError:
            raise ValueError(f"{period} is not a calendar date") from None
    return period


Period = Annotated[
    str,
    Field(pattern=r"^\d{4}(-(0[1-9]|1[0-2])(-(0[1-9]|[12]\d|3[01]))?)?$"),
    AfterValidator(_real_date),
]


class _Args(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class FetchStatCanArgs(_Args):
    """Load one StatCan vector between two reference periods (inclusive) into a slot."""

    vector_id: Annotated[str, Field(pattern=r"^v[1-9]\d*$")]
    start: Period
    end: Period
    into: DataSlot = "series_table"

    @model_validator(mode="after")
    def _ordered(self) -> FetchStatCanArgs:
        _check_order(self.start, self.end)
        return self


class FetchValetArgs(_Args):
    """Load one Bank of Canada Valet series between two dates (inclusive) into a slot."""

    series_id: Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{1,63}$")]
    start: Period
    end: Period
    into: DataSlot = "series_table"

    @model_validator(mode="after")
    def _ordered(self) -> FetchValetArgs:
        _check_order(self.start, self.end)
        return self


class _SingleSeriesArgs(_Args):
    """A recipe over one series; ``slot`` says which filled slot to read."""

    slot: DataSlot = "series_table"


class AnnualInflationArgs(_SingleSeriesArgs):
    expected_periods: Annotated[int, Field(ge=1, le=366)] = 12


class YoYArgs(_SingleSeriesArgs):
    lag: Annotated[int, Field(ge=1, le=120)] | None = None
    interval_years: Annotated[int, Field(ge=1, le=50)] | None = None


class SpreadArgs(_Args):
    series_a_name: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")] = "series_a"
    series_b_name: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")] = "series_b"


class NoArgs(_Args):
    pass


class CalendarYearArgs(_SingleSeriesArgs):
    agg_func: Literal["SUM", "AVG", "MIN", "MAX"] = "SUM"
    expected_periods: Annotated[int, Field(ge=1, le=366)] = 12


class RegimeChangeArgs(_SingleSeriesArgs):
    year: Annotated[int, Field(ge=1900, le=2100)]


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    agent: str
    description: str
    args: type[_Args]
    reads: tuple[DataSlot, ...] = ()  # two-series recipes; single-series ones read their ``slot``


TOOLS: Final[Mapping[str, ToolSpec]] = {
    spec.name: spec
    for spec in (
        ToolSpec(
            "fetch_statcan_vector",
            DATA_FETCHER,
            "Load a StatCan vector (e.g. v3823103) for a period range into a data slot.",
            FetchStatCanArgs,
        ),
        ToolSpec(
            "fetch_valet_series",
            DATA_FETCHER,
            "Load a Bank of Canada Valet series (e.g. V39079) for a date range into a slot.",
            FetchValetArgs,
        ),
        ToolSpec(
            "annual_inflation_rate",
            DATA_ANALYST,
            "Annual % change of the calendar-year average of a monthly index in one slot.",
            AnnualInflationArgs,
        ),
        ToolSpec(
            "yoy_point_to_point",
            DATA_ANALYST,
            "Change against the same period a year (or lag) earlier, for one slot.",
            YoYArgs,
        ),
        ToolSpec(
            "percentage_point_spread",
            DATA_ANALYST,
            "Difference in percentage points and basis points between table_a and table_b.",
            SpreadArgs,
            ("table_a", "table_b"),
        ),
        ToolSpec(
            "affordability_burden_ratio",
            DATA_ANALYST,
            "A year of monthly rent (rent_table) as a % of annual income (income_table).",
            NoArgs,
            ("rent_table", "income_table"),
        ),
        ToolSpec(
            "calendar_year_aggregation",
            DATA_ANALYST,
            "Calendar-year SUM/AVG/MIN/MAX of a monthly series in a slot; partial years -> null.",
            CalendarYearArgs,
        ),
        ToolSpec(
            "discrete_regime_change_counter",
            DATA_ANALYST,
            "Count level changes in one slot within one calendar year (e.g. policy rate).",
            RegimeChangeArgs,
        ),
    )
}


class DraftStep(BaseModel):
    """One step as the planner proposes it: a tool name and its arguments as JSON.

    ``description`` is shown to users, so it passes the CAN-43 output validator: no figures,
    links, markup or hidden characters.
    """

    model_config = ConfigDict(frozen=True)

    tool: str
    args_json: str
    description: StepDescription


class PlanDraft(BaseModel):
    model_config = ConfigDict(frozen=True)

    objective: Objective
    steps: tuple[DraftStep, ...]


class PlanValidationError(ValueError):
    """The draft plan breaks one or more rules; ``problems`` lists every one of them."""

    def __init__(self, problems: Sequence[str]) -> None:
        self.problems = tuple(problems)
        super().__init__("invalid plan: " + "; ".join(self.problems))


def validate_plan(
    draft: PlanDraft, *, confirmed_vectors: Collection[str] | None = None
) -> QueryPlan:
    """Check a draft against the registry and return an executable ``QueryPlan``.

    ``confirmed_vectors`` is the set of StatCan vector IDs the planner's discovery calls returned;
    when given, any other vector is rejected (a well-formed guess would fetch the wrong series).
    ``None`` skips the check for plans that were not discovered by a model.

    Raises ``PlanValidationError`` listing every problem, so a planner can fix them in one turn.
    """
    problems: list[str] = []
    if not draft.objective.strip():
        problems.append("objective is empty")
    if not 1 <= len(draft.steps) <= MAX_STEPS:
        problems.append(f"a plan needs 1 to {MAX_STEPS} steps, got {len(draft.steps)}")

    filled: dict[str, str] = {}  # slot -> identifier of the series loaded into it
    steps: list[PlanStep] = []
    for index, draft_step in enumerate(draft.steps, start=1):
        label = f"step {index} ({draft_step.tool})"
        spec = TOOLS.get(draft_step.tool)
        if spec is None:
            problems.append(f"{label}: unknown tool; use one of {sorted(TOOLS)}")
            continue
        try:
            raw: object = json.loads(draft_step.args_json or "{}")
        except json.JSONDecodeError as error:
            problems.append(f"{label}: args_json is not valid JSON ({error.msg})")
            continue
        if not isinstance(raw, dict):
            problems.append(f"{label}: args_json must be a JSON object")
            continue
        try:
            parsed = spec.args.model_validate(raw)
        except ValidationError as error:
            problems.extend(f"{label}: {_describe(e)}" for e in error.errors())
            continue

        tool_args: dict[str, Any] = parsed.model_dump(exclude_none=True)
        if isinstance(parsed, FetchStatCanArgs | FetchValetArgs):
            if parsed.into in filled:
                problems.append(
                    f"{label}: slot '{parsed.into}' is already filled by {filled[parsed.into]}; "
                    "each slot holds one series"
                )
            source = parsed.vector_id if isinstance(parsed, FetchStatCanArgs) else parsed.series_id
            if (
                isinstance(parsed, FetchStatCanArgs)
                and confirmed_vectors is not None
                and source not in confirmed_vectors
            ):
                problems.append(
                    f"{label}: vector {source} was not returned by lookup_series in this "
                    "conversation; look it up before using it"
                )
            filled[parsed.into] = source
        else:
            reads = (parsed.slot,) if isinstance(parsed, _SingleSeriesArgs) else spec.reads
            missing = [slot for slot in reads if slot not in filled]
            if missing:
                problems.append(
                    f"{label}: no earlier fetch step fills {', '.join(missing)}; "
                    "add fetch steps with matching 'into' before this step"
                )
                continue
            # The analyst cites the series it was handed, never an ID the model typed.
            tool_args["series_id"] = filled[reads[0]]

        steps.append(
            PlanStep(
                step_id=index,
                description=draft_step.description.strip() or spec.description,
                assigned_agent=spec.agent,
                tool_name=spec.name,
                tool_args=tool_args,
            )
        )

    if problems:
        raise PlanValidationError(problems)
    return QueryPlan(
        objective=draft.objective.strip(),
        steps=tuple(steps),
        active_step_id=steps[0].step_id,
    )


def period_bounds(start: str, end: str) -> tuple[str, str]:
    """Expand partial ISO periods to inclusive day bounds (``2025`` -> 2025-01-01..2025-12-31).

    Guardrail 8: never compare variable-length date strings directly.
    """
    return _first_day(start), _last_day(end)


def _first_day(period: str) -> str:
    year, month, day = (period.split("-") + ["01", "01"])[:3]
    return f"{year}-{month}-{day}"


def _last_day(period: str) -> str:
    parts = period.split("-")
    if len(parts) == 3:
        return period
    year = int(parts[0])
    month = int(parts[1]) if len(parts) == 2 else 12
    return f"{year:04d}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"


def _check_order(start: str, end: str) -> None:
    first, last = period_bounds(start, end)
    if first > last:  # both are full YYYY-MM-DD here, so string order is date order
        raise ValueError(f"start {start} is after end {end}")


def _describe(error: Mapping[str, Any]) -> str:
    location = ".".join(str(part) for part in error.get("loc", ())) or "args"
    return f"{location}: {error.get('msg', 'invalid value')}"
