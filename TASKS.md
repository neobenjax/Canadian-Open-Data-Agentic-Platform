# Project Task Board & Milestone Matrix (Jira-Style Hierarchy)
**Project:** Canadian Open Data Agentic Platform (`CanData-MCP` & LangGraph Multi-Agent Suite)  
**Repository:** [neobenjax/Canadian-Open-Data-Agentic-Platform](https://github.com/neobenjax/Canadian-Open-Data-Agentic-Platform.git)  
**Linear Workspace:** [CanData Platform (Team Key: `CAN`)](https://linear.app/canopendataagenticplatform/team/CAN/active)  
**Team Collective (3-Person Core):**
- **Benjamin Sanchez Zebadua** (Project Lead / Solutions Architect)
- **Samir Ibrahim** (Co-Lead / Data & Evals Lead)
- **Yassir Tagelsir Khougali** (Technology Delivery & Transformation Lead)  
*(Martin Torres archived in `collaboration/team-archive/` for subsequent phases)*

---

## 📅 Team Cadence & Communication Guidelines
- **Weekly Time Commitment:** 2 to 4 hours per week per team member. Flexible pace with weekly plan adaptations.
- **Daily Async Check-in:** Brief message in the WhatsApp group before 10:00 AM EST (Done yesterday, Today's focus, Blockers).
- **Weekly Sync Meeting:** Weekly progression demo meeting (Day & time agreed weekly).
- **Demo Rule:** Every member creates a brief 2-3 slide presentation using `/frontend-slides` ([repo](https://github.com/zarazhangrui/frontend-slides)) showcasing screenshots, metrics, and progress.
- **Support Rule:** *"Never Silently Blocked"* — stuck for >2 hours or day job is demanding? Flag it early so a teammate can pair up or rebalance tasks.

---

## 🎯 Milestone 0: Team Onboarding & Gitflow Trial Week (Sprint 0)
**Dates:** Wednesday, October 7, 2026 – Wednesday, October 14, 2026  
**Goal:** Verify that every team member can connect to Linear, create a feature branch, edit a purposeful file, push a commit, open a Pull Request, conduct a peer review via the triangular review loop, and merge to `main` with GitHub branch protection enabled. Zero project coding required.

### Feature 0.1: Developer Environment & Profile Verification Chores
- [ ] **CAN-00 (Kickoff Onboarding Workflow Test Sandbox):** 
  - *Goal:* Verify end-to-end Gitflow & Linear synchronization workflow during the onboarding kickoff meeting without altering personal profile tasks.  
  - *Steps:* Pick up `CAN-00` in Linear $\rightarrow$ Set status `IN PROGRESS` $\rightarrow$ Create branch `feat/CAN-00-test-workflow-sandbox` $\rightarrow$ Add or modify test entry in `collaboration/tests/sandbox.md` $\rightarrow$ Push branch $\rightarrow$ Set status `IN REVIEW` $\rightarrow$ Open PR $\rightarrow$ Triangular peer review $\rightarrow$ Merge to `main` $\rightarrow$ Set status `DONE` $\rightarrow$ Purge feature branch.  
  - *Estimate:* 15 min · *Owner:* All Team Members (Kickoff Live Demo)
- [ ] **CAN-01 (Benjamin's Onboarding Chore):**  
  - *Goal:* Verify workflow & update developer bio.  
  - *Steps:* Claim `CAN-01` in Linear $\rightarrow$ Create branch `feat/CAN-01-profile-update` $\rightarrow$ Add personal bio and links in `ABOUT_THE_TEAM.md` $\rightarrow$ Push branch $\rightarrow$ Open PR $\rightarrow$ Request review from Samir.  
  - *Estimate:* 1 hour · *Owner:* Benjamin Sanchez Zebadua
- [ ] **CAN-02 (Samir's Onboarding Chore):** 
  - *Goal:* Verify workflow, update bio & draft initial benchmark questions.  
  - *Steps:* Claim `CAN-02` in Linear $\rightarrow$ Create branch `feat/CAN-02-profile-and-benchmarks` $\rightarrow$ Add personal bio in `ABOUT_THE_TEAM.md` and create `collaboration/benchmarks/benchmark_questions_draft.md` with 3 sample housing ground-truth questions $\rightarrow$ Push branch $\rightarrow$ Open PR $\rightarrow$ Request review from Yassir.  
  - *Estimate:* 1 hour · *Owner:* Samir Ibrahim
- [ ] **CAN-03 (Yassir's Onboarding Chore):**  
  - *Goal:* Verify workflow, update bio & add meeting notes template.  
  - *Steps:* Claim `CAN-03` in Linear $\rightarrow$ Create branch `feat/CAN-03-profile-and-meeting-notes` $\rightarrow$ Add personal bio in `ABOUT_THE_TEAM.md` and create `collaboration/meetings/sprint_0_trial_notes.md` with weekly sync template $\rightarrow$ Push branch $\rightarrow$ Open PR $\rightarrow$ Request review from Benjamin.  
  - *Estimate:* 1 hour · *Owner:* Yassir Tagelsir Khougali

### Feature 0.2: Triangular Peer Review & Branch Protection Verification
- [ ] **CAN-05 (Branch Protection & PR Approval Test):**  
  - *Goal:* Verify that GitHub blocks direct pushes to `main` and enforces the 1-approval requirement across the triangular review cycle:
    - Benjamin's PR $\rightarrow$ Reviewed & approved by Samir
    - Samir's PR $\rightarrow$ Reviewed & approved by Yassir
    - Yassir's PR $\rightarrow$ Reviewed & approved by Benjamin  
  - *Steps:* Each member reviews and approves their assigned teammate's PR $\rightarrow$ Merge PR into `main` $\rightarrow$ Purge merged feature branch.  
  - *Estimate:* 1 hour · *Owner:* All Team Members
- [ ] **CAN-06 (WhatsApp Async Routine Test):**  
  - *Goal:* Post first 2-minute daily check-in on WhatsApp before 10:00 AM EST.  
  - *Estimate:* 15 min · *Owner:* All Team Members

---

## 🎯 Milestone 1: FastMCP 2.0 Core & Ground-Truth Benchmarks (Sprint 1)
**Dates:** October 14, 2026 – October 21, 2026  
**Goal:** Working FastMCP 2.0 server with DuckDB 1.2+ querying StatCan and Bank of Canada REST APIs; first 15 benchmark questions with ground truth.

### Feature 1.1: Official Canadian REST Connectors
- [ ] **CAN-11:** Implement async HTTPX client for Statistics Canada WDS API (metadata discovery, vector lookup, SDMX cube slice with HTTP caching). *(Owner: Benjamin / Yassir · 2h)*
- [ ] **CAN-12:** Implement async client for Bank of Canada Valet API (policy rate, inflation target, CPI series). *(Owner: Yassir / Benjamin · 2h)*

### Feature 1.2: In-Memory DuckDB Slicing Engine
- [ ] **CAN-13:** Build FastMCP 2.0 server with in-memory DuckDB Arrow streams reducing 200MB payloads to <3KB with tool annotations (`readOnly`, `idempotent`). *(Owner: Benjamin · 3h)*

### Feature 1.3: Benchmark Suite & Security Baseline
- [ ] **CAN-14:** Curate 15 ground-truth benchmark questions based on GTA housing, rent vs income, and inflation metrics. *(Owner: Samir · 2h)*
- [ ] **CAN-15:** Run baseline benchmark comparing plain Claude 3.5 Sonnet vs existing `mcp-statcan` vs CanData-MCP; log hallucinations and citation coverage. *(Owner: Samir / Yassir · 2h)*
- [ ] **CAN-16:** Conduct API security, rate limit, and data provenance audit for Canadian public endpoints. *(Owner: Benjamin / Yassir · 2h)*

---

## 🎯 Milestone 2: LangGraph Multi-Agent Orchestration & Observability (Sprint 2)
**Dates:** October 21, 2026 – October 28, 2026  
**Goal:** Stateful LangGraph 0.2+ multi-agent graph with Supervisor, Query Planner, Data Analyst, Citation Verifier, and OpenTelemetry tracing.

### Feature 2.1: LangGraph Agent Graph & State
- [ ] **CAN-21:** Define typed `AgentState` with Pydantic v2 schemas and `AsyncSqliteSaver` checkpointer for time-travel debugging. *(Owner: Samir / Benjamin · 2.5h)*
- [ ] **CAN-22:** Implement Supervisor agent node that decomposes complex queries into deterministic tool calls. *(Owner: Samir · 2.5h)*
- [ ] **CAN-23:** Implement Data Analyst node executing exact DuckDB SQL math (no mental math). *(Owner: Benjamin · 2.5h)*
- [ ] **CAN-24:** Implement Citation Verifier node checking statistics against official StatCan/BoC table IDs. *(Owner: Samir · 2h)*

### Feature 2.2: Observability & Telemetry
- [ ] **CAN-25:** Set up OpenTelemetry-native Arize Phoenix & LangSmith tracing to measure step latency and token costs per sub-agent. *(Owner: Yassir / Benjamin · 2h)*
- [ ] **CAN-26:** Bilingual French/English metadata mapping and data lineage tracking. *(Owner: Yassir · 2h)*

---

## 🎯 Milestone 3: Interactive Documentation Portal & Human-in-the-Loop (Sprint 3)
**Dates:** October 28, 2026 – November 4, 2026  
**Goal:** Next.js 15 documentation portal (`/apps/docs-portal`), Streamlit interactive analytics app, and LangGraph `interrupt()` HITL.

### Feature 3.1: Documentation & Developer Playground
- [ ] **CAN-31:** Scaffold Next.js 15 App Router + Fumadocs / Tailwind CSS v4 in `/apps/docs-portal`. *(Owner: Benjamin · 3h)*
- [ ] **CAN-32:** Build modern Streamlit UI with `astream_events` v2 real-time streaming and dynamic Plotly charts. *(Owner: Samir / Yassir · 2.5h)*
- [ ] **CAN-33:** Implement LangGraph `interrupt()` breakpoint when data ambiguities arise (e.g. municipal vs CMA boundaries). *(Owner: Samir / Benjamin · 2h)*

### Feature 3.2: Federal CKAN Integration & User Testing
- [ ] **CAN-34:** Add connector for Open Government Canada CKAN federal datasets. *(Owner: Yassir / Benjamin · 2h)*
- [ ] **CAN-35:** User testing session with 3 external Canadian policy/data researchers; log feedback. *(Owner: Yassir · 2h)*

---

## 🎯 Milestone 4: Automated CI/CD Evals & AI Security Guardrails (Sprint 4)
**Dates:** November 4, 2026 – November 11, 2026  
**Goal:** Automated regression testing in GitHub Actions with DeepEval and NIST/Inspect AI standards, plus Pydantic guardrails.

### Feature 4.1: Automated Evaluation Pipeline
- [ ] **CAN-41:** Implement DeepEval automated test harness running against 30 ground-truth questions. *(Owner: Samir · 2.5h)*
- [ ] **CAN-42:** Configure GitHub Actions CI pipeline running Ruff, Pyright, and DeepEval scoring on every PR. *(Owner: Benjamin · 2.5h)*

### Feature 4.2: AI Security Guardrails & Containerization
- [ ] **CAN-43:** Implement Pydantic v2 output validators and prompt injection defense; audit LLM tool calls. *(Owner: Samir · 2.5h)*
- [ ] **CAN-44:** Token cost optimization with prompt caching and compressed serialization. *(Owner: Yassir / Benjamin · 2h)*
- [ ] **CAN-45:** Containerize FastMCP server and LangGraph service; publish images to GHCR with Docker hardening. *(Owner: Benjamin · 2h)*

---

## 🎯 Milestone 5: PyPI Release, Cloud Hosting & Public Beta (Sprint 5)
**Dates:** November 11, 2026 – November 18, 2026  
**Goal:** Public PyPI package (`pip install candata-mcp`), Smithery.ai catalog submission, and live hosted demo.

### Feature 5.1: Package Release & Distribution
- [ ] **CAN-51:** Package `candata-mcp` with `pyproject.toml` and publish to PyPI via `uv`. *(Owner: Benjamin · 2.5h)*
- [ ] **CAN-52:** Submit server to official Anthropic MCP registry and Smithery.ai catalog. *(Owner: Benjamin / Yassir · 1.5h)*
- [ ] **CAN-53:** Deploy hosted demo and docs portal to Vercel / Streamlit Cloud. *(Owner: Benjamin / Yassir · 2h)*

### Feature 5.2: Documentation & Case Study Report
- [ ] **CAN-54:** Build comprehensive bilingual README with architecture diagrams and API reference. *(Owner: Benjamin / Samir · 2h)*
- [ ] **CAN-55:** Publish enterprise case study report comparing manual research vs. agentic synthesis (4 hours vs 12 seconds). *(Owner: Yassir / Samir · 2h)*

---

## 🎯 Milestone 6: Recruiter Blitz & Portfolio Showcase (Sprint 6)
**Dates:** November 18, 2026 – November 25, 2026  
**Goal:** Launch results-first portfolio site, update resumes and LinkedIn profiles, and begin targeted recruiter outreach.

### Feature 6.1: Portfolio Showcase & Career Launch
- [ ] **CAN-61:** Launch modern, results-first portfolio site (`apps/portfolio-site`) showcasing problem, solution, live milestones, and team cards. *(Owner: All · 2.5h)*
- [ ] **CAN-62:** Update all 3 LinkedIn profiles and resumes with exact keyword alignment to Senior AI Engineer / Lead roles. *(Owner: Individual / Benjamin review · 2h)*
- [ ] **CAN-63:** Prepare 1-page technical interview cheat sheets covering DuckDB vs Pandas, LangGraph state, DeepEval metrics. *(Owner: All · 2h)*
- [ ] **CAN-64:** Direct outreach to 30 Canadian AI Engineering VPs and tech hiring managers. *(Owner: All · 2h)*
