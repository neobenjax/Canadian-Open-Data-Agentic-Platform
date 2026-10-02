# Project Task Board & Activity Matrix
**Project:** Canadian Open Data Agentic Platform (`CanData-MCP` & LangGraph Multi-Agent Suite)  
**Repository:** [neobenjax/Canadian-Open-Data-Agentic-Platform](https://github.com/neobenjax/Canadian-Open-Data-Agentic-Platform.git)  
**Linear Workspace:** CanData Platform (`CAN`)  
**Timeline:** 6-Week Collaborative Sprint (October 2 – November 13, 2026)  
**Team:** Benjamin (Lead Architect), Samir (Data & Evals), Person 3 (Tech Delivery), Person 4 (AI Security & Risk)

---

## Daily Team Rhythm
- **Weekly Sync:** Every Friday at 11:00 AM EST (Demo what was built, review Tuesday's post, plan next week).
- **Daily 2-Min Async Check-In:** By 10:00 AM EST in WhatsApp/Slack.
- **Support Rule:** *"Never Silently Blocked"* — stuck for >2h or busy with day-job? Flag it early so a teammate can pair-program.

---

## Sprint 0: Kickoff, Setup & Getting Started Tomorrow (Oct 2)
**Goal:** Align the team on the vision, set up local developer environments, configure AI assistants, and pick initial tasks.

- [ ] **T0.1 (Kickoff Meeting):** Run the 10-slide interactive kickoff deck (`presentation/index.html`). *(Owner: Benjamin)*
- [ ] **T0.2 (Local Setup):** Clone repo, install Python 3.12, run `uv sync`, verify tests run locally. *(Owner: All)*
- [ ] **T0.3 (AI Assistant Setup):** Load the project system prompt into Cursor, Claude Code, or Antigravity. *(Owner: All)*
- [ ] **T0.4 (Linear Board Onboarding):** Join the Linear workspace and claim your Sprint 1 task card. *(Owner: Person 3 / All)*
- [ ] **T0.5 (LinkedIn Agreement):** Agree to the Tuesday 8:15 AM post drop & 30-minute team boost routine. *(Owner: All)*

---

## Sprint 1: FastMCP Core, Real Canadian Data & Ground-Truth Benchmarks (Oct 2 – Oct 9)
**Goal:** Working FastMCP 2.0 server with DuckDB querying StatCan and Bank of Canada APIs; first 15 benchmark questions; API security baseline.

- [ ] **T1.1 (GitHub + Linear Branch Linking):** Verify `feat/CAN-XXX` branches auto-update Linear issue statuses. *(Owner: Benjamin / Person 3)*
- [ ] **T1.2 (Monorepo Layout & Tooling):** Verify `uv workspace` layout, Python 3.12, Ruff linter, and pre-commit hooks. *(Owner: Benjamin)*
- [ ] **T1.3 (StatCan WDS Connector):** Implement async HTTP client for StatCan WDS API with response caching. *(Owner: Person 4 / Benjamin)*
- [ ] **T1.4 (Bank of Canada Valet Connector):** Implement async client for Bank of Canada Valet API (policy rate, inflation). *(Owner: Person 3 / Benjamin)*
- [ ] **T1.5 (DuckDB 1.2+ FastMCP Server):** Build FastMCP 2.0 server with in-memory DuckDB slicing 200MB tables down to <3KB. *(Owner: Benjamin)*
- [ ] **T1.6 (Benchmark Dataset V1):** Curate 15 ground-truth questions based on GTA housing, rent vs income, and inflation. *(Owner: Samir)*
- [ ] **T1.7 (Baseline Scorecard):** Benchmark plain Claude 3.5 Sonnet vs existing `mcp-statcan` vs CanData-MCP. *(Owner: Samir / Person 3)*
- [ ] **T1.8 (API Security & Provenance Review):** Verify rate-limit handling, no hardcoded API keys, and data table citation tracking. *(Owner: Person 4)*
- [ ] **T1.9 (LinkedIn Post #1):** Publish Flagship Post #1: *"Why existing LLMs hallucinate on Canadian open data — and our benchmark scorecard proving it"* (Scorecard graphic). *(Lead: Samir | Boosters: All)*

---

## Sprint 2: Multi-Agent Orchestration & LangGraph (Oct 9 – Oct 16)
**Goal:** LangGraph multi-agent system with Supervisor, Query Planner, Data Analyst, and Citation Verifier.

- [ ] **T2.1 (LangGraph State Machine):** Define typed `AgentState` using Pydantic schemas. *(Owner: Samir / Benjamin)*
- [ ] **T2.2 (Supervisor & Query Planner Node):** Build supervisor agent that breaks complex queries into tool calls. *(Owner: Samir)*
- [ ] **T2.3 (Data Analyst & SQL Node):** Implement agent node running exact DuckDB SQL math (no mental math). *(Owner: Benjamin)*
- [ ] **T2.4 (Citation & Verifier Node):** Build deterministic step verifying all numbers match official table IDs. *(Owner: Samir)*
- [ ] **T2.5 (Bilingual French/English Support):** Support bilingual StatCan/BoC metadata schemas. *(Owner: Person 4 / Person 3)*
- [ ] **T2.6 (Observability & Tracing Setup):** Setup OpenTelemetry / LangSmith tracing to measure latency & token costs. *(Owner: Person 3 / Benjamin)*
- [ ] **T2.7 (Screen Demo Capture):** Record 60-second video demo showing agent thought process and tool handoffs. *(Owner: Samir / Person 3)*
- [ ] **T2.8 (LinkedIn Post #2):** Publish Flagship Post #2: *"How we built a 4-agent LangGraph workflow that queries 200MB of StatCan data in 1.4s with zero mental math"*. *(Lead: Benjamin | Boosters: All)*

---

## Sprint 3: Interactive UI & Human-in-the-Loop (Oct 16 – Oct 23)
**Goal:** Next.js 15 documentation portal (`/apps/docs-portal`) with interactive API sandbox, Streamlit analytical app, and LangGraph HITL.

- [ ] **T3.1 (Next.js 15 Docs Portal):** Setup Next.js 15 + Fumadocs + Tailwind v4 documentation site. *(Owner: Benjamin)*
- [ ] **T3.2 (Streamlit Analytical App):** Build modern Streamlit UI with streaming responses and citation sidebars. *(Owner: Samir / Person 3)*
- [ ] **T3.3 (Dynamic Plotly Chart Engine):** Enable agents to generate dynamic Plotly charts from retrieved Canadian data. *(Owner: Samir)*
- [ ] **T3.4 (Human-in-the-Loop Gate):** Add LangGraph `interrupt()` prompt when queries have geographic ambiguity. *(Owner: Samir / Benjamin)*
- [ ] **T3.5 (Open Canada CKAN Connector):** Add connector for federal Open Government CKAN datasets. *(Owner: Person 4)*
- [ ] **T3.6 (User Testing Pilot):** Test UI with 3 external Canadian policy/data analysts; log feedback. *(Owner: Person 3)*
- [ ] **T3.7 (LinkedIn Post #3):** Publish Flagship Post #3: *"Why Human-in-the-loop is non-negotiable for enterprise public data: Building a HITL LangGraph UI"*. *(Lead: Person 3 | Boosters: All)*

---

## Sprint 4: Automated CI/CD Evals & AI Guardrails (Oct 23 – Oct 30)
**Goal:** Automated regression testing in GitHub Actions scoring faithfulness, answer relevancy, and citation precision with DeepEval.

- [ ] **T4.1 (DeepEval Test Harness):** Implement automated evaluation pipeline running against the 30-question suite. *(Owner: Samir)*
- [ ] **T4.2 (GitHub Actions CI Matrix):** Configure CI pipeline to run unit tests and DeepEval scores on every PR. *(Owner: Benjamin / Person 4)*
- [ ] **T4.3 (AI Guardrails & Security Audit):** Implement Pydantic output validators and prompt injection defense. *(Owner: Person 4)*
- [ ] **T4.4 (Token Cost Optimization):** Benchmark prompt caching and JSON compression to reduce query costs by 40%. *(Owner: Person 3 / Benjamin)*
- [ ] **T4.5 (Docker Containerization):** Containerize FastMCP server and LangGraph service; publish images to GHCR. *(Owner: Person 4)*
- [ ] **T4.6 (LinkedIn Post #4):** Publish Flagship Post #4: *"Testing LLM Agents in CI/CD: How we automatically catch hallucinations before merging PRs"*. *(Lead: Person 4 / Samir | Boosters: All)*

---

## Sprint 5: PyPI Release & Public Launch (Oct 30 – Nov 6)
**Goal:** Public PyPI package (`pip install candata-mcp`), official MCP catalog listing, and live hosted demo.

- [ ] **T5.1 (PyPI Package Release):** Package CanData-MCP and publish to PyPI via `uv`. *(Owner: Benjamin)*
- [ ] **T5.2 (MCP Catalog Submission):** Submit server to official Anthropic MCP registry and Smithery.ai. *(Owner: Benjamin / Person 3)*
- [ ] **T5.3 (Cloud Hosting Deployment):** Deploy hosted Streamlit demo and Next.js 15 docs portal to Vercel. *(Owner: Benjamin / Person 3)*
- [ ] **T5.4 (Bilingual README & Docs):** Build polished GitHub README with badges, architecture diagrams, and French guide. *(Owner: Person 4 / Samir)*
- [ ] **T5.5 (Enterprise Case Study Report):** Write 3-page summary comparing manual research vs. agentic synthesis (4 hours vs 12 seconds). *(Owner: Person 3 / Samir)*
- [ ] **T5.6 (LinkedIn Post #5):** Publish Flagship Post #5: *"We just published CanData-MCP to PyPI: Connect any Claude or Cursor agent to official Canadian data in 1 line of code"*. *(Lead: Benjamin | Boosters: All)*

---

## Sprint 6: Recruiter Outreach & Career Launch (Nov 6 – Nov 13)
**Goal:** Direct outreach to 30 Canadian AI engineering hiring managers, resume updates, and team portfolio launch.

- [ ] **T6.1 (Interactive Portfolio Site):** Deploy interactive slide deck showcase highlighting system architecture and team contributions. *(Owner: All)*
- [ ] **T6.2 (Resume & LinkedIn Overhaul):** Update all 4 LinkedIn headlines and About sections with exact keyword alignment for Senior AI Engineer / Lead roles. *(Owner: Individual / Benjamin review)*
- [ ] **T6.3 (Technical Interview Cheat Sheets):** Compile 1-page talking points: DuckDB vs Pandas, LangGraph state, DeepEval metrics, token optimization. *(Owner: All)*
- [ ] **T6.4 (Direct Outreach Campaign):** Reach out directly to 30 Canadian AI Engineering VPs and tech recruiters. *(Owner: All)*
- [ ] **T6.5 (LinkedIn Post #6 - Grand Finale):** Publish Team Retrospective: *"What 6 weeks of building production agentic AI for Canada taught us — and what we're building next"*. *(Lead: All - Co-authored / Cross-tagged)*
