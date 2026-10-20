"""Rebuild the GTA ground-truth benchmark (CAN-14) from official sources.

Every expected answer is computed from live Statistics Canada WDS and Bank of
Canada Valet responses, and every citation follows the two-tier Citation
Envelope agreed in PR #8 (see docs/CORE_DOCS_CITATION_STANDARDS_ACTIVITIES.md):

- Tier 1, Core Verification Tuple (strict pass/fail):
  table_id, vector_id, reference_period
- Tier 2, Metadata Enrichment (weighted scoring):
  coordinate, release_or_revision_date, bilingual_title, canonical_url

`CitationEnvelope` and `EvalType` are importable so downstream code (CAN-21
state schemas, CAN-24 Citation Verifier, CAN-41 DeepEval) can reuse the schema.

Usage (standard library only, Python 3.12+):
    python collaboration/benchmarks/build_ground_truth.py           # rewrite outputs
    python collaboration/benchmarks/build_ground_truth.py --check   # fail if sources drifted
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Literal

HERE = Path(__file__).resolve().parent
JSON_OUT = HERE / "gta_ground_truth_v1.json"
MD_OUT = HERE / "gta_ground_truth_v1.md"

WDS = "https://www150.statcan.gc.ca/t1/wds/rest/"
VALET = "https://www.bankofcanada.ca/valet/observations/"
TIMEOUT = 60


# ------------------------------------------------------- citation envelope

EvalType = Literal["numeric", "comparison", "refusal", "flag"]
"""How a question is graded.

