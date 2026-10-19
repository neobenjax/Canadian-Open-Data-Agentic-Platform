# Architectural Decision & Review Resolution Record: Official Citation & Release Standards

This document tracks the rationale, technical specification, and peer-review resolution for codifying the **Citation Envelope** and release tracking standards across the Canadian Open Data Agentic Platform.

---

## 1. Specification Overview

### Two-Tier Citation Envelope
To balance strict hallucination prevention with realistic LLM evaluation (preventing missing optional metadata like French translations from failing an answer just as severely as wrong numerical data), the citation schema is split into:

1. **Tier 1 — Core Verification Tuple (Strict Pass/Fail):**
   - `table_id` (e.g. `34-10-0133-01`)
   - `vector_id` (e.g. `v3823103`)
   - `reference_period` (e.g. `2025` for annual series, or `2025-10` for monthly)
2. **Tier 2 — Metadata Enrichment (Weighted Scoring):**
   - `coordinate` (e.g. `125.3.3.0.0.0.0.0.0.0` for `v3823103`)
   - `release_or_revision_date` (official release timestamp from WDS / Valet API)
   - `bilingual_title` (`cubeTitleEn`, `cubeTitleFr`)
   - `canonical_url` (direct official portal deep-link)

---

## 2. Review Feedback & Resolution Log (PR #8)

| Item | Reviewer Feedback (Samir) | Status | Resolution Detail |
| :--- | :--- | :---: | :--- |
| **Fix 1: Benchmark Coordinate & Period** | Coordinate for `v3823103` is `125.3.3.0.0.0.0.0.0.0`, and table `34-10-0133-01` is annual (`2025`). | ✅ Resolved | Updated `collaboration/benchmarks/benchmark_questions_draft.md` with live API verified coordinate and annual period. |
| **Fix 2: Broken Local Link** | Walkthrough contained a hardcoded local `file:///` path to the tracker. | ✅ Resolved | Converted to relative markdown link in `docs/CORE_DOCS_CITATION_STANDARDS_WALKTHROUGH.md`. |
| **Suggestion 3: Single Tuple Definition** | Reconcile varying tuple lengths (4-part vs 7-field). | ✅ Resolved | Unified across `CANADIAN_AGENTIC_DATA_PLATFORM_PLAN.md` and `TASKS.md` around the 2-tier Citation Envelope. |
| **Suggestion 4: Eval Scoring Strictness** | Split required vs scored fields for `CAN-41`. | ✅ Resolved | Codified 2-tier evaluation in `CAN-41` and `CAN-16` (strict on Core Tuple, scored on Enrichment). |
| **Suggestion 5: Activity Checklist Scaffolding** | Checklist contained transient agent steps. | ✅ Resolved | Refactored into this permanent Architectural Decision & Resolution Record. |
| **Suggestion 6: Nuance & Tone** | Note that many (not all) series are revised, and soften Slide 2 copy. | ✅ Resolved | Updated Slide 2 copy in `presentation/index.html` to *"Many official series are revised"* and *"sets off inaccurate policy or investment conclusions"*. |
