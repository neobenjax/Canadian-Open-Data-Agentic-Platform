# Security Checklist: Public API Connectors

Use for any PR that adds or changes a connector in `packages/candata-mcp`. The first four items match the **Security & Risk Review (GRC Checklist)** in `.github/PULL_REQUEST_TEMPLATE.md`; items 5-14 are the checks from [CAN-16](../../docs/CAN_16_API_SECURITY_AND_PROVENANCE_AUDIT.md). Status column shows where Valet (CAN-12) stands today; WDS (CAN-11) is unmerged and marked "to check".

## A. PR template items

| # | Check | Valet today |
|---|---|---|
| 1 | No hardcoded secrets, private tokens or unmasked credentials | Pass (no credentials; fixtures are public responses) |
| 2 | Public API rate limiting and backoff handled cleanly | **Partial** (backoff yes; `Retry-After`, concurrency cap, cache no; R-01) |
| 3 | Data provenance and table citation fields verified (`table_id`, `reference_period`) | Pass (tested) |
| 4 | Docker / dependency vulnerability scan clean | Not run in CAN-16 (no CI scan exists yet; CAN-42) |

## B. Transport and requests

| # | Check | Valet today |
|---|---|---|
| 5 | HTTPS-only base URL; `http://` fails closed, never follows a downgrade | Pass (V-F5) |
| 6 | Explicit timeout on every request | Pass (30 s) |
| 7 | Descriptive `User-Agent` with a contact | **Gap** (`candata-mcp` only; V-F6) |
| 8 | Path segments validated with `re.fullmatch`, then URL-quoted; query values passed as params, never concatenated | **Partial** (uses `re.match`; R-02) |
| 9 | Request volume bounded (limiter, cache, or row cap) | **Gap** (R-01, R-06) |

## C. Responses and errors

| # | Check | Valet today |
|---|---|---|
| 10 | Body-level failure checked, not just the HTTP code (WDS returns 200 with `FAILED`) | n/a for Valet; **required for WDS** (R-09) |
| 11 | Distinct handling for 404 (not found), 409 (WDS table locked), 429 and 5xx (retry) | Valet pass; WDS 409 required (R-08) |
| 12 | Blank or non-numeric values never become `0` | Pass (blank is `None`; non-numeric raises) |

## D. Provenance and terms

| # | Check | Valet today |
|---|---|---|
| 13 | Citation Envelope rules E1-E8 in the audit doc (section 5) met | E1-E6 pass; **E7, E8 open** (R-04, R-05) |
| 14 | Source attribution and terms-of-use link carried with the figure; derived values marked as modified | **Gap** (R-05) |

## How to use
Copy this table into the PR description, tick each row, and link any row marked Gap or Partial to a register entry in [`api_risk_register.md`](api_risk_register.md).
