# Task Activities: CAN-62 LinkedIn Showcase & Video/GIF Generator Workflow

## 📋 Task Overview
- **Issue Key:** `CAN-62` (Linear: `BEN-38`)
- **Feature Branch:** `feat/CAN-62-linkedin-showcase-video-generator`
- **Owner:** Benjamin Sanchez Zebadua
- **Objective:** Build an automated, high-fidelity LinkedIn showcase video and animated GIF generator pipeline, capture live screenshots across Monorepo, Distribution mirror, Linear, and GitHub PR rulesets, and create a reusable workflow for weekly sprint social updates.

---

## 🛠️ Implementation Checklist

- [x] **Phase 1: Environment & Guardrail Alignment**
  - [x] Verify Gitflow: Checkout feature branch `feat/CAN-62-linkedin-showcase-video-generator`.
  - [x] Transition Linear issue `CAN-62` to *In Progress*.
  - [x] Update `AGENTS.md` and `.env.example` with `.env`-based team member resolution and personalized greetings.
  - [x] Create this task activities tracking file (`docs/CAN_62_TASK_ACTIVITIES.md`).

- [x] **Phase 2: Live Screenshot & Asset Capture**
  - [x] Capture live screenshot of GTA Housing Ground-Truth Benchmark (`collaboration/benchmarks/benchmark_questions_draft.md`) on GitHub.
  - [x] Capture live screenshot of Monorepo structure & README (`Canadian-Open-Data-Agentic-Platform`).
  - [x] Capture live screenshot of Linear.app project board (sprint milestones, completed CAN-00..08 tasks).
  - [x] Capture live screenshot of merged PR with Linear key link (`BEN-XX` / `CAN-XX`).
  - [x] Capture live screenshot of GitHub repository rulesets / branch protection settings.
  - [x] Capture live screenshot of distribution mirror repo (`Canadian-Open-Data-Agentic-Platform-MCP-Server`).
  - [x] Store raw captures in `collaboration/social/assets/` and `presentation/social-showcase/assets/`.

- [x] **Phase 3: Interactive 16:9 Motion Stage & Storyboard Engine**
  - [x] Create `presentation/social-showcase/index.html` with fixed 16:9 aspect ratio (`1920x1080` canvas).
  - [x] Implement Scene 1 (The Hook): Toronto 2-bedroom rent hallucination ($2,640 vs. $2,045 official StatCan Table 34-10-0133-01 / v3823103).
  - [x] Implement Scene 2 (Monorepo Engine): Monorepo folder hierarchy & DuckDB Arrow streaming engine callouts.
  - [x] Implement Scene 3 (Agent-in-the-Loop Gitflow): Linear tickets + branch protocol + PR auto-close verification.
  - [x] Implement Scene 4 (Peer Review Guardrail): GitHub branch protection rule screenshot + Triangular review diagram (Benjamin -> Samir -> Yassir -> Benjamin).
  - [x] Implement Scene 5 (Distribution Mirror Pipeline): Monorepo `publish-mcp-server.yml` automated downstream sync with individual author attribution diagram.
  - [x] Implement Scene 6 (CTA & Engagement): "What Canadian data question would you want an AI agent to answer correctly?" + GitHub link + team tags.
  - [x] Build in-browser WebM/MP4 recorder & frame exporter directly in the showcase player.

- [x] **Phase 4: Python CLI Showcase Generator & Post Draft Integration**
  - [x] Create `scripts/generate_social_showcase.py` to automate headless asset rendering, video generation, and GIF compilation.
  - [x] Create `collaboration/social/sprint_showcase_config.yaml` as the reusable template for future sprint posts.
  - [x] Support both MP4/WebM video export and optimized looping GIF generation via Pillow (<15MB for LinkedIn).

- [x] **Phase 5: Manual Walkthrough & Verification**
  - [x] Verify local rendering in Chromium browser.
  - [x] Verify Python scripts syntax with `py_compile`.
  - [x] Write detailed walkthrough guide in `docs/CAN_62_LINKEDIN_SHOWCASE_WALKTHROUGH.md` with instructions on how to test, preview, and export.
  - [ ] Request user review and approval before committing, pushing, or merging.
