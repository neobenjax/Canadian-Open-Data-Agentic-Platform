# CAN-26: Bilingual Metadata Mapping and Data Lineage

**Linear:** BEN-21 · **Branch:** `feat/CAN-26-bilingual-metadata-lineage` · **Sprint:** 2 · **Owner:** Yassir

---

## 1. Executive Summary

`TASKS.md` gives CAN-26 one line: "Bilingual French/English metadata mapping and data lineage tracking." This task delivers both halves for the five query tools of the FastMCP server, without changing the Citation Envelope that PR #8 defined.

- **Bilingual.** A caller can ask for `lang="fr"`. The payload then carries a `display` block with the title in the requested language. When the publisher has no French title, the English title comes back with `fallback: true` and a note. Nothing is ever translated.
- **Lineage.** Every sliced payload carries a `lineage` block: the upstream request, when it was fetched, the release it came from, and each step applied before the model saw the figure.

The two are separate from `citation` on purpose. The envelope says *which* official figure an answer rests on; lineage says *how it got here*.

---

## 2. Deliverables

| Path | Purpose |
|---|---|
| `packages/candata-mcp/src/candata_mcp/bilingual.py` | `parse_language`, `localize_title`, `LocalizedTitle` |
| `packages/candata-mcp/src/candata_mcp/lineage.py` | `SourceCall`, `LineageRecord`, `build_lineage`, `statcan_call`, `valet_call` |
| `packages/candata-mcp/src/candata_mcp/engine.py` | `slice_statcan` / `slice_valet` take `lang` and `source_call`; `clamp_payload` records truncation in the lineage |
| `packages/candata-mcp/src/candata_mcp/server.py` | `lang` on the five query tools; lineage on `execute_sql_analytics` |
| `tests/test_bilingual.py`, `tests/test_lineage.py`, `tests/conftest.py` | New unit tests and shared fixtures |
| `tests/test_server.py` | Server-level tests for `lang`, `source_call` and the analytics lineage |

---

## 3. Bilingual mapping

### 3.1 Where French comes from