numeric:    values must match within tolerance
comparison: a categorical answer (which / faster / higher) plus supporting values
refusal:    pass only if the agent declines to give the requested number
flag:       pass only if the agent states the stated problem (e.g. mismatched years)
"""


@dataclass(frozen=True)
class BilingualTitle:
    en: str
    fr: str


@dataclass(frozen=True)
class CoreVerificationTuple:
    """Tier 1: strict pass/fail. reference_period is `2025`, `2025-10`,
    `2025-01-30`, or an interval such as `2024-01/2025-12`."""

    table_id: str
    vector_id: str
    reference_period: str


@dataclass(frozen=True)
class MetadataEnrichment:
    """Tier 2: weighted scoring; missing fields lower the score but never fail an answer."""

    coordinate: str | None
    release_or_revision_date: str | None
    bilingual_title: BilingualTitle
    canonical_url: str


@dataclass(frozen=True)
class CitationEnvelope:
    publisher: str
    core: CoreVerificationTuple
    enrichment: MetadataEnrichment


# ---------------------------------------------------------------- sources


@dataclass(frozen=True)
class StatCanSeries:
    """One StatCan series, located by table and dimension member names."""

    product_id: int
    members: tuple[str, ...]
    latest_n: int


Frequency = Literal["annual", "monthly", "daily"]

# WDS frequencyCode -> period granularity
_FREQUENCIES: dict[int, Frequency] = {12: "annual", 6: "monthly", 1: "daily"}


@dataclass
class Series:
    key: str
    publisher: str
    table_id: str
    vector_id: str
    coordinate: str | None
    title: BilingualTitle
    canonical_url: str
    frequency: Frequency
    points: dict[str, float]  # API reference date (YYYY-MM-DD) -> value
    release_times: dict[str, str] = field(default_factory=dict)


STATCAN: dict[str, StatCanSeries] = {
    # CMHC average rents, two-bedroom, row + apartment structures of 3+ units
    "rent_2br_toronto": StatCanSeries(
        34100133,
        (
            "Toronto, Ontario",
            "Row and apartment structures of three units and over",
            "Two bedroom units",
        ),
        40,
    ),
    "rent_2br_oshawa": StatCanSeries(
        34100133,
        (
            "Oshawa, Ontario",
            "Row and apartment structures of three units and over",
            "Two bedroom units",
        ),
        10,
    ),
    # CMHC vacancy rates, row + apartment 3+ units, weighted average
    "vacancy_toronto": StatCanSeries(34100130, ("Toronto, Ontario",), 5),
    "vacancy_oshawa": StatCanSeries(34100130, ("Oshawa, Ontario",), 5),
    "vacancy_hamilton": StatCanSeries(34100130, ("Hamilton, Ontario",), 5),
    # CMHC housing starts, monthly (not seasonally adjusted)
    "starts_toronto": StatCanSeries(
        34100154, ("Toronto, Ontario", "Housing starts", "Total units"), 36
    ),
    # New housing price index, monthly
    "nhpi_toronto": StatCanSeries(
        18100205, ("Toronto, Ontario", "Total (house and land)"), 30
    ),
    # Canadian Income Survey: median after-tax income, all economic families and unattached persons
    "income_aftertax_toronto": StatCanSeries(
        11100190,
        (
            "Toronto, Ontario",
            "Median after-tax income",
            "Economic families and persons not in an economic family",
        ),
        8,
    ),
    # CPI annual averages (official annual table, base 2002=100)
    "cpi_annual_toronto_all": StatCanSeries(
        18100005, ("Toronto, Ontario", "All-items"), 4
    ),
    "cpi_annual_toronto_shelter": StatCanSeries(
        18100005, ("Toronto, Ontario", "Shelter"), 4
    ),
    "cpi_annual_toronto_rented": StatCanSeries(
        18100005, ("Toronto, Ontario", "Rented accommodation"), 4
    ),
    "cpi_annual_canada_shelter": StatCanSeries(18100005, ("Canada", "Shelter"), 4),
    "cpi_annual_canada_mortgage": StatCanSeries(
        18100005, ("Canada", "Mortgage interest cost"), 4
    ),
    # CPI monthly
    "cpi_monthly_toronto_all": StatCanSeries(
        18100004, ("Toronto, Ontario", "All-items"), 18
    ),
    "cpi_monthly_toronto_shelter": StatCanSeries(
        18100004, ("Toronto, Ontario", "Shelter"), 18
    ),
}

BOC_POLICY_RATE = "V39079"


def _post(endpoint: str, body: list[dict[str, Any]]) -> list[dict[str, Any]]:
    request = urllib.request.Request(
        WDS + endpoint,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.load(response)


def _table_id(product_id: int) -> str:
    s = str(product_id)
    return f"{s[0:2]}-{s[2:4]}-{s[4:8]}-01"


_metadata_cache: dict[int, dict[str, Any]] = {}


def _metadata(product_id: int) -> dict[str, Any]:
    if product_id not in _metadata_cache:
        _metadata_cache[product_id] = _post(
            "getCubeMetadata", [{"productId": product_id}]
        )[0]["object"]
    return _metadata_cache[product_id]


def _coordinate(meta: dict[str, Any], members: tuple[str, ...]) -> str:
    ids: list[int] = []
    for position, name in enumerate(members, start=1):
        dimension = next(
            d for d in meta["dimension"] if d["dimensionPositionId"] == position
        )
        member = next(
            (m for m in dimension["member"] if m["memberNameEn"] == name), None
        )
        if member is None:
            raise KeyError(
                f"{name!r} not found in dimension {position} of table {meta['productId']}"
            )
        ids.append(member["memberId"])
    return ".".join(str(i) for i in ids + [0] * (10 - len(ids)))


def fetch_statcan(key: str, spec: StatCanSeries) -> Series:
    meta = _metadata(spec.product_id)
    coordinate = _coordinate(meta, spec.members)
    data = _post(
        "getDataFromCubePidCoordAndLatestNPeriods",
        [
            {
                "productId": spec.product_id,
                "coordinate": coordinate,
                "latestN": spec.latest_n,
            }
        ],
    )[0]["object"]
    points: dict[str, float] = {}
    releases: dict[str, str] = {}
    for point in data["vectorDataPoint"]:
        if point["value"] is None:
            continue
        period = point["refPer"]
        points[period] = float(point["value"])
        releases[period] = point["releaseTime"]
    return Series(
        key=key,
        publisher="Statistics Canada",
        table_id=_table_id(spec.product_id),
        vector_id=f"v{data['vectorId']}",
        coordinate=coordinate,
        title=BilingualTitle(meta["cubeTitleEn"], meta["cubeTitleFr"]),
        canonical_url=f"https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid={spec.product_id}01",
        frequency=_FREQUENCIES[meta["frequencyCode"]],
        points=points,
        release_times=releases,
    )


def fetch_boc_policy_rate(start: str, end: str) -> Series:
    url = f"{VALET}{BOC_POLICY_RATE}/json?start_date={start}&end_date={end}"
    with urllib.request.urlopen(url, timeout=TIMEOUT) as response:
        payload = json.load(response)
    detail = payload["seriesDetail"][BOC_POLICY_RATE]
    points = {o["d"]: float(o[BOC_POLICY_RATE]["v"]) for o in payload["observations"]}
    return Series(
        key="boc_policy_rate",
        publisher="Bank of Canada",
        table_id="Valet",
        vector_id=BOC_POLICY_RATE,
        coordinate=None,
        title=BilingualTitle(detail["label"], "Cible du taux du financement à un jour"),
        canonical_url=f"https://www.bankofcanada.ca/valet/observations/{BOC_POLICY_RATE}",
        frequency="daily",
        points=points,
    )


# -------------------------------------------------------------- helpers


def pct_change(old: float, new: float) -> float:
    return round((new / old - 1) * 100, 1)


def _period(series: Series, ref_date: str) -> str:
    """Format an API reference date at the series' own granularity."""
    return {"annual": ref_date[:4], "monthly": ref_date[:7], "daily": ref_date}[
        series.frequency
    ]


