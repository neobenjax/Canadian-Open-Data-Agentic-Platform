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
uv run ruff format --check .
uv run pyright
uv run pytest
```

### 5. Monorepo-to-MCP-Distribution Architecture Guardrail
- **The Monorepo is the Single Source of Truth:**
  - This repository (`Canadian-Open-Data-Agentic-Platform`) houses EVERYTHING: core MCP packages (`packages/`), test suites (`tests/`), team web apps (`apps/`), interactive 16:9 slides (`presentation/`), internal sprint meeting notes and GTA benchmarks (`collaboration/`), architecture guides (`docs/`), and task tracking (`TASKS.md`).
  - **NEVER delete these folders from this repository.**
- **The Standalone Distribution Repo:**
  - `https://github.com/neobenjax/Canadian-Open-Data-Agentic-Platform-MCP-Server.git` is an automated, read-only distribution mirror.
  - Issues and PRs are disabled on the distribution repo. All external community PRs must be opened against this monorepo.
- **The `distribution/` Staging Directory:**
  - Files intended for the root of the standalone distribution repo live inside `distribution/` (e.g. `distribution/README.md`, `distribution/CONTRIBUTING.md`).
  - Do NOT create loose prefixed files (like `MCP_README.md`) in the monorepo root.
- **Individual Contributor Attribution on Downstream Releases:**
  - Automated syncs via `.github/workflows/publish-mcp-server.yml` dynamically extract the original commit author (`--author="$AUTHOR_NAME <$AUTHOR_EMAIL>"`).
  - Whichever developer (Benjamin, Samir, or Yassir) authors the feature commit in the monorepo will appear as the **sole author** of that commit in the standalone MCP Server repository history.
- **GitHub PAT Scope Requirement:**
  - Any Personal Access Token used to push workflow files (`.github/workflows/*.yml`) must include both `repo` and `workflow` scopes.

### 6. Official Data Connector & Evaluation Standards (Evals-First Guardrails)
- **Data Quality & Reliability Fidelity:** Never drop official quality, reliability, or confidentiality flags (e.g., StatCan `statusCode`, `symbolCode` like A-F data quality grades, `..` not available). Connectors and observation containers MUST carry them so downstream evaluation agents can distinguish reliable figures from "use with caution" or suppressed estimates.
- **Fail-Loud Ambiguity Resolution:** Never silently select the first match (`.first()`) when resolving hierarchical dimension members (e.g., duplicate geography names across municipalities/CMA boundaries like Smiths Falls, Abbotsford-Mission). Connectors MUST detect ambiguity and raise an informative `AmbiguousMemberError` listing candidate IDs.
- **Strict Identifier Validation (Zero-Tolerance for Bogus Defaults):** Required identifiers (e.g., `vectorId`, `productId`, `series_id`) MUST strictly validate as positive/non-empty values and fail loud on malformed payloads, rather than defaulting to `0` or `""` which generates hallucinated citations (e.g., `v0`).
- **Provenance, Operating Windows & Timezone Awareness:** Official data releases are referenced to specific release schedules. StatCan WDS release times are Eastern Time (`America/Toronto` / ET); connectors must handle daily maintenance windows (HTTP 409 between 00:00-08:30 ET) with clear actionable errors and declare descriptive user agents (`CanDataMCP/...`).

### 7. In-Memory Embedded Engine Sandboxing (Zero-Trust Local Execution)
- Embedded query engines (DuckDB, SQLite, Python REPLs) MUST explicitly disable external filesystem, network, and configuration access via driver-level flags:
  `duckdb.connect(":memory:", config={"enable_external_access": False, "lock_configuration": True})`.
- Keyword regex blocklists (`INSERT`, `DROP`, `DELETE`) are strictly a secondary defense layer; driver-level sandboxing is mandatory to defeat prompt injection and arbitrary file read (AFR) table functions (`read_text`, `read_csv`, `glob`).

### 8. Temporal Boundary Normalization Standard
- Slicing and filtering tools accepting partial ISO dates (`YYYY`, `YYYY-MM`) must normalize bounds (`YYYY` -> `YYYY-01-01` to `< (YYYY+1)-01-01`) before comparison.
- Never perform raw string comparisons on variable-length dates, which silently excludes observations (e.g. `"2025-01-01" <= "2025"` evaluates to False).

### 9. Mandatory PR Author Assignee Rule (Housekeeping)
- Every PR opened or managed by an agent MUST set the PR author as the primary Assignee (`neobenjax` for Benjamin, `samiromer2` for Samir, `yassirtmk` for Yassir). `scripts/sync_tasks.py --create-pr` automatically enforces this.

### 10. Headless Git & Subprocess Execution Guardrail (Windows Non-Interactive)
- In automated agent sessions and script runners, set `GIT_TERMINAL_PROMPT=0` to prevent git subcommands from hanging indefinitely on Windows credential or passphrase prompts.
- When pushing or querying remote repositories in automated subagents, use authenticated URLs via environment tokens (`$env:GITHUB_TOKEN`) or GitHub MCP tools rather than interactive credentials.

