## 🎯 Linear Issue References (Dual-Key Auto-Closing)
<!-- Both keys required for Linear GitHub auto-closing integration. PR Triage action validates this automatically. -->
Closes BEN-<!-- Native Linear issue key, e.g. 45 -->
Closes CAN-<!-- Canonical sprint task key, e.g. 17 -->

---

## 🛠️ Summary of Changes
- **Task Key:** `CAN-`
- **Component Modified:** [ ] `/packages/candata-mcp` | [ ] `/packages/agent-orchestrator` | [ ] `/apps/docs-portal` | [ ] `/scripts` | [ ] `/collaboration`
- **Description:** 

---

## 🧪 Automated CI & Evaluation Checks
<!-- The CI Pipeline (.github/workflows/ci.yml) validates all items below automatically before merge -->
- [ ] Code formatting & linting clean (`uv run ruff check .` & `ruff format --check .`)
- [ ] Strict type checking passes (`uv run pyright`)
- [ ] Unit & integration test suite passes (`uv run pytest -m 'not live'`)
- [ ] Task checkbox verified in `TASKS.md` (`python scripts/verify_pr_ready.py`)

---

## 🛡️ Security & Provenance Checklist
- [ ] No hardcoded API keys, tokens, or unmasked credentials
- [ ] Rate limits, exponential backoff, and maintenance windows handled
- [ ] Two-Tier Citation Envelope maintained (`vector_id`, `reference_period`, `release_time`)

---

## 👥 Triangular Peer Review Assignment
<!-- Assigned automatically by PR Triage Action based on author: -->
<!-- Benjamin -> @samiromer2 | Samir -> @yassirtmk | Yassir -> @neobenjax -->
- **Assigned Reviewer:** @
