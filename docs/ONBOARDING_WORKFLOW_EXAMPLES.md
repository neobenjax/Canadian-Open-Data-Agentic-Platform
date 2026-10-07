# Team Onboarding & Workflow Walkthrough (Kickoff Meeting Guide)

**Welcome to the Canadian Open Data Agentic Platform engineering collective!**  
This guide is designed for our kickoff onboarding meeting. It walks through real, end-to-end task examples demonstrating our collaborative git flow, GitHub branch protection, Linear task tracking, and how our AI coding assistants (**Cursor, Claude Code, Antigravity, Copilot**) automate this entire workflow.

---

## 🧭 The Core Workflow in 60 Seconds

Our repository enforces **GitHub Branch Protection on `main`**. Direct pushes to `main` are strictly blocked. Every change must be made on a feature branch, submitted via Pull Request, and approved by a teammate.

```mermaid
flowchart TD
    A[1. Claim Task in Linear: CAN-XXX] --> B[2. AI Agent or Dev: git checkout -b feat/CAN-XXX-name]
    B --> C[3. Implement Code / File Changes]
    C --> D[4. Pre-Flight Verification: uv run ruff check && pytest]
    D --> E[5. Commit: [CAN-XXX] feat: description]
    E --> F[6. Push: git push -u origin feat/CAN-XXX-name]
    F --> G[7. Open PR on GitHub with Closes CAN-XXX]
    G --> H[8. Assigned Teammate Reviews & Approves]
    H --> I[9. Merge PR into main]
    I --> J[10. Purge Feature Branch Locally & on GitHub]
```

---

## 🧪 Live Kickoff Meeting Demonstration: The Sandbox Task (`CAN-00`)

To demonstrate the full gitflow and Linear status synchronization during the kickoff meeting **without consuming or touching anyone's personal onboarding chore**, use the dedicated test ticket:

- **Issue Key:** `CAN-00`
- **Title:** `[CAN-00] Kickoff Onboarding Workflow Test Sandbox`
- **Target File:** `collaboration/tests/sandbox.md`

### Live Step-by-Step Demo Script:

1. **Pick up the task & set status to `IN PROGRESS`:**
   ```bash
   python scripts/sync_tasks.py --mark-in-progress CAN-00 --assignee Benjamin
   ```
   *(Linear moves `CAN-00` card to **In Progress** and `TASKS.md` marks `[IN PROGRESS]`)*

2. **Branch from `main`:**
   ```bash
   git checkout main && git pull origin main
   git checkout -b feat/CAN-00-test-workflow-sandbox
   ```

3. **Make test edit in `collaboration/tests/sandbox.md`:**
   Add a verification row in the table:
   ```markdown
   | 2026-10-07 | Benjamin Sanchez | Live demo during onboarding kickoff | Passed |
   ```

4. **Pre-Flight check, commit, and push:**
   ```bash
   uv run ruff check .
   git add collaboration/tests/sandbox.md
   git commit -m "[CAN-00] test: live demonstration of gitflow and linear sync"
   git push -u origin feat/CAN-00-test-workflow-sandbox
   ```

5. **Set status to `IN REVIEW` & open PR:**
   ```bash
   python scripts/sync_tasks.py --mark-in-review CAN-00
   ```
   Open PR on GitHub with Title `[CAN-00] test: live demonstration of gitflow and linear sync` and body:
   ```markdown
   ## Description
   Live meeting demonstration of branch protection, commit signing, and review workflow.
   
   Closes CAN-00
   ```

6. **Peer Approval & Merge:**
   - Reviewer clicks **Approve** on GitHub.
   - Author clicks **Squash and Merge**.

7. **Set status to `DONE` & Purge Branch:**
   ```bash
   python scripts/sync_tasks.py --mark-done CAN-00
   git checkout main && git pull origin main
   git branch -d feat/CAN-00-test-workflow-sandbox
   git push origin --delete feat/CAN-00-test-workflow-sandbox
   ```
   *(Linear card is moved to **Done**, `TASKS.md` checkbox becomes `[x]`, and the branch is clean).*

---

## 🔄 The Triangular Peer Review Loop

With our 3-person core team (**Benjamin**, **Samir**, **Yassir**), code reviews follow a clear triangular cycle so everyone reviews real code and no single person becomes a bottleneck:

| PR Author | Assigned Reviewer | GitHub Handle |
|---|---|---|
| **Benjamin Sanchez** | **Samir Ibrahim** | `@samiroibrahim` |
| **Samir Ibrahim** | **Yassir Khougali** | `@yassir-tagelsir-khougali` |
| **Yassir Khougali** | **Benjamin Sanchez** | `@neobenjax` |

---

## 🛠️ Real Example 1: Samir's Onboarding Chore (`CAN-02`)

### The Linear Ticket
- **Issue Key:** `CAN-02`
- **Title:** `[CAN-02] Samir's Onboarding Chore: Bio update & initial benchmark questions`
- **Objective:** Verify GitFlow and add 3 sample GTA housing ground-truth benchmark questions.

---

### Option A: The "Zero-Friction" AI Agent Method (Recommended)
You do not need to memorize git commands. You can simply open your AI assistant (**Cursor, Claude Code, Antigravity**) and type:

> **Prompt to your Agent:**  
> *"I am starting work on Linear task CAN-02. Please check out the feature branch from latest main, update my bio in ABOUT_THE_TEAM.md, draft 3 GTA housing questions in collaboration/benchmarks/benchmark_questions_draft.md, verify that tests pass, and commit following our CONTRIBUTING.md guide."*