### 11. Post-Squash Branch Cleanup Protocol
- GitHub PR squash-merges create a single new consolidated commit hash on `main`. As a result, standard `git branch -d` locally will report that the branch is not fully merged.
- Before deleting, verify that the squash commit is present on `origin/main` (e.g. via `git log origin/main --grep="<PR title or ticket ID>"`).
- Once confirmed, safely force-delete the local feature branch:
  ```bash
  git branch -D feat/<issue-id>-<short-description>
  ```

### 12. Cross-PR Scope Hygiene & Infrastructure Decoupling
- Maintain strict single-concern scope per Pull Request. Feature branches for specific connectors or services (e.g., Bank of Canada, StatCan) must focus exclusively on their domain logic, models, and tests.
- Never bundle cross-cutting infrastructure changes (e.g., monorepo root package management, test runner restructuring, global CI workflow edits) into a feature PR unless explicitly designated by the issue scope. Cross-cutting improvements belong in dedicated, isolated PRs.

### 13. Stacked Feature Branch Rebase Protocol
- When developing a feature branch that branches off an in-flight dependency branch rather than `main`, squash-merging the dependency branch into `main` invalidates the local commit history.
- Never perform a plain `git rebase main` on the downstream branch, as this attempts to replay already-squashed commits and generates severe merge conflicts.
- Always execute an upstream-delimited rebase:
  ```bash
  git rebase --onto origin/main <base-feature-tip-commit> <downstream-feature-branch>
  ```

### 14. Review Approval & Technical Debt Issue Conversion (`[TECH-DEBT]`)
- During peer code review, do not block or delay immediate PR approval for out-of-scope architectural optimizations, prospective enhancements, or adjacent refactoring ideas.
- Approve the PR when core functional and quality requirements are met, and immediately file targeted GitHub Issues for deferred items:
  - Title format: `[TECH-DEBT] <Clear description of debt or optimization>`
  - Label: `tech-debt`
  - Reference the originating PR number and relevant source files for traceability.

### 15. External Feedback Anonymization & Taxonomy Scrubbing (IP Protection)
- When incorporating architectural reviews, evaluation benchmarks, or process feedback from external commenters, partners, or platforms, strictly strip vendor-specific proper nouns, external individual names, and proprietary taxonomy labels.
- Translate all feedback into generalized, domain-agnostic technical terminology before recording in repository documentation, commit histories, or code comments.

### 16. Task-ID Scope Discipline for Non-Implementation Branches
- Feature tickets (`feat/CAN-XXX`) and Linear issue closing keys (`Closes BEN-XX`, `Closes CAN-XXX`) are reserved exclusively for deliverables tracked on the active sprint board.
- Non-implementation activities—such as repository governance, general documentation updates, developer guides, or CI chore—must use semantic prefixes without ticket keys (e.g., `docs/<topic>`, `chore/<topic>`). Never fabricate or attach unrelated ticket IDs to purely operational PRs.

### 17. Outcome-Focused Commit Semantics
- Git commit messages must succinctly describe the resulting technical change or architecture outcome (e.g., `docs: consolidate operational invariants, eval taxonomy, and headless git guardrails`).
- Never use procedural meta-text, reactive phrases, or conversational commentary (e.g., avoid `fix: address review comments`, `updates per review`, `address PR feedback`).

### 18. Two-Tier Citation Envelope Architecture
- All Canadian Open Data agent responses and connector observation outputs must structure citations according to the Two-Tier Citation Envelope standard:
  - **Tier 1 (Core Pass/Fail Citations):** Structural data provenance required for truthfulness verification. Must include `vectorId`, `productId` (StatCan) or `series_id` (Bank of Canada), exact observation coordinate/date, and publishing agency. Absence of Tier 1 metadata constitutes an automatic evaluation hallucination / test failure.
  - **Tier 2 (Enrichment Scored Citations):** Data quality, reliability, and contextual attributes (e.g., StatCan `symbolCode` quality grades A through F, `statusCode` confidentiality flags, BoC observation frequency and description, dimension release dates). Evaluated using a graduated scoring rubric to measure output completeness and trustworthiness.

### 19. Deterministic Evaluation Categorization (`eval_type` Taxonomy)
- Ground-truth evaluation benchmarks (such as GTA housing and macroeconomic suites) must categorize every test prompt under an explicit, deterministic `eval_type`:
  - `numeric`: Exact or tolerance-bounded numerical value checks against official releases.
  - `comparison`: Multi-series trend analysis, relative rankings, or cross-geographical ratio validations.
  - `refusal`: Mandatory refusal / boundary defense verification (e.g., gracefully declining suppressed data, non-existent series, or out-of-scope temporal intervals).
  - `flag`: Data quality and reliability grade checks (e.g., asserting that the agent properly surfaced a 'use with caution' or preliminary data warning).

