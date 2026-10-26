# CAN-16: API Security, Rate Limit and Official Data Verification (Provenance) Audit

| | |
|---|---|
| **Task** | CAN-16 / BEN-15, Sprint 1 |
| **Branch** | `feat/CAN-16-api-security-provenance-audit` |
| **Audited** | Bank of Canada Valet API (code and live), Statistics Canada WDS (guide, live GETs and live read-only POST lookups) |
| **Audit date** | 2026-10-20 (probes at 2026-10-21 03:08-03:09 UTC); POST lookups added 2026-10-22 (BEN-44, 18:45-18:47 UTC) |
| **Related** | [CAN-12 Valet client](CAN_12_BOC_VALET_CLIENT.md), [Citation standards](CORE_DOCS_CITATION_STANDARDS_ACTIVITIES.md), [risk register](../collaboration/governance/api_risk_register.md), [security checklist](../collaboration/governance/security_checklist.md) |

---

## 1. Purpose and Scope

`TASKS.md` asks CAN-16 for two things: (a) an API security, rate-limit and official data verification audit of the Canadian public endpoints, and (b) codification of the Citation Envelope so a revised official series cannot drift silently.

The Citation Envelope itself was already defined in PR #8 and is implemented in `packages/candata-mcp/src/candata_mcp/citation.py` and mirrored by `collaboration/benchmarks/build_ground_truth.py` (CAN-14). **This task does not change the schema.** It records the rules each source must meet (section 5) and the evidence behind them.

**In scope:** Valet (code reviewed, live GETs), WDS (user guide, live GETs). **Out of scope:** prompt injection (CAN-43), the Citation Verifier node (CAN-24), bilingual mapping (CAN-26), the CKAN connector (CAN-34).

**WDS caveat.** The WDS client (CAN-11) is not merged. WDS findings are therefore written as **requirements CAN-11 must meet**, and every WDS field is marked *live-verified* or *from the user guide*. The fields that only POST methods return were first marked *guide only*; they were live-verified on 2026-10-22 (BEN-44, Appendix A W-6 to W-8).

---

## 2. Method and Evidence

