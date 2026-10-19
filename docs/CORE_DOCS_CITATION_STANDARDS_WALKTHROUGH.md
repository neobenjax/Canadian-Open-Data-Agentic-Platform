# Walkthrough Guide: Core Citation & Release Standards

This walkthrough documents the technical and task-level updates made to codify the **Official Citation & Release Tracking Standard** across CanData-MCP core documentation and task specifications.

---

## 🎯 What Was Changed

### 1. `TASKS.md` Task Specification Updates
- **`CAN-11` (Statistics Canada WDS API Client):**
  Added explicit acceptance criteria to parse and return structured metadata:
  `table_id`, `vector_id`, `coordinate`, `reference_period`, `release_time`, bilingual En/Fr titles, and canonical portal deep-link.
- **`CAN-12` (Bank of Canada Valet API Client):**
  Added explicit acceptance criteria for observation dates, series IDs, publication timestamps, and Valet portal deep-links.
- **`CAN-16` (Official Data Verification & Security Audit):**
  Codified the **Citation Envelope**:
  - **Core Verification Tuple (Strict Pass/Fail):** $\langle \text{table\_id}, \, \text{vector\_id}, \, \text{reference\_period} \rangle$
  - **Enrichment Metadata (Scored):** $\langle \text{release\_or\_revision\_date}, \, \text{coordinate}, \, \text{bilingual\_title}, \, \text{canonical\_link} \rangle$
- **`CAN-24` (LangGraph Citation Verifier Node):**
  Updated to validate statistics against Core Verification Tuples and cross-examine release/revision timestamps.
- **`CAN-41` & `CAN-42` (DeepEval CI/CD Pipeline):**
  Added 2-tier evaluation (strict accuracy on core tuple vs partial credit on metadata enrichment) to prevent severe grading penalties for missing optional enrichment.

### 2. `CANADIAN_AGENTIC_DATA_PLATFORM_PLAN.md`
- **Section 1.1:** Updated to *"Zero Hallucination & Release Tracking"*, formally defining the Citation Envelope and 2-tier verification structure.

### 3. `presentation/index.html` (Interactive Slide Deck)
- **Slide 2 ("Nobody Trusts AI Without Receipts & Timestamps"):**
  Updated card badge to `CITATIONS & REVISIONS` with nuanced, professional tone:
  > *"Many official series are revised, and unanchored citations go stale. In central banking and policy, one number quoted without release dates and coordinates sets off inaccurate policy or investment conclusions."*
  > *"🎯 CanData Citation Tuple: Table ID · Vector · Coordinate · Ref Period · Release Timestamp · Bilingual En/Fr Deep-link."*
- **Slide 5 (Architecture / LangGraph item 4):**
  Updated to specify the Citation Verifier sub-agent cross-examining revision dates against official release timestamps.

### 4. `collaboration/benchmarks/benchmark_questions_draft.md`
- Updated the **Question Format & Citation Tuple Standard** table with accurate coordinate (`125.3.3.0.0.0.0.0.0.0` for `v3823103`) and annual reference period (`2025` for Table `34-10-0133-01`) verified against live StatCan WDS API.

### 5. Task Activity Tracker
- Documented all implementation and review resolution phases in [`CORE_DOCS_CITATION_STANDARDS_ACTIVITIES.md`](CORE_DOCS_CITATION_STANDARDS_ACTIVITIES.md).

---

## 🧪 How to Verify Manually

1. **Verify Task Parser Integrity:**
   Run the task parser CLI to confirm all 37 tasks parse with zero errors:
   ```powershell
   python scripts/sync_tasks.py --status
   ```
   *Expected output:* Total Tasks: 37 | Done: 7 | Todo: 30. All milestone headers and task lines parse cleanly.

2. **Verify Git Branch:**
   ```powershell
   git branch --show-current
   ```
   *Expected output:* `docs/core-citation-and-release-standards`

3. **Verify Git Diff:**
   ```powershell
   git diff
   ```
   Confirm all modified lines accurately represent the Citation Tuple and presentation highlights without any task-specific code development.

4. **Verify Presentation Deck Locally:**
   Open `presentation/index.html` in your browser:
   - Navigate to Slide 2: verify the cyan card displays *"Nobody Trusts AI Without Receipts & Timestamps"* and the CanData Citation Tuple.
   - Navigate to Slide 5: verify the LangGraph architecture card lists the citation verifier revision cross-examination.