| Source | French title | How |
|---|---|---|
| Statistics Canada | Always | `cubeTitleFr` from `getCubeMetadata` (live-verified in the CAN-16 audit, row W-7, added by PR #28) |
| Bank of Canada | Only where sourced | The `FRENCH_TITLES` table in `boc_valet.py`; today only `V39079`. Valet has no `?lang=fr` (audit V-3) |

### 3.2 Behaviour

| Request | Result |
|---|---|
| `lang` omitted or `en` | English title, `fallback: false` |
| `lang="fr"`, French published | French title, `fallback: false` |
| `lang="fr"`, French missing or blank | English title, `language: "en"`, `requested: "fr"`, `fallback: true`, plus a `note` |
| Anything else (`de`, `french`) | `{"error": "Unsupported language ..."}` before any upstream call |

`parse_language` accepts case and region variants (`FR`, `fr-CA`, `fr_CA`). The existing `title: {en, fr}` field is unchanged, so field-by-field comparison with the CAN-14 benchmark still works.

### 3.3 Why a fallback flag and not a translation

AGENTS.md section 6 and the audit (E3) say never invent a Tier 2 value. A machine-translated French title would look official and could not be verified. Returning the English title with an explicit flag keeps the answer honest and lets the caller decide.

### 3.4 Limits

- Only `V39079` has a sourced French title. Adding the CPI measures needs the Bank's own French labels; they are not guessed here. Tracked with the Valet fixes in BEN-45.
- The title is the **cube** title for StatCan, as in the envelope and the CAN-14 ground truth. The series title (`SeriesTitleEn/Fr`, for example "Toronto, Ontario; ...; Two bedroom units") is available from `get_series_info` but is not part of the envelope, so it is not in `display`.

---

## 4. Data lineage

### 4.1 The block

```json
"lineage": {
  "publisher": "Statistics Canada",
  "source_call": {
    "endpoint": "https://www150.statcan.gc.ca/t1/wds/rest/getDataFromVectorsAndLatestNPeriods",
    "request": {"vectorId": 3823103, "latestN": 12}
  },
  "fetched_at": "2026-10-22T19:23:31+00:00",
  "upstream_release": "2025-12-17T08:30",
  "title_source": "getCubeMetadata productId 34100133",
  "steps": [
    "fetched 12 observations via getDataFromVectorsAndLatestNPeriods",
    "sliced in DuckDB: earliest to latest, newest first, limit 12; 12 rows matched, 12 returned"
  ]
}
```

| Field | Meaning | When it is `null` |
|---|---|---|
| `source_call` | Endpoint and the parameters the server actually sent | The caller of the engine did not say what it fetched |
| `fetched_at` | When the connector read the data | Never, for the query tools |
| `upstream_release` | The release timestamp already used in `citation.enrichment` (WDS `releaseTime`) | Valet, which publishes none (audit section 3.5) |
| `title_source` | Where the titles came from (`getCubeMetadata`) | Valet |
| `steps` | Fetch, slice, and truncation, in order | Never |

Valet payloads add the step `release timestamp: not published by Valet`, so the missing release date reads as a fact about the source, not a gap in the code.

### 4.2 Rules

- Nothing is guessed. `source_call` is built by the server from what it called (normalised IDs, the real `recent` / `start_date` / `end_date`), never reconstructed afterwards.
- `upstream_release` reuses the envelope's value, so the two can never disagree.
- Truncation is recorded: when `clamp_payload` drops rows to fit the 3 072-byte budget it adds `truncated: rows dropped from the end ...` to `steps` before it measures, so the note itself is inside the budget.
- `execute_sql_analytics` gets a lineage too, because derived numbers are the ones a reader cannot re-check by eye: its steps are the fetch and `computed in DuckDB with the read-only SQL shown`.

### 4.3 Payload budget cost

Measured live on 2026-10-22 (compact JSON, the form `clamp_payload` measures):

| Tool | Before | After | Lineage + `display` |
|---|---|---|---|
| `query_statcan_vector` (`v3823103`, 12 rows) | 2 305 B | 3 002 B | 697 B |
| `query_valet_policy_rate` (10 rows) | 1 174 B | 1 761 B | 587 B |
| `query_valet_cpi` (`trim`, 12 rows) | 1 088 B | 1 641 B | 553 B |

A 12-row StatCan payload now sits 70 bytes under the budget. Longer titles will push it over, and the clamp then drops data rows, not lineage. That is the intended trade-off (the lineage is what makes the figure checkable), but if it bites, the cheapest saving is dropping `display` when the title is unchanged.

**Existing behaviour, not changed here.** The MCP text a client receives is indented, so it is about 650 bytes larger than the compact size the 3 072-byte budget is measured against (for example 3 652 B on the wire for 3 002 B compact). The budget is therefore not a wire limit.

---

## 5. Verification

- `uv run ruff check .`, `uv run ruff format --check .`, `uv run pyright` and `uv run pytest` pass (135 passed, 2 deselected).
- Live check against the real APIs on 2026-10-22: the three payloads above, with `lang="fr"`:
  - `query_statcan_vector` returned the French cube title, `fallback: false`.
  - `query_valet_policy_rate` returned "Taux cible du financement à un jour".
  - `query_valet_cpi` (`trim`) returned the English title with `fallback: true` and the note.

## 6. Traps

- **A mocked result without `fetched_at` breaks the engine.** The engine reads `result.fetched_at` for the lineage. Test doubles built with `MagicMock(spec=...)` must set it; the existing fixtures now do.
- **`fetched_at` inherits audit finding V-F8.** When Valet's `Date` header is missing the connector silently falls back to the local clock, so lineage cannot yet say which one it is. Fixing it is part of BEN-45.
- **`lang` is not a translation switch.** Statuses, units and dimension member names are not localised; only titles are.
- **BEN-45 touches the same file.** The Valet fixes (V-F1, V-F4, V-F7, V-F8) edit `boc_valet.py`. This task does not, apart from reading `FRENCH_TITLES` and `VALET_BASE_URL`.