def _envelope(series: Series, period: str, release: str | None) -> CitationEnvelope:
    return CitationEnvelope(
        publisher=series.publisher,
        core=CoreVerificationTuple(series.table_id, series.vector_id, period),
        enrichment=MetadataEnrichment(
            coordinate=series.coordinate,
            release_or_revision_date=release,
            bilingual_title=series.title,
            canonical_url=series.canonical_url,
        ),
    )


def cite(series: Series, *ref_dates: str) -> list[CitationEnvelope]:
    """One envelope per reference period used in the answer."""
    return [
        _envelope(series, _period(series, d), series.release_times.get(d))
        for d in ref_dates
    ]


def cite_range(series: Series, first: str, last: str) -> list[CitationEnvelope]:
    """One envelope for a contiguous span (e.g. 24 summed months)."""
    releases = [t for d, t in series.release_times.items() if first <= d <= last]
    period = f"{_period(series, first)}/{_period(series, last)}"
    return [_envelope(series, period, max(releases) if releases else None)]


def year(y: int) -> str:
    return f"{y}-01-01"


def month(y: int, m: int) -> str:
    return f"{y}-{m:02d}-01"


# ------------------------------------------------------------ questions


def build_questions(s: dict[str, Series]) -> list[dict[str, Any]]:
    q: list[dict[str, Any]] = []

    # --- A. GTA rental market -------------------------------------------
    r = s["rent_2br_toronto"]
    r24, r25 = r.points[year(2024)], r.points[year(2025)]
    q.append(
        {
            "id": "GT-01",
            "eval_type": "numeric",
            "category": "Rental market",
            "question": "What was the average monthly rent for a two-bedroom unit in the Toronto CMA in the October 2025 CMHC Rental Market Survey, and how much did it change from 2024?",
            "expected": {
                "rent_2025": r25,
                "rent_2024": r24,
                "change_dollars": r25 - r24,
                "change_pct": pct_change(r24, r25),
            },
            "tolerance": "Exact dollars; percentage ±0.1 pp",
            "citations": cite(r, year(2024), year(2025)),
            "traps": [
                "Asking rents from listing sites (Rentals.ca / Urbanation, ~$2,600+) are not CMHC survey rents; survey rents include sitting tenants under rent control.",
                "The survey is taken in October; the table labels it as the annual period '2025'.",
                "'Apartment structures of six units and over' is a different series with a different value.",
            ],
        }
    )

    v = s["vacancy_toronto"]
    q.append(
        {
            "id": "GT-02",
            "eval_type": "numeric",
            "category": "Rental market",
            "question": "What was the purpose-built rental vacancy rate in the Toronto CMA in 2025, and how does it compare to 2023?",
            "expected": {
                "vacancy_2025_pct": v.points[year(2025)],
                "vacancy_2024_pct": v.points[year(2024)],
                "vacancy_2023_pct": v.points[year(2023)],
                "change_2023_2025_pp": round(
                    v.points[year(2025)] - v.points[year(2023)], 1
                ),
            },
            "tolerance": "Exact to one decimal",
            "citations": cite(v, year(2023), year(2024), year(2025)),
            "traps": [
                "News coverage of CMHC's Fall 2024 report quotes Toronto at 2.2%-2.3% for 2024; this table (row + apartment, weighted) says 2.5%. The agent must not blend sources.",
                "The change must be expressed in percentage points, not percent.",
            ],
        }
    )

    o = s["rent_2br_oshawa"]
    o25 = o.points[year(2025)]
    q.append(
        {
            "id": "GT-03",
            "eval_type": "numeric",
            "category": "Rental market",
            "question": "In 2025, how did the average two-bedroom rent in the Oshawa CMA (Durham) compare with the Toronto CMA?",
            "expected": {
                "oshawa_2025": o25,
                "toronto_2025": r25,
                "gap_dollars": r25 - o25,
                "toronto_premium_pct": pct_change(o25, r25),
            },
            "tolerance": "Exact dollars; percentage ±0.1 pp",
            "citations": [*cite(o, year(2025)), *cite(r, year(2025))],
            "traps": [
                "Durham Region is mostly covered by the Oshawa CMA; Peel, York and Halton fall inside the Toronto CMA and have no separate CMA series in this table.",
            ],
        }
    )

    vac = {
        name: s[f"vacancy_{name}"].points[year(2025)]
        for name in ("toronto", "oshawa", "hamilton")
    }
    highest = max(vac, key=lambda k: vac[k])
    q.append(
        {
            "id": "GT-04",
            "eval_type": "comparison",
            "category": "Rental market",
            "question": "Among the Toronto, Oshawa and Hamilton CMAs, which had the highest rental vacancy rate in 2025?",
            "expected": {"answer": highest.capitalize(), "vacancy_2025_pct": vac},
            "tolerance": "Correct CMA; rates exact to one decimal",
            "citations": [
                c
                for n in ("toronto", "oshawa", "hamilton")
                for c in cite(s[f"vacancy_{n}"], year(2025))
            ],
            "traps": [
                "Oshawa and Hamilton differ by only 0.1 pp; an agent that guesses or rounds will get this wrong.",
            ],
        }
    )

    # --- B. Supply & prices ---------------------------------------------
    st = s["starts_toronto"]
    months_24 = [month(2024, m) for m in range(1, 13)]
    months_25 = [month(2025, m) for m in range(1, 13)]
    starts_24 = int(sum(st.points[m] for m in months_24))
    starts_25 = int(sum(st.points[m] for m in months_25))
    q.append(
        {
            "id": "GT-05",
            "eval_type": "numeric",
            "category": "Supply & prices",
            "question": "How many housing units were started in the Toronto CMA in calendar year 2025, and how does that compare with 2024?",
            "expected": {
                "starts_2025": starts_25,
                "starts_2024": starts_24,
                "change_pct": pct_change(starts_24, starts_25),
            },
            "tolerance": "Exact unit counts; percentage ±0.1 pp",
            "citations": cite_range(st, months_24[0], months_25[-1]),
            "computation": "Sum of the 12 monthly (not seasonally adjusted) values for each year.",
            "traps": [
                "The seasonally adjusted annual rate (SAAR) series is a different measure and must not be summed or quoted as an annual total.",
            ],
        }
    )

    n = s["nhpi_toronto"]
    n_dec24, n_dec25 = n.points[month(2024, 12)], n.points[month(2025, 12)]
    q.append(
        {
            "id": "GT-06",
            "eval_type": "numeric",
            "category": "Supply & prices",
            "question": "How did new home prices in the Toronto CMA change between December 2024 and December 2025?",
            "expected": {
                "nhpi_dec_2024": n_dec24,
                "nhpi_dec_2025": n_dec25,
                "change_pct": pct_change(n_dec24, n_dec25),
            },
            "tolerance": "±0.1 pp; direction must be correct",
            "citations": cite(n, month(2024, 12), month(2025, 12)),
            "traps": [
                "The New Housing Price Index covers new homes from builders only; resale prices (TRREB / CREA) are a different measure.",
                "The index is a price index (base December 2016 = 100), not a dollar price.",
            ],
        }
    )

    # --- C. Rent vs income ----------------------------------------------
    inc = s["income_aftertax_toronto"]
    inc19, inc24 = inc.points[year(2019)], inc.points[year(2024)]
    r19 = r.points[year(2019)]
    q.append(
        {
            "id": "GT-07",
            "eval_type": "numeric",
            "category": "Rent vs income",
            "question": "In 2024, what share of the Toronto CMA's median after-tax income would a year of average two-bedroom rent take?",
            "expected": {
                "annual_rent_2024": r24 * 12,
                "median_aftertax_income_2024": inc24,
                "rent_share_pct": round(r24 * 12 / inc24 * 100, 1),
            },
            "tolerance": "±0.1 pp",
            "citations": [*cite(r, year(2024)), *cite(inc, year(2024))],
            "traps": [
                "Use the same year for rent and income (2024 is the latest income year); pairing 2025 rent with 2024 income must be flagged.",
                "The income series covers all families and unattached persons, renters and owners alike; renter incomes are lower, so this understates renters' burden.",
            ],
        }
    )

    q.append(
        {
            "id": "GT-08",
            "eval_type": "numeric",
            "category": "Rent vs income",
            "question": "Between 2019 and 2024, how did average two-bedroom rent growth in the Toronto CMA compare with growth in median after-tax income?",
            "expected": {
                "rent_2019": r19,
                "rent_2024": r24,
                "rent_growth_pct": pct_change(r19, r24),
                "income_2019": inc19,
                "income_2024": inc24,
                "income_growth_pct": pct_change(inc19, inc24),
            },
            "tolerance": "±0.1 pp on each rate",
            "citations": [
                *cite(r, year(2019), year(2024)),
                *cite(inc, year(2019), year(2024)),
            ],
            "traps": [
                "Both series are in current (nominal) dollars; the agent should not mix nominal and inflation-adjusted figures.",
            ],
        }
    )

    q.append(
        {
            "id": "GT-09",
            "eval_type": "flag",
            "category": "Rent vs income",
            "question": "Using median household income from the 2021 Census, what share of income does the 2025 average two-bedroom rent in Toronto represent?",
            "expected": {
                "behaviour": "Flag the vintage mismatch before (or instead of) computing.",
                "must_mention": [
                    "2021 Census income refers to calendar year 2020, five years before the 2025 rent figure.",
                    "A same-year comparison is available: 2024 Canadian Income Survey (see GT-07).",
                ],
            },
            "tolerance": "Pass only if the mismatch is stated; a bare percentage fails",
            "citations": [*cite(inc, year(2024)), *cite(r, year(2025))],
            "traps": [
                "Census 2021 median household after-tax income for Toronto ($85,000, income year 2020) produces a plausible-looking ~28.9% that silently mixes 2020 income with 2025 rent.",
            ],
        }
    )

    # --- D. Inflation & rates -------------------------------------------
    ra = s["cpi_annual_toronto_rented"]
    aa = s["cpi_annual_toronto_all"]
    q.append(
        {
            "id": "GT-10",
            "eval_type": "comparison",
            "category": "Inflation & rates",
            "question": "In 2025, did the cost of rented accommodation in Toronto rise faster or slower than overall consumer prices? Give both annual inflation rates.",
            "expected": {
                "rented_accommodation_pct": pct_change(
                    ra.points[year(2024)], ra.points[year(2025)]
                ),
                "all_items_pct": pct_change(
                    aa.points[year(2024)], aa.points[year(2025)]
                ),
                "answer": "Faster",
            },
            "tolerance": "±0.1 pp on each rate; faster/slower must be correct",
            "citations": [
                *cite(ra, year(2024), year(2025)),
                *cite(aa, year(2024), year(2025)),
            ],
            "traps": [
                "StatCan publishes no city-level 'Rent' index for Toronto, only 'Rented accommodation'.",
                "The national CPI rent figure is frequently mis-attributed to Toronto.",
                "December-to-December comparisons differ from annual averages.",
            ],
        }
    )

    ts, cs = s["cpi_annual_toronto_shelter"], s["cpi_annual_canada_shelter"]
    q.append(
        {
            "id": "GT-11",
            "eval_type": "comparison",
            "category": "Inflation & rates",
            "question": "How did shelter inflation in Toronto in 2025 compare with shelter inflation for Canada as a whole?",
            "expected": {
                "toronto_shelter_pct": pct_change(
                    ts.points[year(2024)], ts.points[year(2025)]
                ),
                "canada_shelter_pct": pct_change(
                    cs.points[year(2024)], cs.points[year(2025)]
                ),
                "answer": "Toronto was lower than Canada",
            },
            "tolerance": "±0.1 pp on each rate; comparison must be correct",
            "citations": [
                *cite(ts, year(2024), year(2025)),
                *cite(cs, year(2024), year(2025)),
            ],
            "traps": [
                "The common assumption that Toronto shelter costs always rise fastest is wrong for 2025."
            ],
        }
    )

    ms, ma = s["cpi_monthly_toronto_shelter"], s["cpi_monthly_toronto_all"]
    a25, a26 = month(2025, 8), month(2026, 8)
    q.append(
        {
            "id": "GT-12",
            "eval_type": "comparison",
            "category": "Inflation & rates",
            "question": "In August 2026, how did shelter prices in Toronto change year over year, compared with overall consumer prices?",
            "expected": {
                "shelter_yoy_pct": pct_change(ms.points[a25], ms.points[a26]),
                "all_items_yoy_pct": pct_change(ma.points[a25], ma.points[a26]),
                "answer": "Shelter prices fell while overall prices rose",
            },
            "tolerance": "±0.1 pp on each rate; the sign of shelter must be correct",
            "citations": [*cite(ms, a25, a26), *cite(ma, a25, a26)],
            "traps": [
                "A model answering from habit will say shelter rose; the published figure is a decline."
            ],
        }
    )

    boc = s["boc_policy_rate"]
    days_2025 = sorted(d for d in boc.points if d.startswith("2025"))
    changes = []
    previous = boc.points[max(d for d in boc.points if d < "2025-01-01")]
    start_rate = previous
    for d in days_2025:
        if boc.points[d] != previous:
            changes.append({"effective_date": d, "from": previous, "to": boc.points[d]})
            previous = boc.points[d]
    q.append(
        {
            "id": "GT-13",
            "eval_type": "numeric",
            "category": "Inflation & rates",
            "question": "How many times did the Bank of Canada change its policy interest rate in 2025, and where did the rate start and end the year?",
            "expected": {
                "number_of_changes": len(changes),
                "rate_start_2025_pct": start_rate,
                "rate_end_2025_pct": boc.points[days_2025[-1]],
                "changes": changes,
            },
            "tolerance": "Exact count and rates",
            "citations": cite_range(boc, days_2025[0], days_2025[-1]),
            "traps": [
                "Valet dates are effective dates, one business day after each announcement (e.g. announced 29 January, effective 30 January).",
                "Holds (no change) at scheduled announcements must not be counted as changes.",
            ],
        }
    )

    # --- E. Unanswerable / refusal --------------------------------------
    cm = s["cpi_annual_canada_mortgage"]
    q.append(
        {
            "id": "GT-14",
            "eval_type": "refusal",
            "category": "Unanswerable",
            "question": "What was mortgage interest cost inflation in Toronto in 2025?",
            "expected": {
                "behaviour": "State that StatCan does not publish a Toronto mortgage interest cost index; offer the national figure instead.",
                "canada_mortgage_interest_cost_pct": pct_change(
                    cm.points[year(2024)], cm.points[year(2025)]
                ),
            },
            "tolerance": "Pass only if the Toronto figure is declined; national figure ±0.1 pp",
            "citations": cite(cm, year(2024), year(2025)),
            "traps": [
                "Toronto CPI is published for only 6 aggregates (All-items, Shelter, Rented and Owned accommodation, Water/fuel/electricity, All-items 1992=100). Any Toronto mortgage figure is fabricated."
            ],
        }
    )

    first_year = min(r.points)
    q.append(
        {
            "id": "GT-15",
            "eval_type": "refusal",
            "category": "Unanswerable",
            "question": "What was the average two-bedroom rent in the Toronto CMA in 1985?",
            "expected": {
                "behaviour": "Decline: the official CMHC series for Toronto does not cover 1985.",
                "earliest_available_period": _period(r, first_year),
            },
            "tolerance": "Pass only if no number is given for 1985",
            "citations": cite(r, first_year),
            "traps": [
                "Plausible-sounding historical rents are a classic hallucination; the series starts in 1992."
            ],
        }
    )

    return q


