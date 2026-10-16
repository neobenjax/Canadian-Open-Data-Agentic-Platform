# Implementation Task Tracker: Core Citation & Release Standards

This task document tracks the activities required to codify official citation metadata standards (table ID, vector ID, coordinate, reference period, release/revision timestamp) across `TASKS.md`, `CANADIAN_AGENTIC_DATA_PLATFORM_PLAN.md`, and presentation slides.

---

## Activities Checklist

### Phase 1: Planning & Setup
- [x] Create Implementation Plan artifact.
- [x] Create this Task Tracker document (`docs/CORE_DOCS_CITATION_STANDARDS_ACTIVITIES.md`).
- [x] Incorporate required fields:
  - Vector Coordinate paths (e.g., `1.1.2.0.0.0.0.0.0.0`)
  - Bilingual En/Fr metadata (`cubeTitleEn`, `cubeTitleFr`)
  - Canonical official deep-link URLs to StatCan / BoC web portals
  - Presentation highlight in `presentation/index.html` with CanData-MCP tone
- [x] Checkout general documentation branch `docs/core-citation-and-release-standards`.

### Phase 2: Task Specifications & Architecture Updates
- [x] Update `TASKS.md` under Milestone 1 (`CAN-11`, `CAN-12`, `CAN-16`):
  - Add explicit acceptance criteria for `table_id`, `vector_id`, `coordinate`, `reference_period`, `release_time` / `revision_timestamp`, bilingual En/Fr titles, and canonical portal deep-links.
- [x] Update `TASKS.md` under Milestone 2 (`CAN-24`):
  - Require Citation Verifier sub-agent to validate the complete Citation Tuple against in-memory DuckDB Arrow slices.
- [x] Update `TASKS.md` under Milestone 4 (`CAN-41`, `CAN-42`):
  - Include automated DeepEval citation accuracy, groundedness, and revision freshness metrics.
- [x] Update `CANADIAN_AGENTIC_DATA_PLATFORM_PLAN.md` Section 1.1 to document release tracking and citation standards.
- [x] Update `presentation/index.html` Slide 2 and Slide 5 to highlight "Nobody Trusts AI Without Receipts & Timestamps" in CanData tone.
- [x] Update `collaboration/benchmarks/benchmark_questions_draft.md` Question Format table to include Reference Period, Revision Timestamp, Coordinate, and Canonical URL.

### Phase 3: Verification & Walkthrough
- [x] Validate `python scripts/sync_tasks.py --status` parses all tasks cleanly without formatting regression.
- [x] Verify no syntax/parser regressions across modified markdown and presentation files.
- [x] Write detailed Walkthrough Guide explaining the changes and how to manually verify them.
- [ ] Present changes to the user for review and approval.

### Phase 4: Gitflow & GitHub Sync (Only after User Approval)
- [ ] Commit changes formatted as core documentation: `docs: codify official citation metadata and release tracking standards across roadmap`.
- [ ] Push branch `docs/core-citation-and-release-standards`.
- [ ] Ask user for approval to merge into `main`, update versions, and publish to GitHub.
- [ ] Purge merged feature branch.