- Only read-only GET requests, each with a descriptive `User-Agent` (`CanDataMCP-audit/0.1 (CAN-16 read-only audit; ...)`). Appendix A lists every request. The 2026-10-22 follow-up (BEN-44) added three read-only POST lookups (W-6 to W-8); WDS uses POST for these query methods and they change no data.
- Valet code audited at `main` 9f71ed1: `boc_valet.py`, `citation.py`, `tests/connectors/test_boc_valet.py`.
- WDS rules come from the official [WDS user guide](https://www.statcan.gc.ca/en/developers/wds/user-guide) (v1.6) and from live responses.
- Findings are rated **High / Medium / Low / Info**. No High findings were found.

---

## 3. Valet Audit

### 3.1 Rate limits and availability

| Check | Result | Evidence |
|---|---|---|
| Published limit | **None published.** No `Retry-After`, `X-RateLimit-*` or similar header on 200, 400 or 404 responses. | Appendix A, V-1 to V-4 |
| Usage terms | The [Terms of Use](https://www.bankofcanada.ca/terms/) forbid circumventing limits on "the number or frequency of requests" (naming the Valet API) and overburdening the site. No numeric limit is given. | Appendix A, V-6 |
| Caching signal | `Cache-Control: max-age=30` on 200 responses; no `ETag` or `Last-Modified`. | V-1, V-2 |
| Client behaviour | `ValetClient._get_json` retries 429/500/502/503/504 and transport errors, 2 retries, backoff 0.5 s then 1.0 s. Timeout 30 s. Tested in `test_boc_valet.py`. | `boc_valet.py` |

**Findings**
- **V-F1 (Medium): `Retry-After` is ignored.** On a 429 the client waits at most 1.5 s in total before giving up. Valet publishes no `Retry-After` today, so this is latent, but the terms make honoring limits a legal expectation.
- **V-F2 (Low): no client-side concurrency cap or response cache.** A caller (for example the CAN-13 server or the CAN-23 agent) can issue many parallel requests for the same series, although Valet marks responses fresh for 30 s.
- **V-F3 (Low): unbounded history.** `get_observations` with no `recent` or dates returns a series' full history; there is no size cap.

### 3.2 Input validation and request construction

| Check | Result |
|---|---|
| Series and group names | Validated by `_NAME = ^[A-Za-z0-9_\-]+$`, then `urllib.parse.quote`. Tests reject `""`, `V39079/../x`, `V 39079`, `a?b=c`. |
| Query values | Passed through `httpx` `params` (encoded, not concatenated). Dates must be ISO `YYYY-MM-DD`; `recent` must be positive and cannot be combined with dates. |
| Error bodies | Only `message` is read from a JSON error body; otherwise the reason phrase is used. |

**Findings**
- **V-F4 (Low): trailing newline passes the name check.** `re.match` with `$` accepts `"V39079\n"` (verified). `quote()` turns it into `%0A`, so no injection results and Valet would return 404, but `re.fullmatch` is the correct check. Fix is one line; left out of this PR because it changes CAN-12 code (see section 7).
- **V-F5 (Info): `base_url` is not required to be HTTPS.** It is configurable for tests. An `http://` base gets a 301 from Valet (V-5); `httpx` does not follow redirects by default, and an empty 301 body raises `ValetResponseError`, so the client fails closed rather than downgrading.

### 3.3 Transport and secrets

| Check | Result |
|---|---|
| HTTPS | Default base is `https://www.bankofcanada.ca/valet`. `http://` answers `301` (V-5). |
| Credentials | None used or stored. Valet needs no key. |
| Fixtures | `tests/fixtures/valet/*.json` hold public API responses only. Required because `publish-mcp-server.yml` mirrors this package publicly. |
| Identification | `User-Agent: candata-mcp`, with no version or contact. |

**Finding V-F6 (Info):** a descriptive `User-Agent` with a contact URL helps the Bank reach us before blocking us.

### 3.4 Attribution (terms of use)

The terms require attributing the Bank of Canada "in any reasonable manner" and indicating if changes were made, and require "due diligence in ensuring the accuracy" of reproduced content. Every Valet response includes `terms.url`.

- **V-F7 (Medium): attribution is only partly carried.** `CitationEnvelope.publisher` is set to "Bank of Canada" (good), but `terms.url` is discarded and nothing marks derived figures (for example a year-over-year change computed by CAN-23) as modified.

### 3.5 Provenance (envelope fields)

| Field | Published by Valet? | What `citation()` does |
|---|---|---|
| `table_id` | n/a | `"Valet"` |
| `vector_id` | Yes (series name) | series name |
| `reference_period` | Yes (observation `d`, `dateFormat`) | `YYYY-MM-DD`, `YYYY-MM` or `YYYY`, or `start/end` |
| `release_or_revision_date` | **No** | `None` (Ben approved, PR #13) |
| `coordinate` | n/a | `None` |
| `bilingual_title` | EN yes; **FR no** (`?lang=fr` returns 400, V-3) | FR from `FRENCH_TITLES` (V39079 only), else `None` |
| `canonical_url` | Yes | `.../valet/observations/<series>` |

**Finding V-F8 (Medium): silent fallback in `fetched_at`.** `_fetched_at` uses the server `Date` header, but when it is missing or unparseable it silently falls back to the **local clock**. The two sources are indistinguishable downstream, which weakens the one provenance signal Valet gives us.

**Drift risk:** because Valet has no revision date, a revised value cannot be detected by comparing dates. `fetched_at` only proves when a value was read. The mitigation is the Citation Verifier (CAN-24) re-fetching, not anything in the connector.

---

## 4. WDS Audit

Source: WDS user guide v1.6, live GETs (Appendix A, W-1 to W-5) and live read-only POST lookups (W-6 to W-8). `https://www150.statcan.gc.ca/t1/wds/rest/`.

### 4.1 Rate limits and availability

| Check | Result | Basis |
|---|---|---|
| Published limits | **50 requests/s server-wide, 25 requests/s per IP.** | User guide |
| Update window | Data updates every business day at **08:30 ET**. From midnight until 08:30 certain methods return no data and locked tables answer **HTTP 409**. | User guide |
| Caching | `Cache-Control: max-age=1800` on all probed responses. | W-1 to W-3 |
| Transport | HTTPS; `Strict-Transport-Security: max-age=31536000; includeSubDomains`. | W-1 to W-3 |

**Requirements for CAN-11 (WDS-R1 to WDS-R4)**
- **WDS-R1:** stay well under 25 req/s per IP; use a shared limiter, not per-call sleeps.
- **WDS-R2:** treat `409` as retryable-with-backoff, and surface it distinctly from `404`. Avoid scheduled refreshes between 00:00 and 08:30 ET.
- **WDS-R3:** honor the 1800 s cache window (HTTP caching is already in the CAN-11 spec).
- **WDS-R4:** send a descriptive `User-Agent`.

### 4.2 Input and response handling

- **Vector IDs are bare integers.** `vectorIds="v3823103"` fails with `"The vector id [v3823103] is not valid. Error code = 3"` (W-3); `3823103` succeeds (W-4). The portal shows `v`-prefixed IDs, so CAN-11 must strip the prefix, and the envelope's `vector_id` must keep one stable form (the benchmark uses `v3823103`).
- **HTTP 200 can carry a failure.** The failed lookup above returned HTTP 200 with `[{"status":"FAILED", ...}]`. **CAN-11 must check the body `status`, not just the HTTP code.**
- `getCodeSets` is ~315 KB and `getAllCubesList` is larger; neither belongs on a hot path.

### 4.3 Provenance (envelope fields)

| Envelope field | WDS source | Verified |
|---|---|---|
| `table_id` | `productId` (8 digits, for example `34100133` for `34-10-0133-01`). An integer in series responses, a string (`"34100133"`) in `getCubeMetadata` (W-F5). | Live (W-4, W-6, W-7) |
| `vector_id` | `vectorId` | Live (W-4) |
| `reference_period` | `refPer` (normalized) and `refPerRaw` | Live (W-4) |
| `release_or_revision_date` | per-data-point `releaseTime` (`2025-12-17T08:30`); cube-level `releaseTime` (`2025-12-17T08:30`); cube-level `issueDate` (`2018-06-27`); `correctionFootnote` (`[]`) | `releaseTime` live (W-2, W-4, W-8); cube `releaseTime`, `issueDate` and `correctionFootnote` live (W-7). The guide's "corrections" field is named `correctionFootnote` in the response, and `issueDate` is not the latest release (W-F6). |
| `coordinate` | `coordinate` (`125.3.3.0.0.0.0.0.0.0`) | Live (W-6) |
| `bilingual_title` | `cubeTitleEn/Fr` (W-7), `SeriesTitleEn/Fr` (W-6) | Live (W-6, W-7). French text is returned in UTF-8. |
| `canonical_url` | portal deep link built from `productId` | Not verified; pattern to be confirmed |

**Findings**
- **W-F1 (Medium): `refPer` and `refPerRaw` can disagree.** For `v3823103` (annual) the same data point returned `refPer: "2024-01-01"` but `refPerRaw: "2024-10-01"`, and `2025-01-01` vs `2025-10-01`. The guide calls `refPer` the "normalized date". The benchmark expects `2025`. CAN-11 must choose `refPer` deliberately and derive the envelope period from the series frequency (the response carries `frequencyCode: 12`; confirm its meaning in `getCodeSets`), or `reference_period` will drift.
- **W-F2 (Positive): `releaseTime` is per data point.** A revised value gets its own `releaseTime`, so `release_or_revision_date` can be filled from WDS. This is the field that prevents silent temporal drift, and it is the main difference from Valet.
- **W-F3 (Medium): `releaseTime` has no time zone.** `2025-12-17T08:30` is documented as 08:30 ET with DST applied. CAN-11 must store it as a local ET timestamp or convert it explicitly, never compare it to a UTC `fetched_at` as-is.
- **W-F4 (Info): `getChangedCubeList/{date}` lists tables released that day** with their `releaseTime` (W-2). It is the cheapest way for the Citation Verifier to ask "did this table change since I read it?".
- **W-F5 (Low): `productId` has two types.** `getSeriesInfoFromVector` returns it as an integer (`34100133`) and `getCubeMetadata` as a string (`"34100133"`) (W-6, W-7). CAN-11 must normalise to one form before building the envelope `table_id`, and must reject an empty or non-positive value instead of defaulting (AGENTS.md section 6).
- **W-F6 (Medium): cube-level `issueDate` is not a revision date.** For `34100133`, `issueDate` is `2018-06-27` while the cube's `releaseTime` and the latest data point are `2025-12-17T08:30` (W-7, W-8), and `correctionFootnote` is empty. `release_or_revision_date` must come from per-point `releaseTime` (W-F2), never from `issueDate`.
- **W-F7 (Medium): a series can have rows with no value.** `v3823103` returns rows for 1987 to 1991 with `value: null` and `statusCode: 1`, followed by the first real value for 1992 (755.0, `releaseTime` `2001-10-31T08:30`) (W-8). The cube's `cubeStartDate` is `1987-01-01`, so neither it nor the first row is the start of the data. CAN-11 must keep `statusCode` and `symbolCode` (AGENTS.md section 6) and must not treat a row as an observation, or an answer could cite a 1987 Toronto rent that does not exist. The CAN-14 ground truth for GT-15 (earliest period `1992`) is correct.
- **W-F8 (Medium): WDS can answer HTTP 200 with an HTML outage page.** During the BEN-44 retry (around 2026-10-22 03:08 UTC) WDS returned an HTML maintenance page with HTTP 200 instead of JSON; the raw body was not kept. By 18:45 UTC the same endpoints returned `application/json` (W-6 to W-8). CAN-11 must check `Content-Type` and parse failures as an outage, in addition to the body `status` check in section 4.2, and report them as retryable rather than as an empty result.

---

## 5. Citation Envelope Conformance Rules

Codifies PR #8 as testable rules. Both connectors must meet them; the benchmark already does.

| # | Rule | Valet today | WDS (CAN-11 must) |
|---|---|---|---|
| E1 | Tier 1 (`table_id`, `vector_id`, `reference_period`) is strict pass/fail and never empty. | Met | Must handle W-F1 and the body-level `FAILED` status (section 4.2) |
| E2 | Tier 2 fields may be `None`; `None` lowers score but never fails an answer. | Met | n/a |
| E3 | Never invent a Tier 2 value. `None` beats a guess. | Met (PR #13) | Same |
| E4 | `fetched_at` is not a substitute for `release_or_revision_date`. | Met (kept separate) | Same |
| E5 | `reference_period` formats: `YYYY`, `YYYY-MM`, `YYYY-MM-DD`, or `start/end`; granularity follows the series frequency. | Met | Must derive from frequency (W-F1) |
| E6 | `release_or_revision_date` carries an explicit time zone or is documented as ET. | n/a (`None`) | Must (W-F3) |
| E7 | Source attribution travels with the figure. | **Partly (V-F7)** | Open: licence text not yet checked |
| E8 | `fetched_at` source is distinguishable (server `Date` vs local clock). | **Not met (V-F8)** | Must |

**Naming.** The standards docs call the last Tier 2 field `deep_link` / `canonical_link`; code and benchmark use **`canonical_url`**. They are the same field. No rename is proposed, since it would break the CAN-14 field-by-field comparison.

---

## 6. Open Items

1. **WDS POST lookups: done (BEN-44, 2026-10-22).** `coordinate`, `SeriesTitleFr` / `cubeTitleFr`, `issueDate` and `correctionFootnote` are now live-verified (W-6, W-7); findings W-F5 to W-F8 came out of them. Still unverified: a cube with a non-empty `correctionFootnote`, so the correction shape is unknown.
2. **Shared `CitationEnvelope` home.** Samir proposes a Pydantic v2 model in `packages/candata-mcp` (CAN-21, CAN-43). Not decided; not changed here.
3. **Valet fixes (V-F1, V-F4, V-F7, V-F8).** Small changes to CAN-12 code. Proposed as a follow-up, not bundled, so this PR stays documentation-only.
4. **Open Government Licence / WDS terms** not yet reviewed; needed for E7.
5. **Canonical WDS deep-link pattern** to confirm against the portal.

---

## Appendix A: Live Requests

V-1 to W-5 are GET. W-6 to W-8 are POST query methods (JSON body, `Content-Type: application/json`). All are read-only, from one IP, no authentication. Raw logs: `valet_probes.log`, `wds_get_probes.log` (session scratchpad; available on request).

| ID | Time (UTC) | URL | Result |
|---|---|---|---|
| V-1 | 2026-10-21 03:08:26 | `https://www.bankofcanada.ca/valet/series/V39079/json` | 200, `max-age=30`, no limit headers |
| V-2 | 03:08:26 | `.../valet/observations/V39079/json?recent=1` | 200, `max-age=30` |
| V-3 | 03:08:26 | `.../valet/observations/V39079/json?recent=1&lang=fr` | 400 "invalid query parameters: lang" |
| V-4 | 03:08:27 | `.../valet/series/NOT_A_SERIES/json` | 404 JSON `message` |
| V-5 | 03:08:27 | `http://www.bankofcanada.ca/valet/series/V39079/json` | 301 (to HTTPS) |
| V-6 | 03:08:41, 03:08:53 | `https://www.bankofcanada.ca/terms/` | 200, terms text read |
| V-7 | 03:09:05 | `https://www.bankofcanada.ca/valet/docs` | 200 (client-rendered, no usable text) |
| W-1 | 03:08:43 | `https://www150.statcan.gc.ca/t1/wds/rest/getCodeSets` | 200, 315 KB, `max-age=1800` |
| W-2 | 03:08:43 | `.../getChangedCubeList/2026-10-20` | 200, `releaseTime` `2026-10-20T08:30` |
| W-3 | 03:08:43 | `.../getDataFromVectorByReferencePeriodRange?vectorIds="v3823103"...` | 200 with `FAILED`, error code 3 |
| W-4 | 03:08:53 | `.../getDataFromVectorByReferencePeriodRange?vectorIds=3823103&startRefPeriod=2024-01-01&endReferencePeriod=2025-12-31` | 200, 2 points, `releaseTime` per point |
| W-5 | 03:09:04-05 | `https://www.statcan.gc.ca/en/developers/wds/user-guide`, `.../developers/wds` | 200, guide read |
| W-6 | 2026-10-22 18:45:44 | POST `.../getSeriesInfoFromVector` body `[{"vectorId":3823103}]` | 200, `application/json`, `SUCCESS`; `coordinate`, `SeriesTitleEn/Fr`, `productId` (integer) |
| W-7 | 18:45:45 | POST `.../getCubeMetadata` body `[{"productId":34100133}]` | 200, `application/json`, 67 KB, `SUCCESS`; `cubeTitleEn/Fr`, `issueDate`, `releaseTime`, `correctionFootnote: []`, `productId` (string) |
| W-8 | 18:47:26 | POST `.../getDataFromVectorsAndLatestNPeriods` body `[{"vectorId":3823103,"latestN":100}]` | 200, `application/json`, `SUCCESS`; 39 points, 1987 to 2025; 1987 to 1991 `value: null`, `statusCode: 1`; first value 1992 |
