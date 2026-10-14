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

### 2. The Linear Issue Linking & Auto-Closing Guardrail (Full-Circle Integration)
- Every feature or bug fix corresponds to a Linear task from workspace:  
  `https://linear.app/canopendataagenticplatform/team/BEN/active`.
- **Commit Formatting:** Always format git commits with the Linear task key:
  ```bash
  git commit -m "[CAN-XXX] feat: description of change"
  ```
- **PR Dual-Key Auto-Closing Rule:** Linear's underlying team key is **`BEN`**. GitHub's native Linear integration **only auto-closes issues when referenced by their native team key** (`BEN-XX`). Therefore, PR descriptions MUST include both keys:
  ```markdown
  Closes BEN-XX
  Closes CAN-XXX
  ```
  *(Example: `CAN-02` corresponds to `BEN-6`, `CAN-08` corresponds to `BEN-42`).*
- **Linked Documentation Deliverable:** Every feature PR should include a linked documentation file in `docs/` or `collaboration/` (e.g. `collaboration/benchmarks/benchmark_questions_draft.md` for CAN-02, `docs/CAN_08_ONBOARDING_AND_ENV_AUTOMATION.md` for CAN-08) documenting deliverables, traps, and verification.

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

7. **Mark In-Review:**
   Transition task state on Linear & TASKS.md:
   ```bash
   python scripts/sync_tasks.py --mark-in-review CAN-XXX
   ```

8. **Proactive Pull Request Offer & HITL Reviewer Validation (CRITICAL FOR ALL AGENTS):**
   Immediately after pushing changes and marking the task in-review, the AGENT MUST proactively ask the human developer:
   > *"I have pushed your changes to `feat/<issue-id>-<short-description>` and marked CAN-XXX in review. Would you like me to automatically create and send the Pull Request for you, or would you prefer to open it manually on GitHub?"*

   - **Path A: Developer chooses Automated PR Creation (Agent / CLI):**
     Before sending the PR or assigning reviewers, the AGENT MUST execute **Human-in-the-Loop (HITL) Reviewer Validation**:
     > *"The default triangular reviewer for your role is **<Assigned Reviewer>** (`@<github-handle>`). Would you like to proceed with this reviewer, or would you like to assign a different reviewer or add more reviewers?"*
     
     **Triangular Reviewer Defaults:**
     - **Benjamin's PRs** $\rightarrow$ Default Reviewer: **Samir Omer** (`@samiromer2`)
     - **Samir's PRs** $\rightarrow$ Default Reviewer: **Yassir Khougali** (`@yassirtmk`)
     - **Yassir's PRs** $\rightarrow$ Default Reviewer: **Benjamin Sanchez** (`@neobenjax`)

     Once confirmed/modified by the developer, the agent can create the PR using GitHub API / GitHub MCP or by running:
     ```bash
     python scripts/sync_tasks.py --create-pr CAN-XXX --reviewer <chosen-handle>
     ```
     The agent then provides the created PR link and reminds the developer that 1 peer approval is required before merge.

   - **Path B: Developer chooses Manual PR Creation:**
     Provide the developer with the pre-formatted PR details so they can copy-paste them to GitHub:
     - PR Title: `[CAN-XXX] feat: description of change`
     - PR Body containing `Closes BEN-XX` and `Closes CAN-XXX` (where `BEN-XX` is the native Linear issue key)
     - Reviewer Assignment: `@samiromer2`, `@yassirtmk`, or `@neobenjax`
     - Compare & Pull Request URL: `https://github.com/neobenjax/Canadian-Open-Data-Agentic-Platform/pull/new/feat/<issue-id>-<short-description>`

9. **Task Completion & Post-Merge Cleanup:**
   After the PR is approved and merged on GitHub:
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
