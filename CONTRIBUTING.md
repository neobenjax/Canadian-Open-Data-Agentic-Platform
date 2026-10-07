# Contributing & Branch Protection Guide

Welcome to the **Canadian Open Data Agentic Platform**! To guarantee production-grade code quality, security, and seamless collaboration across our 3-person core team (**Benjamin Sanchez Zebadua**, **Samir Ibrahim**, **Yassir Tagelsir Khougali**), this repository enforces strict branch protection and GitHub rulesets.

---

## 1. Active Branch Protection Rule (Enforced on `main`)

Our GitHub repository enforces the following rule on branch `main`:

> 🔒 **Direct pushes to `main` are strictly blocked.**  
> All code contributions MUST be submitted through a Pull Request and approved by at least **1 peer reviewer** before merging.

### Summary of Active Protections:
- **Require a pull request before merging:** Enabled.
- **Require approvals:** **1 approval minimum**. Pull requests targeting `main` cannot be merged until another team member has reviewed and approved the changes.
- **No unreviewed code:** Merging is disabled until review requirements are satisfied.
- **Linear history:** Recommended to maintain a clean git graph without merge bubbles.

---

## 2. Standard Feature Branch Workflow

Every team member and AI coding assistant MUST follow this workflow:

```mermaid
flowchart LR
    A[Linear Task: CAN-XXX] --> B[git checkout main && git pull origin main]
    B --> C[git checkout -b feat/CAN-XXX-description]
    C --> D[Write Code & Run uv run pytest]
    D --> E[git commit -m '[CAN-XXX] feat: description']
    E --> F[git push -u origin feat/CAN-XXX-description]
    F --> G[Open PR with template & Closes CAN-XXX]
    G --> H[Triangular Reviewer Approves]
    H --> I[Merge to main & Purge Branch]
```

### Step-by-Step Instructions:

1. **Always start from the latest `main`:**
   ```bash
   git checkout main
   git pull origin main
   ```

2. **Create your feature branch:**
   Format: `feat/<issue-id>-<short-description>` or `fix/<issue-id>-<short-description>`  
   *(The issue ID comes from your Linear task, e.g. `CAN-02`)*:
   ```bash
   git checkout -b feat/CAN-02-profile-and-benchmarks
   ```

3. **Develop & Run Pre-Flight Checks:**
   ```bash
   uv run ruff check .
   uv run pytest
   ```

4. **Commit your changes using Conventional Commits with Linear Key:**
   ```bash
   git add .
   git commit -m "[CAN-02] feat: update bio and add initial benchmark draft"
   ```

5. **Push your branch to GitHub:**
   ```bash
   git push -u origin feat/CAN-02-profile-and-benchmarks
   ```

6. **Open a Pull Request:**
   - Go to GitHub and open a PR targeting `main`.
   - Ensure the PR description includes `Closes CAN-XXX`.
   - Assign your assigned peer reviewer based on the **Triangular Review Cycle**:
     - **Benjamin's PRs** $\rightarrow$ Request review from **Samir** (`@samiroibrahim`)
     - **Samir's PRs** $\rightarrow$ Request review from **Yassir** (`@yassir-tagelsir-khougali`)
     - **Yassir's PRs** $\rightarrow$ Request review from **Benjamin** (`@neobenjax`)

7. **Address Feedback, Approve & Merge:**
   - Once your teammate approves the PR, merge it into `main`.

8. **Purge the Merged Feature Branch:**
   ```bash
   git checkout main
   git pull origin main
   git branch -d feat/CAN-02-profile-and-benchmarks
   git push origin --delete feat/CAN-02-profile-and-benchmarks
   ```

---

## 3. Seamless Integration with AI Coding Assistants

All AI coding assistants in this repository (**Claude Code, Cursor, Antigravity, Codex, Copilot**) are configured via [`AGENTS.md`](AGENTS.md) and [`.cursorrules`](.cursorrules) to enforce this exact workflow automatically.

### What Team Members Can Tell Their AI Agent:
You don't need to manually run git commands if you don't want to. You can simply prompt your assistant:

> *"I am starting work on task CAN-02. Please create the feature branch, make the changes to my bio and benchmark questions, verify all tests pass, and commit following our Contributing guide."*

The Agent will automatically:
1. Verify latest `main` and branch off to `feat/CAN-02-...`.
2. Implement your code modifications.
3. Run `uv run ruff check .` and `uv run pytest`.
4. Commit with `[CAN-02] feat: ...`.
5. Push the feature branch and generate your PR link with your designated triangular reviewer.

---

## 4. Recommended GitHub Rulesets to Deepen Security & Quality

To elevate this repository to enterprise engineering standards, we recommend enabling the following settings under **GitHub Repository Settings $\rightarrow$ Rules $\rightarrow$ Rulesets** (or Branch Protection):

| Recommended Rule | Why It Protects Our Team |
|---|---|
| **Dismiss stale approvals when new commits are pushed** | If an approver gives a green light and the author pushes 5 new commits, the approval is revoked until re-reviewed. Prevents accidental bugs from sneaking in after approval. |
| **Require status checks to pass before merging** | Blocks PR merges if automated CI workflows (`ruff check`, `pytest`, `pyright`) fail. Guarantees broken code never enters `main`. |
| **Require conversation resolution before merging** | Ensures all review comments and questions raised by teammates must be marked "Resolved" before the merge button unlocks. |
| **Block force pushes (`--force`)** | Disables `git push --force` on `main` to prevent anyone from accidentally overwriting repository history. |
| **Block branch deletion** | Prevents anyone from accidentally deleting `main`. |
| **GitHub Secret Scanning & Push Protection** | Automatically detects and blocks commits containing API keys, private tokens, or passwords before they reach GitHub. (Settings $\rightarrow$ Code security and analysis $\rightarrow$ Secret scanning). |

---

## 5. Local Developer Pre-Flight Checklist

Before opening any PR, ensure your local environment passes these sanity checks:
```bash
# 1. Check code formatting & linting
uv run ruff check .

# 2. Run unit tests
uv run pytest

# 3. Verify type annotations
uv run pyright
```