### 20. Statutory Policy Framework Constants vs. REST Time-Series Handling
- Statutory economic mandates and official policy targets (such as the Bank of Canada's 2% inflation target control range or official CPI basket weights) represent legal/institutional policy frameworks, not dynamic time-series observations.
- Connectors and evaluation harnesses must never attempt to query dynamic time-series endpoints for fixed statutory definitions. Encode policy frameworks as versioned domain constants with authoritative citations; reserve REST API calls strictly for empirical time-series data.

### 21. Direct Peer-to-Peer Review & Interaction Protocol
- All agent interactions in PR reviews, pull request descriptions, and issue discussions must maintain an objective, direct, and constructive peer engineering tone.
- Avoid excessive sycophancy, flattering boilerplate ("outstanding work!", "kudos on the brilliant PR"), or formal corporate hierarchical titles. State architectural feedback, required corrections, and approval rationales with clear, actionable technical facts.

### 22. Post-Integration `/learn` Harvesting Protocol
- Upon completing and merging major milestone PRs or architectural integrations, agents must execute the `/learn` harvesting routine across recent session transcripts.
- Capture newly identified failure modes, reviewer expectations, and operational invariants into `AGENTS.md` and `.cursorrules` to ensure continuous cross-session agent alignment.

### 23. Mandatory GitHub PR Milestone & Label Taxonomy
- Every Pull Request opened in this repository MUST have:
  1. **Primary Assignee:** The PR author (`neobenjax`, `samiromer2`, or `yassirtmk`).
  2. **Designated Triangular Reviewer:** Requested reviewer per the triangular peer review matrix.
  3. **Milestone Attached:** Directly attached to the corresponding sprint milestone (`Milestone 0` through `Milestone 6`).
  4. **Tri-Tier Label Taxonomy:** At least one label from each mandatory category:
     - **Milestone Label:** `milestone:m0` to `milestone:m6`
     - **Semantic Type Label:** `type:feat`, `type:fix`, `type:docs`, `type:chore`, `type:eval`, or `type:security`
     - **Domain Area Label:** `area:connectors`, `area:fastmcp-engine`, `area:orchestration`, `area:evals-benchmarks`, or `area:governance`
- `python scripts/sync_tasks.py --create-pr CAN-XXX` automatically resolves and attaches the milestone, labels, author, and reviewer.

### 24. Follow-Up Issue & Backlog Governance (Anti-Orphan Invariant)
- When any AI agent identifies deferred architectural optimizations, technical debt items, or follow-up tasks and creates issues in Linear:
  1. **Zero-Orphan Project Attachment:** Every Linear issue MUST be attached to the parent project (`Canadian-Open-Data-Agentic-Platform`) or its specific Milestone project. Unparented issues are strictly prohibited.
  2. **Mandatory Explicit Ownership:** Every issue MUST be assigned to an explicit developer (`Benjamin`, `Samir`, or `Yassir`) based on role ownership. Never leave an issue unassigned (`None`) or generic (`Owner: All`).
  3. **Sprint State & Tentative Due Date Discipline:** If an issue is scheduled for the active sprint, set its state to `Todo` (never leave forgotten in `Backlog`) and assign a tentative `dueDate` matching the sprint milestone end date.
  4. **Bidirectional TASKS.md Synchronization:** New follow-up tasks MUST be immediately mirrored in `TASKS.md` under the target milestone with their canonical key (e.g. `CAN-17`) so that `scripts/sync_tasks.py` tracks them locally and across automated workflows.

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

### `.env`-Based Developer Resolution Protocol:
Before prompting the developer, the agent MUST read the `.env` file in the repository root:
1. **If `CANDATA_TEAM_MEMBER` is present and non-empty:**
   - Immediately greet the human developer by their name:
     > *"Welcome back, <Name>! Ready to continue building CanData-MCP."*
   - Automatically adopt their corresponding role guidelines without asking for confirmation.
2. **If `CANDATA_TEAM_MEMBER` is missing or empty:**
   - Prompt the user on the very first turn:
     > *"Welcome to the CanData team workspace! Which team member are you today?*  
     > *1: Benjamin (Solutions Architect & Lead)*  
     > *2: Samir (Data Visualization & Agent Evals Lead)*  
     > *3: Yassir (Technology Delivery & Transformation Lead)"*
   - Once the user answers, write or update `CANDATA_TEAM_MEMBER=<Selected Name>` in `.env` so that all subsequent sessions and subagents automatically greet and identify them.

### Role-Specific Guidelines:
- **Role 1 (Benjamin Sanchez Zebadua — Solutions Architect & Lead):** Focus on monorepo structure, FastMCP 2.0 core, DuckDB 1.2+ Arrow streaming engine, Next.js architecture, CI/CD pipelines, Docker container hardening, and public API rate-limiting security.
- **Role 2 (Samir Ibrahim — Data Viz & Evals):** Focus on GTA Housing ground-truth benchmarks, LangGraph agent reasoning nodes, DeepEval CI suites, dynamic Plotly economic trend charts, prompt injection defense, and LLM evaluation safety guardrails.
- **Role 3 (Yassir Tagelsir Khougali — Tech Delivery & Transformation):** Focus on LangGraph Human-in-the-Loop (`interrupt()`) workflows, OpenTelemetry token telemetry, user testing scripts, Linear agile sprint tracking, Canadian data lineage tracking, and audit logging governance.

*(Note: Martin Torres' profile is archived in `collaboration/team-archive/martin_torres_profile.md` for subsequent phases).*
