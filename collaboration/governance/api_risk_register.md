# API Risk Register: Canadian Public Endpoints

Owner: Yassir (CAN-16). Audit evidence: [`docs/CAN_16_API_SECURITY_AND_PROVENANCE_AUDIT.md`](../../docs/CAN_16_API_SECURITY_AND_PROVENANCE_AUDIT.md). Last reviewed 2026-10-20.

**Scale:** Likelihood and Impact are L / M / H. **Status:** Open, Mitigated, Accepted. "Audit ref" points to the finding ID in the audit doc.

| ID | Source | Risk | L | I | Mitigation | Owner | Linked task | Status | Audit ref |
|---|---|---|---|---|---|---|---|---|---|
| R-01 | Valet | No published rate limit; terms forbid circumventing limits or overburdening the site. Retries ignore `Retry-After` and there is no concurrency cap. | M | M | Honor `Retry-After` if it appears; add a shared limiter and a short response cache (Valet marks responses fresh for 30 s). | Benjamin (CAN-13 server) / Yassir | CAN-13 | Open | V-F1, V-F2 |
| R-02 | Valet | Series name check uses `re.match` with `$`, so `"V39079\n"` passes. Harmless today (encoded as `%0A`, Valet answers 404). | L | L | Switch to `re.fullmatch`; add a test. | Yassir | CAN-12 follow-up | Open | V-F4 |
| R-03 | Valet | No revision timestamp. A revised value cannot be detected by comparing dates. | M | H | Keep `release_or_revision_date = None`; rely on `fetched_at` plus Citation Verifier re-fetch. | Samir | CAN-24 | Mitigated (by design) | section 3.5 |
| R-04 | Valet | `fetched_at` silently falls back to the local clock when the server `Date` header is missing, so the two sources look identical. | L | M | Record the source of `fetched_at` (server vs local) or fail loudly. | Yassir | CAN-12 follow-up | Open | V-F8 |
| R-05 | Valet | Attribution required by the terms is only partly carried (`publisher` is set, `terms.url` is dropped, derived figures are not marked as modified). | M | M | Carry `terms.url`; mark computed values as derived in the Data Analyst output. | Yassir / Benjamin | CAN-12 follow-up, CAN-23 | Open | V-F7 |
| R-06 | Valet | Unbounded history when no `recent` or dates are passed. | L | L | Default to `recent`; cap rows in the MCP tool layer. | Benjamin | CAN-13 | Open | V-F3 |
| R-07 | WDS | Published limits 25 req/s per IP, 50 req/s server-wide; exceeding them risks blocking. | M | H | Shared rate limiter well under 25 req/s; 1800 s HTTP cache. | Benjamin | CAN-11 | Open (requirement) | WDS-R1, WDS-R3 |
| R-08 | WDS | Tables are locked 00:00-08:30 ET and answer HTTP 409; a naive client reports failure or stale data. | M | M | Retry 409 with backoff and report it distinctly; avoid scheduled pulls in that window. | Benjamin | CAN-11 | Open (requirement) | WDS-R2 |
| R-09 | WDS | HTTP 200 can carry `FAILED` in the body (for example vector ID with a `v` prefix, error code 3). A client that checks only the HTTP code treats failure as success. | M | H | Check body `status` on every response; strip the `v` prefix before calling. | Benjamin | CAN-11 | Open (requirement) | section 4.2 |
| R-10 | WDS | `refPer` and `refPerRaw` differ for annual series (`2024-01-01` vs `2024-10-01`); picking the wrong one corrupts `reference_period`, a Tier 1 field. | M | H | Use `refPer`; derive the envelope period from the series frequency; test against the benchmark (`v3823103` expects `2025`). | Benjamin | CAN-11, CAN-14 | Open (requirement) | W-F1 |
| R-11 | WDS | `releaseTime` has no time zone (08:30 ET, DST applied). Comparing it to UTC `fetched_at` misorders events. | M | M | Store as ET with an explicit zone, or convert once at the boundary. | Benjamin | CAN-11 | Open (requirement) | W-F3 |
| R-12 | WDS | Large payloads (`getCodeSets` is about 315 KB; `getAllCubesList` is larger) on a hot path. | L | M | Cache and load lazily; never call per request. | Benjamin | CAN-11, CAN-13 | Open (requirement) | section 4.2 |
| R-13 | WDS | POST-only fields (`coordinate` metadata, French titles, `corrections`, `issueDate`) were not live-verified. | M | M | Verify against the merged CAN-11 client or approved lookups. | Yassir | CAN-16 | Open (question to Ben) | section 6 |
| R-14 | Both | Field naming drift: docs say `deep_link` / `canonical_link`, code says `canonical_url`. | L | L | Keep `canonical_url`; record the alias (done in the audit doc). | Yassir | CAN-16 | Mitigated | section 5 |
| R-15 | Both | Public mirror: `publish-mcp-server.yml` publishes this package under the commit author's name. | L | H | Public-API data only in fixtures; no secrets (checked for Valet fixtures). | All | CAN-08 | Mitigated | section 3.3 |
| R-16 | Both | The shared `CitationEnvelope` model has no agreed home (Samir proposes Pydantic v2 in `packages/candata-mcp`). Two copies could diverge. | M | M | Decide in CAN-21; benchmark and connector import one model. | Benjamin / Samir | CAN-21, CAN-43 | Open | section 6 |