# ---------------------------------------------------------------- output


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# GTA Housing Ground-Truth Benchmark v1 (`CAN-14`)",
        "",
        "> **Generated file. Do not edit by hand.** Run `python collaboration/benchmarks/build_ground_truth.py` to rebuild from official sources.",
        "",
        f"- **Questions:** {len(payload['questions'])}",
        f"- **Built:** {payload['built_on']}",
        "- **Sources:** Statistics Canada WDS, Bank of Canada Valet (live API responses, no news coverage)",
        "- **Machine-readable copy:** [`gta_ground_truth_v1.json`](gta_ground_truth_v1.json) (for `CAN-15` baseline and `CAN-41` DeepEval)",
        "",
        "## Target Systems",
        "",
        "The benchmark is model-agnostic. It measures the industry baseline problem (frontier LLMs answering Canadian data questions), not one vendor. Typical runs compare:",
        "",
        "1. Frontier LLMs **without tools**, from any vendor",
        "2. The same models with an existing open-source StatCan MCP server",
        "3. The same models with CanData-MCP",
        "",
        "Every run must record the **exact model ID and run date**, since model versions change faster than this benchmark.",
        "",
        "## Scoring",
        "",
        "Citations follow the two-tier **Citation Envelope** from PR #8 ([`docs/CORE_DOCS_CITATION_STANDARDS_ACTIVITIES.md`](../../docs/CORE_DOCS_CITATION_STANDARDS_ACTIVITIES.md)):",
        "",
        "1. **Tier 1, Core Verification Tuple (strict pass/fail):** `table_id`, `vector_id`, `reference_period`, plus the value(s) within tolerance.",
        "2. **Tier 2, Metadata Enrichment (weighted):** `coordinate`, `release_or_revision_date`, `bilingual_title`, `canonical_url`. Missing fields lower the score but never fail the answer.",
        "",
        "Each question has an `eval_type`:",
        "",
        "| eval_type | Passes when |",
        "| :--- | :--- |",
        "| `numeric` | Values match within tolerance |",
        "| `comparison` | The categorical answer (which / faster / lower) is right and supporting values match |",
        "| `refusal` | The agent declines to give the requested number (a fabricated number fails) |",
        "| `flag` | The agent states the problem (e.g. mismatched data years) before or instead of answering |",
        "",
        "## CI Policy",
        "",
        "- **Pull requests:** run only the offline tests in `tests/test_ground_truth_benchmark.py` against this committed JSON. No network calls, so API outages can't block a PR.",
        "- **Scheduled or manual:** run `build_ground_truth.py --check` to detect official revisions. If it reports drift, rebuild and review the diff in a normal PR.",
        "",
        "## Questions",
        "",
        "| ID | eval_type | Category | Question |",
        "| :--- | :--- | :--- | :--- |",
    ]
    for q in payload["questions"]:
        lines.append(
            f"| [{q['id']}](#{q['id'].lower()}) | `{q['eval_type']}` | {q['category']} | {q['question']} |"
        )
    lines.append("")

    for q in payload["questions"]:
        lines += [
            "---",
            "",
            f"## {q['id']}",
            "",
            f"**Category:** {q['category']} · **eval_type:** `{q['eval_type']}`",
            "",
            f"> {q['question']}",
            "",
            "**Expected:**",
            "",
        ]
        for k, v in q["expected"].items():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                lines.append(f"- `{k}`:")
                lines += [
                    f"  - {', '.join(f'{ik}: {iv}' for ik, iv in item.items())}"
                    for item in v
                ]
            elif isinstance(v, list):
                lines.append(f"- `{k}`:")
                lines += [f"  - {item}" for item in v]
            else:
                lines.append(f"- `{k}`: {v}")
        lines += ["", f"**Tolerance:** {q['tolerance']}", ""]
        if "computation" in q:
            lines += [f"**Computation:** {q['computation']}", ""]
        lines += [
            "**Citation envelopes:**",
            "",
            "| table_id | vector_id | reference_period | coordinate | release_or_revision_date |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ]
        for c in q["citations"]:
            core, extra = c["core"], c["enrichment"]
            coordinate = f"`{extra['coordinate']}`" if extra["coordinate"] else "n/a"
            lines.append(
                f"| [{core['table_id']}]({extra['canonical_url']}) | `{core['vector_id']}` | `{core['reference_period']}` | {coordinate} | {extra['release_or_revision_date'] or 'n/a'} |"
            )
        lines += ["", "**Traps:**", ""]
        lines += [f"- {t}" for t in q["traps"]]
        lines.append("")
    return "\n".join(lines)


def _jsonable(value: Any) -> Any:
    """Convert dataclasses (CitationEnvelope and friends) to plain dicts."""
    return json.loads(json.dumps(value, default=asdict, ensure_ascii=False))


def build() -> dict[str, Any]:
    series = {key: fetch_statcan(key, spec) for key, spec in STATCAN.items()}
    series["boc_policy_rate"] = fetch_boc_policy_rate("2024-12-01", "2025-12-31")
    return _jsonable(
        {
            "benchmark": "GTA housing ground truth",
            "version": 1,
            "built_on": date.today().isoformat(),
            "questions": build_questions(series),
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if expected answers differ from the committed JSON",
    )
    args = parser.parse_args()

    payload = build()

    if args.check:
        committed = json.loads(JSON_OUT.read_text())
        old = {q["id"]: q["expected"] for q in committed["questions"]}
        drifted = [
            q["id"] for q in payload["questions"] if old.get(q["id"]) != q["expected"]
        ]
        if drifted:
            print(
                f"Ground truth drifted for: {', '.join(drifted)}. Re-run without --check and review."
            )
            return 1
        print("Ground truth matches official sources.")
        return 0

    JSON_OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    MD_OUT.write_text(render_markdown(payload) + "\n")
    print(
        f"Wrote {JSON_OUT.name} and {MD_OUT.name} ({len(payload['questions'])} questions)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
