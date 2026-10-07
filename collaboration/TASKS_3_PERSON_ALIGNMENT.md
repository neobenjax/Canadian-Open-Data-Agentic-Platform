# Implementation Task Tracker: 3-Person Team Realignment

This task file tracks all implementation activities required to adjust the Canadian Open Data Agentic Platform repository for a 3-person core team (Benjamin Sanchez Zebadua, Samir Ibrahim, Yassir Tagelsir Khougali) while backing up Martin Torres' profile.

---

## Task Checklist

### Phase 1: Archival & Backup
- [x] **T-01:** Create `collaboration/team-archive/martin_torres_profile.md` with Martin's bio, LinkedIn link, and credentials.
- [x] **T-02:** Backup photo asset to `assets/team/archive/martin.jpg` and `apps/portfolio-site/assets/team/archive/martin.jpg`.

### Phase 2: Core Documentation & Roster Updates
- [x] **T-03:** Update `ABOUT_THE_TEAM.md` to feature Benjamin, Samir, and Yassir as the active core team, noting the triangular review loop and linking to the archive.
- [x] **T-04:** Update `collaboration/ABOUT_THE_TEAM.md` with matching 3-person roster.

### Phase 3: AI Agent Persona & Rules Alignment
- [x] **T-05:** Update `AGENTS.md` to 3 active personas (Benjamin, Samir, Yassir) with distributed security/governance responsibilities.
- [x] **T-06:** Update `.cursorrules` with the 3 active personas.
- [x] **T-07:** Add Automated Feature Execution Protocol from `CONTRIBUTING.md` into `AGENTS.md` and `.cursorrules` so all agents autonomously execute branch verification, linting, tests, conventional commit, push, and PR assignment.

### Phase 4: Task Board & Milestone Realignment
- [x] **T-08:** Update `TASKS.md` header to 3-person core collective.
- [x] **T-09:** In `TASKS.md`, remove `CAN-04` from Milestone 0 (Sprint 0) and configure triangular review loop (Benjamin &rarr; Samir &rarr; Yassir &rarr; Benjamin).
- [x] **T-10:** In `TASKS.md`, reassign future milestone tasks previously assigned to Martin across the 3 members.

### Phase 5: Master Architecture Plan & Kickoff Deck
- [x] **T-11:** Update `CANADIAN_AGENTIC_DATA_PLATFORM_PLAN.md` team structure and rotation matrices to 3 members.
- [x] **T-12:** Update `presentation/index.html` Slide 4 (team cards), Slide 6/7 (rotation), and Slide 10 (Sprint 0 checklist).
- [x] **T-13:** Create `docs/ONBOARDING_WORKFLOW_EXAMPLES.md` with concrete task walkthroughs (`CAN-01`, `CAN-02`, `CAN-03`) and AI copy-paste prompts for today's kickoff onboarding meeting.

### Phase 6: Portfolio Landing Page Layout
- [x] **T-14:** Update `apps/portfolio-site/index.html` team section CSS to 3-column layout (`repeat(3, 1fr)`) and cards to the 3 active members.

### Phase 7: Account Setup & Task Sync Automation
- [x] **T-15:** Create `scripts/sync_tasks.py` zero-dependency CLI utility for parsing `TASKS.md`, filtering by owner, and bidirectionally syncing with Linear GraphQL API.
- [x] **T-16:** Create `docs/DEVELOPER_SETUP_AND_AUTOMATION_GUIDE.md` covering SSH signing keys, Linear MCP config, and `sync_tasks.py` commands.
- [x] **T-17:** Update `AGENTS.md` and `.cursorrules` with account setup instructions and task status synchronization rules.

### Phase 8: Verification & Walkthrough
- [x] **T-18:** Verify all links, images, CLI tool, and layout locally.
- [x] **T-19:** Create detailed `walkthrough.md` artifact.
- [ ] **T-20:** Request user review and approval before committing and merging.