#### What Your Agent Does Autonomously:
1. Runs `git checkout main && git pull origin main`.
2. Creates feature branch: `git checkout -b feat/CAN-02-profile-and-benchmarks`.
3. Edits `ABOUT_THE_TEAM.md` and creates `collaboration/benchmarks/benchmark_questions_draft.md`.
4. Runs pre-flight verification: `uv run ruff check .` and `uv run pytest`.
5. Commits: `git commit -m "[CAN-02] feat: update bio and add initial GTA housing benchmark questions"`.
6. Pushes: `git push -u origin feat/CAN-02-profile-and-benchmarks`.
7. Prints your GitHub PR link and instructs you to assign **Yassir** as your reviewer.

---

### Option B: The Manual Terminal Method (For CLI Enthusiasts)
If you prefer running terminal commands directly:

```bash
# 1. Update main and branch out
git checkout main
git pull origin main
git checkout -b feat/CAN-02-profile-and-benchmarks

# 2. Make your edits (e.g., in VS Code / Cursor)
# - Edit ABOUT_THE_TEAM.md
# - Create collaboration/benchmarks/benchmark_questions_draft.md

# 3. Run pre-flight checks
uv run ruff check .
uv run pytest

# 4. Stage and commit with Linear key
git add .
git commit -m "[CAN-02] feat: update bio and add initial GTA housing benchmark questions"

# 5. Push to GitHub
git push -u origin feat/CAN-02-profile-and-benchmarks
```

---

### The GitHub PR & Peer Review Step
1. Navigate to: `https://github.com/neobenjax/Canadian-Open-Data-Agentic-Platform/pulls`.
2. Click **New Pull Request** with base `main` $\leftarrow$ compare `feat/CAN-02-profile-and-benchmarks`.
3. **PR Title:** `[CAN-02] feat: update bio and add initial GTA housing benchmark questions`
4. **PR Description:**
   ```markdown
   Closes CAN-02

   ### Summary of Changes
   - Updated Samir Ibrahim's profile in ABOUT_THE_TEAM.md
   - Created draft benchmark questions in collaboration/benchmarks/benchmark_questions_draft.md
   - Verified local linter and pytest tests pass
   ```
5. **Assign Reviewer:** Select **Yassir Khougali** (`@yassir-tagelsir-khougali`).

---

### How Yassir Reviews & Approves:
1. Yassir receives a GitHub notification or clicks the PR link.
2. Under **"Files changed"**, Yassir reviews the markdown additions.
3. Because branch protection is active, the green **"Merge pull request"** button is **disabled** with the message:  
   *“Merging is blocked: At least 1 approving review is required.”*
4. Yassir clicks **Review changes** $\rightarrow$ selects **Approve** $\rightarrow$ submits review.
5. The **"Merge pull request"** button turns green!

---

### Merge & Branch Purge Step:
Once approved, Samir (or Yassir) clicks **Merge pull request** $\rightarrow$ **Confirm merge**.  
Then run locally:
```bash
git checkout main
git pull origin main
git branch -d feat/CAN-02-profile-and-benchmarks
git push origin --delete feat/CAN-02-profile-and-benchmarks
```
*(Linear will automatically transition `CAN-02` to **Done** because the PR description included `Closes CAN-02`).*

---

## 🛠️ Real Example 2: Yassir's Onboarding Chore (`CAN-03`)

### The Linear Ticket
- **Issue Key:** `CAN-03`
- **Title:** `[CAN-03] Yassir's Onboarding Chore: Bio update & meeting notes template`
- **Assigned Reviewer:** **Benjamin Sanchez** (`@neobenjax`)

### What Yassir Tells His Agent:
> *"I am working on task CAN-03. Please create feature branch feat/CAN-03-profile-and-meeting-notes from main, update my bio in ABOUT_THE_TEAM.md, create collaboration/meetings/sprint_0_trial_notes.md with a weekly meeting template, run verification checks, and push following our contributing guidelines."*

### What Benjamin Does:
- Benjamin inspects Yassir's PR, reviews the meeting notes template, clicks **Approve**, and confirms the merge into `main`.

---

## 🛠️ Real Example 3: Benjamin's Onboarding Chore (`CAN-01`)

### The Linear Ticket
- **Issue Key:** `CAN-01`
- **Title:** `[CAN-01] Benjamin's Onboarding Chore: Lead bio update & project badges`
- **Assigned Reviewer:** **Samir Ibrahim** (`@samiroibrahim`)

### What Benjamin Tells His Agent:
> *"I am working on task CAN-01. Please branch from latest main into feat/CAN-01-profile-update, update my bio in ABOUT_THE_TEAM.md, verify tests pass, commit with [CAN-01] Conventional Commit, and push to origin."*

### What Samir Does:
- Samir reviews Benjamin's PR, approves it, and unlocks the merge to `main`.

---

## 💡 Quick Tips for Daily Teamwork

1. **Daily 2-Minute WhatsApp Async Check-in (Before 10:00 AM EST):**  
   - *Yesterday:* What you completed (e.g. "Opened PR #3 for CAN-02").  
   - *Today:* What you're picking up next.  
   - *Blockers:* Anything stuck >2 hours or day job conflicts.
2. **Weekly Sync Demo:**  
   - Use `/frontend-slides` ([zarazhangrui/frontend-slides](https://github.com/zarazhangrui/frontend-slides)) to generate a quick 2-slide interactive deck with your screenshots or benchmark outputs.
3. **If You Encounter a Branch Violation Error:**  
   - If git rejects a push with `remote: error: Changes must be made through a pull request`, don't panic! It means GitHub branch protection is working perfectly. Check your branch (`git status`) and push to `feat/CAN-XXX-...` instead.
