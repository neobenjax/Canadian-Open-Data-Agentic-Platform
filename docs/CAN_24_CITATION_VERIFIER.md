# CAN-24: Citation Verifier

**Owner:** Samir · **Milestone:** 2 (Sprint 2) · **Linear:** BEN-19 · **Code:** `packages/agent-orchestrator/src/candata_agent/verifier.py`

The Citation Verifier is the last node before an answer leaves the graph. Every figure the agent wants to state comes in as a **claim**: a value plus its two-tier Citation Envelope. The verifier checks each claim against Statistics Canada WDS or Bank of Canada Valet, and only an all-verified report may go to the user.

## What it checks

For each claim, in order. The first failure decides the verdict.

| Step | Check | Verdict on failure |
| :-- | :-- | :-- |
| 1 | Tier 1 is well formed: `NN-NN-NNNN-NN` table, `vNNN` vector (or a Valet series name), period `YYYY`, `YYYY-MM`, `YYYY-MM-DD` or `start/end`. StatCan citations must carry `release_or_revision_date`. | `malformed_citation` (the source is never called) |
| 2 | The vector exists. | `not_found` |
| 3 | The vector belongs to the cited table, and to the cited coordinate when one is given. `125.3.3` equals `125.3.3.0.0.0.0.0.0.0`. | `table_mismatch` |
| 4 | Every cited period has an observation with a published value. | `period_not_found`, `suppressed` |
| 5 | The stated value matches the official value to its published precision (±half the last published decimal). | `value_mismatch` |
| 6 | The cited release date is the official one. Older means the series was revised or re-released since. | `stale_release`, `release_mismatch` |
| — | The source can't be reached (network error, WDS outage page). | `source_unavailable`, which never passes |

- **Citation-only claims:** a claim with `value=None` checks the citation only. Use it for range citations (for example `2024-01/2025-12` behind a computed annual total) and for the inputs of computed figures. A value claim must cite a single period.
- **Quality flags:** StatCan `statusCode` and `symbolCode` are passed through on every verdict, so the answer can carry "use with caution" without failing.
- **Valet:** publishes no release dates, so step 6 doesn't apply to Bank of Canada claims.

## Using it

```python
from candata_agent.verifier import CitationVerifier, Claim, make_citation_verifier_node
from candata_mcp.connectors.boc_valet import ValetClient
from candata_mcp.connectors.statcan_wds import StatCanClient

async with StatCanClient() as statcan, ValetClient() as valet:
    verifier = CitationVerifier(statcan, valet)
    report = await verifier.verify([Claim(citation, 2045.0, "Toronto 2BR rent, 2025")])
    report.passed  # False if any claim failed
    report.failures  # the failing ClaimVerdicts, each with code + message
    report.to_dict()  # JSON-safe, for traces and audit logs

node = make_citation_verifier_node(
    verifier
)  # LangGraph node: reads `claims`, writes `verification`
```

The node accepts a dict state or an attribute-style state. That lets it be wired before the CAN-21 `AgentState` (#34) settles. Once it does, add a `claims` channel and a `verification` field, and route a failed report back to the Data Analyst (CAN-23) or to a HITL interrupt, never to the final answer.

**For CAN-25 tracing:**
- The node is a single async function, `citation_verifier`.
- `report.to_dict()` gives per-claim codes, which can go on the span as attributes.
- The verifier makes no LLM calls, so it uses no tokens. Its latency is the WDS and Valet round trips, one per claim.

## Connector change

`StatCanClient.get_data_by_reference_period(vector_id, start, end=None)` wraps WDS `getDataFromVectorByReferencePeriodRange` (GET). The other WDS calls are POSTs, so `_post_json` now delegates to a shared `_request_json(method, …)`. Retries, the 409 maintenance-window handling and JSON validation are unchanged.

## Verification

- 22 offline tests in `tests/test_citation_verifier.py`, built from real figures:
  - GT-01 rent, $2,045 and $1,972
  - the $2,632 listing-site trap
  - the v729961 July 2025 gap (statusCode 1)
  - the GT-13 policy rate
  - malformed IDs, stale and non-existent release dates, an unknown vector against an outage
  - the node with both state styles
  - the new client call
- **Live:** `uv run pytest -m live tests/test_citation_verifier.py` verifies all 37 citations in `gta_ground_truth_v1.json` against WDS and Valet, plus the GT-01 values. It passed on Oct 28, 2026, with no stale release dates.

## Not in scope

- Extracting claims from model text. The Data Analyst or Supervisor hands over structured claims.
- Checking computed figures (growth rates, shares). Verify their inputs here; the arithmetic is the Data Analyst's exact SQL (CAN-23).
- Concurrency. Claims are checked one at a time, which keeps WDS usage polite. Batch per vector if latency matters once traced.
