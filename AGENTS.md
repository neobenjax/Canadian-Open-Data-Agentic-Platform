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

## 🚀 Automated Feature Execution Protocol (from CONTRIBUTING.md)

Whenever a developer says *"Work on [CAN-XXX]"*, *"I am starting task [CAN-XXX]"*, or asks you to implement a feature:
You MUST execute the exact workflow defined in [`CONTRIBUTING.md`](CONTRIBUTING.md) autonomously:

1. **Check & Create Feature Branch:**
   Check current branch. If on `main`, pull latest `origin/main` and branch:
   ```bash
   git checkout main && git pull origin main
   git checkout -b feat/<issue-id>-<short-description>
   ```
   **NEVER write code directly on `main`.**

2. **Mark In-Progress:**
   Transition the task on Linear or execute:
   ```bash
   python scripts/sync_tasks.py --mark-in-progress CAN-XXX
   ```

3. **Execute Implementation:**
   Implement requested changes cleanly following modern 2026 standards.

4. **Run Pre-Flight Verification:**
   ```bash
   uv run ruff check .
   uv run pytest
   ```

5. **Linear Conventional Commit:**
   Stage files and commit formatted with the Linear key:
   ```bash
   git add .
   git commit -m "[CAN-XXX] feat: description of change"
   ```

6. **Push Feature Branch:**
   ```bash
   git push -u origin feat/<issue-id>-<short-description>
   ```

7. **Prepare PR with Triangular Review Assignment:**
   Provide the developer with:
   - PR Title: `[CAN-XXX] feat: description of change`
   - PR Body containing `Closes CAN-XXX`
   - Designated Reviewer Assignment:
     - **Benjamin's PRs** $\rightarrow$ Request review from **Samir** (`@samiroibrahim`)
     - **Samir's PRs** $\rightarrow$ Request review from **Yassir** (`@yassir-tagelsir-khougali`)
     - **Yassir's PRs** $\rightarrow$ Request review from **Benjamin** (`@neobenjax`)
   - Remind the developer that GitHub requires 1 approved review before merging into `main`.

8. **Task Completion & Post-Merge Cleanup:**
   After the PR is merged on GitHub:
   - Update `TASKS.md` checkbox and Linear status: `python scripts/sync_tasks.py --mark-done CAN-XXX`
   - Purge the feature branch:
     ```bash
     git checkout main && git pull origin main
     git branch -d feat/<issue-id>-<short-description>
     git push origin --delete feat/<issue-id>-<short-description>
     ```

---

## 🔧 Account Setup & Commit Signing Automation

When a developer asks for help setting up accounts or signing commits:
- Refer to [`docs/DEVELOPER_SETUP_AND_AUTOMATION_GUIDE.md`](docs/DEVELOPER_SETUP_AND_AUTOMATION_GUIDE.md).
- **SSH Commit Signing:**
  ```bash
  git config --global gpg.format ssh
  git config --global user.signingkey "$HOME/.ssh/id_ed25519.pub"
  git config --global commit.gpgsign true
  ```
- **Linear CLI / Mirror Checks:**
  - View overall progress: `python scripts/sync_tasks.py --status`
  - View member tasks: `python scripts/sync_tasks.py --owner <Name>`
  - Sync with Linear cloud: `python scripts/sync_tasks.py --status --sync-linear`

---

## 🎭 Role-Aware Assistant Initialization (3-Person Core Team)

On the very first prompt in a session, ask your human developer:
> *"Welcome to the CanData team workspace! Which team member are you today?*  
> *1: Benjamin (Solutions Architect & Lead)*  
> *2: Samir (Data Visualization & Agent Evals Lead)*  
> *3: Yassir (Technology Delivery & Transformation Lead)"*

### Role-Specific Guidelines:
- **Role 1 (Benjamin Sanchez Zebadua — Solutions Architect & Lead):** Focus on monorepo structure, FastMCP 2.0 core, DuckDB 1.2+ Arrow streaming engine, Next.js architecture, CI/CD pipelines, Docker container hardening, and public API rate-limiting security.
- **Role 2 (Samir Ibrahim — Data Viz & Evals):** Focus on GTA Housing ground-truth benchmarks, LangGraph agent reasoning nodes, DeepEval CI suites, dynamic Plotly economic trend charts, prompt injection defense, and LLM evaluation safety guardrails.
- **Role 3 (Yassir Tagelsir Khougali — Tech Delivery & Transformation):** Focus on LangGraph Human-in-the-Loop (`interrupt()`) workflows, OpenTelemetry token telemetry, user testing scripts, Linear agile sprint tracking, Canadian data lineage tracking, and audit logging governance.

*(Note: Martin Torres' profile is archived in `collaboration/team-archive/martin_torres_profile.md` for subsequent phases).*
