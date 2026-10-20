# CAN-12: Async Bank of Canada Valet API Client

**Linear:** BEN-11 · **Branch:** `feat/CAN-12-boc-valet-client` · **Sprint:** 1 · **Owners:** Yassir / Benjamin

---

## 1. Executive Summary

CanData-MCP needs official Bank of Canada figures (policy rate, CPI and core-inflation measures) that carry a verifiable citation. CAN-12 delivers an async, read-only client for the [Valet API](https://www.bankofcanada.ca/valet/docs) in `packages/candata-mcp`, a small citation model that matches the two-tier Citation Envelope from PR #8, and the project's first `pyproject.toml` so the pre-flight commands in `AGENTS.md` can run.

One acceptance criterion is only partly achievable: the task asks for "series publication/revision metadata", and **Valet does not publish it** (see section 4). The client records when a figure was fetched instead and leaves the revision date empty.

---

## 2. Deliverables

| Path | Purpose |
|---|---|
| `packages/candata-mcp/src/candata_mcp/connectors/boc_valet.py` | `ValetClient` and its result types |
| `packages/candata-mcp/src/candata_mcp/citation.py` | Frozen dataclasses for the Citation Envelope |
| `tests/connectors/test_boc_valet.py` | 29 offline tests plus 1 opt-in live test (`pytest -m live`) |
| `tests/fixtures/valet/` | Real Valet responses saved on 2026-10-19 |
| `pyproject.toml`, `uv.lock` | Python 3.12+, `httpx`; dev tools `pytest`, `pytest-asyncio`, `respx`, `ruff`, `pyright` |

### 2.1 Client API

| Method | Returns |
|---|---|
| `get_series(series_id)` | `SeriesDetail`: label, description, frequency, unit, date format, URL |
| `get_observations(series_id, start_date=, end_date=, recent=)` | `ObservationSet`, oldest first |
| `get_policy_rate(...)` | Observations for `V39079` (overnight rate target) |
| `get_cpi(measure, ...)` | Observations for one of the `CPI_SERIES` measures |
| `get_group(name)` / `list_groups()` | Group members and group discovery |

`CPI_SERIES` covers the nine members of the `CPI_MONTHLY` group: `total`, `total_sa`, `yoy`, `xfet`, `cpiw`, `cpix`, `median`, `trim`, `common`.

### 2.2 What every result carries

`ObservationSet` holds the series details, the observations (`date`, `value`; `value` is `None` when Valet leaves it blank), and `fetched_at`, taken from the server's HTTP `Date` header. `ObservationSet.citation()` returns a `CitationEnvelope`:

| Envelope field | Value for Valet |
|---|---|
| `core.table_id` | `"Valet"` (same as CAN-14) |
| `core.vector_id` | Valet series name, e.g. `V39079` |
| `core.reference_period` | `2025-10-30`, `2026-09`, or an interval `start/end`; granularity follows the series' `dateFormat` |
| `enrichment.coordinate` | `None` (not a StatCan concept) |
| `enrichment.release_or_revision_date` | `None` (not published by Valet) |
| `enrichment.bilingual_title` | `en` from Valet; `fr` from `FRENCH_TITLES` (currently only `V39079`: "Taux cible du financement à un jour"), otherwise `None` |
| `enrichment.canonical_url` | `https://www.bankofcanada.ca/valet/observations/<series>` |

### 2.3 Errors and input checks

All errors derive from `ValetError`: `ValetNotFoundError` (404), `ValetHTTPError` (other error statuses, carries `status_code` and Valet's own message), `ValetRequestError` (timeouts and connection failures after retries), `ValetResponseError` (200 with an unexpected body or a non-numeric value). Timeouts, connection errors and 429/5xx are retried with exponential backoff (2 retries by default). Series names are validated before any request, `recent` cannot be combined with dates, and dates must be ISO `YYYY-MM-DD`.

---

## 3. Risks and Traps

| Risk | Handling |
|---|---|
| Valet returns `recent=N` newest first but date ranges oldest first | The client always sorts oldest first (tested) |
| Valet dates are *effective* dates, one business day after an announcement (announced 2025-01-29, effective 2025-01-30) | Documented here; values are reported as published |
| Policy-rate holds are not changes | Left to callers; the client returns raw observations |
| A figure can be revised after it is read | `fetched_at` pins when it was read; Valet gives no revision date to compare against |
| Blank observation values | Returned as `None`, never as `0` |
| Rate limits and availability of a public API | Bounded retries with backoff; no caching yet |
| **This package is mirrored publicly** by `publish-mcp-server.yml` under the commit author's name | Public-API data only in fixtures; no secrets |

---

## 4. Known Gaps and Open Questions

Resolved in review on [PR #13](https://github.com/neobenjax/Canadian-Open-Data-Agentic-Platform/pull/13) (items 1-2) or still open (item 3). Items 4-5 are approved as written.

1. **Inflation target (resolved).** The 2% target is a policy framework agreement, not a Valet series. `boc_valet.py` exposes `INFLATION_TARGET_PCT = 2.0` and `INFLATION_TARGET_RANGE = (1.0, 3.0)` as documented constants, with the Bank's framework URL. The current agreement runs to the end of 2026; re-verify when the renewal is announced.
2. **Revision metadata and French titles (resolved).** Valet publishes no publication or revision timestamp, no `Last-Modified` header, and rejects `?lang=fr`. `release_or_revision_date` stays `None` (`fetched_at` records when it was read). French titles come from the sourced `FRENCH_TITLES` table (`V39079` only) and are `None` for any other series.
3. **Where the shared citation model lives (open).** `citation.py` mirrors `CitationEnvelope` from CAN-14 (`collaboration/benchmarks/build_ground_truth.py`, PR #9, since merged). Samir proposes a Pydantic v2 model in `packages/candata-mcp`. It differs in one place: `BilingualTitle.fr` may be `None`. If the team moves the model into this package, `citation.py` is the only file to replace.
4. **`pyproject.toml` ownership (approved).** None existed on `main`; CAN-51 (Sprint 5) covers packaging. This PR adds a minimal root file, and CAN-11 will build on it.
5. **Ruff scope.** `uv run ruff check .` reported 165 findings in existing files (`scripts/sync_tasks.py` alone has 114). Those six files are listed in `extend-exclude` in `pyproject.toml` so the command passes for the code that is clean. Remove each entry as the file is cleaned.

---

## 5. Verification and Status

Run on Windows, Python 3.13, `uv 0.13.1`, 2026-10-19.

| Check | Result |
|---|---|
| `uv run ruff check .` | All checks passed |
| `uv run pytest` | 37 passed, 1 deselected (live) |
| `uv run pytest -m live` | 1 passed against the real API |
| `uv run pyright` | 0 errors, 0 warnings (strict on `packages/candata-mcp/src`) |

**Cross-check against CAN-14.** Using the client for 2025 returned the same four policy-rate changes recorded in the CAN-14 ground truth (GT-13): 2025-01-30 (3.25 to 3.00), 2025-03-13 (to 2.75), 2025-09-18 (to 2.50), 2025-10-30 (to 2.25). The citation's `reference_period` was `2025-01-01/2025-12-31`, identical to GT-13.

**To reproduce:**
```bash
uv run ruff check .
uv run pytest
uv run pyright
uv run pytest -m live   # optional, needs network
```

**Status:** implemented and verified; the open items in section 4 remain.

**Links:** [`TASKS.md`](../TASKS.md) (CAN-12), [`CORE_DOCS_CITATION_STANDARDS_ACTIVITIES.md`](CORE_DOCS_CITATION_STANDARDS_ACTIVITIES.md), [CAN-14 benchmark PR #9](https://github.com/neobenjax/Canadian-Open-Data-Agentic-Platform/pull/9).
