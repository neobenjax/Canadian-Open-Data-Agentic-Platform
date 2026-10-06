# Universal AI Agent Guardrails & Guidelines (2026 Edition)

This file defines the mandatory operating rules, developer guardrails, and persona guidelines for all AI coding assistants (**Claude Code, Cursor, Antigravity, Codex, Copilot**) working in this repository.

---

## 🛡️ Non-Negotiable Agent Guardrails

### 1. The Branch Protection Guardrail (NEVER Direct Commit to `main`)
- Direct pushes to `main` are **strictly blocked by GitHub branch protection**.
- You MUST ALWAYS check out a feature branch before making changes:
  ```bash
  git checkout main
  git pull origin main
  git checkout -b feat/<issue-id>-<short-description>
  ```
  *(Example: `feat/CAN-01-update-team-profile` — note that `CAN-01` refers to the Linear issue key).*

### 2. The Linear Issue Linking Guardrail
- Every feature or bug fix corresponds to a Linear task from workspace:  
  `https://linear.app/canopendataagenticplatform/team/CAN/active`.
- Always format commit messages with the Linear issue key:
  ```bash
  git commit -m "[CAN-XXX] feat: description of change"
  ```
- Always include `Closes CAN-XXX` in Pull Request descriptions so Linear automatically marks the card as Done upon merge.

### 3. The 2026 Modern Engineering Standards
- **Python:** Use `uv` package manager, Python 3.12+, strict type hints (`pyright`), Ruff formatting. Follow [python-best-practices](https://github.com/ludo-technologies/python-best-practices).
- **Web & Frontend:** Follow Google Chrome's [modern-web-guidance](https://github.com/googlechrome/modern-web-guidance). Clean, accessible, responsive design adhering to modern web performance and design tokens.
- **Demos & Presentations:** Use [frontend-slides](https://github.com/zarazhangrui/frontend-slides) to create zero-dependency fixed 16:9 interactive slides for weekly demos.

### 4. Mandatory Pre-Flight Verification
Before suggesting to push or open a PR, verify:
```bash
uv run ruff check .
uv run pytest
```

---

## 🎭 Role-Aware Assistant Initialization

On the very first prompt in a session, ask your human developer:
> *"Welcome to the CanData team workspace! Which team member are you today?*  
> *1: Benjamin (Solutions Architect & Lead)*  
> *2: Samir (Data Visualization & Agent Evals Lead)*  
> *3: Yassir (Technology Delivery & Transformation Lead)*  
> *4: Martin (AI Security & Risk Governance Lead)"*

### Role-Specific Guidelines:
- **Role 1 (Benjamin Sanchez Zebadua — Solutions Architect):** Focus on monorepo structure, FastMCP 2.0 core, DuckDB 1.2+ Arrow streaming engine, Next.js architecture, and CI/CD pipelines.
- **Role 2 (Samir Ibrahim — Data Viz & Evals):** Focus on GTA Housing ground-truth benchmarks, LangGraph agent reasoning nodes, DeepEval CI suites, and dynamic Plotly economic trend charts.
- **Role 3 (Yassir Tagelsir Khougali — Tech Delivery & HITL):** Focus on LangGraph Human-in-the-Loop (`interrupt()`) workflows, OpenTelemetry token telemetry, user testing scripts, and Linear agile sprint tracking.
- **Role 4 (Martin Torres — AI Security & GRC):** Focus on AI guardrails, Pydantic v2 schema constraints, API security, Canadian data lineage, prompt injection defense, and Docker hardening.
