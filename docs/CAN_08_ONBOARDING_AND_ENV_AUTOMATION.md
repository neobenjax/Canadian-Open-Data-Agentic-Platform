# CAN-08: Linear Environment Wizard, Project Hierarchy & Agent PR Automation

**Task Key:** `CAN-08`  
**Linear Issue:** [`[CAN-08] Linear .env Setup Wizard, Project Hierarchy Automation, and State Reconciliation` (BEN-42)](https://linear.app/canopendataagenticplatform/issue/BEN-42/can-08-linear-env-setup-wizard-project-hierarchy-automation-and-state)  
**Pull Request:** [GitHub PR #4](https://github.com/neobenjax/Canadian-Open-Data-Agentic-Platform/pull/4)  
**Author / Lead:** **Benjamin Sanchez Zebadua** (`@neobenjax`)  
**Designated Peer Reviewer:** **Samir Omer** (`@samiromer2`)  
**Status:** In Review  

---

## 1. Executive Summary

This chore establishes the complete developer onboarding foundation, automated Linear issue synchronization, parent project hierarchy, and proactive agent Pull Request protocols for the **Canadian Open Data Agentic Platform**.

It provides team members with a 1-command zero-friction onboarding flow while configuring enterprise guardrails (SSH commit signing, branch protection, and triangular peer reviews).

---

## 2. Linear Team Key & Issue Auto-Closing Note (The "Claude" Observation)

> [!IMPORTANT]
> **Linear Issue Closing Syntax (`BEN-XX` vs `CAN-XX`):**
> In our Linear workspace (`canopendataagenticplatform`), the underlying team identifier key is **`BEN`**.
>
> While our project tasks use the semantic convention `[CAN-XX]` in issue titles and `TASKS.md`, GitHub's native Linear integration **only auto-closes issues when referenced by their native team key** (e.g., `Closes BEN-42` or `Closes BEN-6`).
>
> Therefore, every Pull Request description MUST include:
> ```markdown
> Closes BEN-XX
> Closes CAN-XX
> ```
> This ensures that upon PR merge to `main`, Linear automatically transitions the card to **Done**.

---

## 3. Core Deliverables & Technical Architecture

### 3.1. Zero-Dependency `.env` Setup Wizard
Located in [`scripts/sync_tasks.py`](../scripts/sync_tasks.py):
- Automatically checks for the presence of `.env`.
- If missing, launches an interactive CLI wizard prompting for the personal Linear API key (`lin_api_...`) and GitHub Personal Access Token (`ghp_...`).
- Creates a sanitized local `.env` and provides [` .env.example`](../.env.example) for git tracking.
- Implements custom pure Python `.env` file parsing with zero external pip dependencies.

### 3.2. Option 1: Linear Hierarchy Reorganization
- Reorganized the Linear workspace under the unified parent project **`Canadian-Open-Data-Agentic-Platform`** (Slug: `d0e8b9397d7e`) with **Benjamin Sanchez Zebadua** set as Project Lead.
- Created 7 native `ProjectMilestone` records (Milestones 0 through 6).
- Migrated all 36 tasks to point directly to the parent project and their respective native milestone.
- Reconciled initial task states:
  - `CAN-00` (`BEN-41`) $\rightarrow$ **Done**
  - `CAN-02` (`BEN-6`) $\rightarrow$ **In Review**
  - `CAN-08` (`BEN-42`) $\rightarrow$ **In Review**
  - Archived legacy standalone milestone projects to keep the workspace uncluttered.

### 3.3. Proactive Agent Pull Request & HITL Reviewer Validation
Updated [`AGENTS.md`](../AGENTS.md) and [`.cursorrules`](../.cursorrules):
- **Mandatory Proactive Prompt:** Coding assistants (Cursor, Claude Code, Antigravity, Copilot) must proactively ask the developer upon pushing changes whether to open the PR automatically.
- **Mandatory Human-in-the-Loop (HITL) Validation:** Prompts the developer to confirm or customize the assigned reviewer before creating the PR.
- **Verified GitHub Handles:**
  - Benjamin's PRs $\rightarrow$ Default Reviewer: **Samir Omer** (`@samiromer2`)
  - Samir's PRs $\rightarrow$ Default Reviewer: **Yassir Khougali** (`@yassirtmk`)
  - Yassir's PRs $\rightarrow$ Default Reviewer: **Benjamin Sanchez** (`@neobenjax`)

### 3.4. Workspace Chore Cleanup
- Permanently deleted `CAN-06` / `BEN-9` (daily WhatsApp check-in) as non-repo chores.
- Assigned all architecture and shared repository tasks to **Benjamin Sanchez**.
- Assigned GTA benchmark and evaluation tasks to **Samir Omer**.
- Maintained unassigned status for Yassir's upcoming tasks (`CAN-03`, `CAN-26`, `CAN-35`) until his Linear onboarding.

---

## 4. Verification & Status Summary

| Item | Status | Verification Command / URL |
|---|---|---|
| **Linear Issue** | `BEN-42` (In Review) | [Linear Issue BEN-42](https://linear.app/canopendataagenticplatform/issue/BEN-42) |
| **GitHub Pull Request** | Open (#4) | [PR #4 on GitHub](https://github.com/neobenjax/Canadian-Open-Data-Agentic-Platform/pull/4) |
| **PR Attachment** | Attached to `BEN-42` | Visible in Linear under Attachments |
| **Reviewer Assigned** | `@samiromer2` | Verified via GitHub API |
| **Local Status** | Synchronized | `python scripts/sync_tasks.py --sync-linear` |
