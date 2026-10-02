# Project Task Board & Activity Matrix (2026 Edition)
**Project:** Canadian Open Data Agentic Platform (`CanData-MCP` & LangGraph Multi-Agent Suite)  
**Repository:** [neobenjax/Canadian-Open-Data-Agentic-Platform](https://github.com/neobenjax/Canadian-Open-Data-Agentic-Platform.git)  
**Linear Workspace:** CanData (`CAN`)  
**Timeline:** Accelerated 6-Week Sprint (October 2, 2026 – November 13, 2026)  
**Team:** 
- **Benjamin** (Team Leader / Solutions Architect — Frontend Infrastructure & AI Systems)
- **Samir** (Co-Lead — Real-World Data Visualization & Agent Evals)
- **Person 3** (Technology Delivery & Transformation Lead — PMP & Applied Business Analytics)
- **Person 4** (AI Security, Risk & Governance Lead — Banking Tech & CompTIA Security+)

---

## Sprint 0: Architecture Setup, Monorepo Layout & Team Kickoff (Oct 2)
**Goal:** Align team on vision with interactive slide deck, establish GitHub + Linear.app integration, and scaffold monorepo.

- [ ] **T0.1 (Kickoff Deck Delivery):** Present interactive 16:9 HTML slide deck (`presentation/kickoff-deck.html`) covering the mission, architecture, team superpowers, and 6-week roadmap. *(Owner: Benjamin)*
- [ ] **T0.2 (Monorepo Layout Scaffolding):** Create directory structure: `/packages` (Public AI tools), `/apps/docs-portal` (Next.js 15), and `/collaboration` (Team logs, benchmarks, Linear sync). *(Owner: Benjamin)*
- [ ] **T0.3 (Linear.app Workspace Setup):** Create Linear project `CanData Platform`, configure 1-week cycles, create issue template with Risk & Eval fields, and link GitHub webhook. *(Owner: Person 3 / Benjamin)*
- [ ] **T0.4 (AI Assistant Persona Initialization):** Ensure all 4 team members configure their coding assistants (Claude Code, Cursor, Antigravity) with the role-aware system prompt. *(Owner: All)*
- [ ] **T0.5 (Linear Issue Ingestion):** Populate Linear Sprint 1 backlog with tasks T1.1 – T1.9. *(Owner: Person 3)*

---

## Sprint 1: FastMCP 2.0 Core, Ground-Truth Benchmarks & Security Baselines (Oct 2 – Oct 9)
**Goal:** Working FastMCP 2.0 server with DuckDB 1.2+ querying StatCan WDS API + BoC Valet API, connected to Claude Desktop; first 15 benchmark questions; API security & risk review.

- [ ] **T1.1 (Git & Linear Integration):** Connect Linear issues to GitHub branches (`feat/CAN-<ID>-...`) with automated PR status transitions. *(Owner: Benjamin / Person 3)*
- [ ] **T1.2 (Monorepo Tooling Configuration):** Configure `uv workspace` layout, Python 3.12, strict `pyright`, Ruff linter/formatter, and pre-commit hooks. *(Owner: Benjamin)*
- [ ] **T1.3 (StatCan WDS Async Connector):** Implement async HTTPX client for Statistics Canada WDS API (metadata discovery, vector lookup, SDMX cube slice with HTTP ETag caching). *(Owner: Person 4 / Benjamin)*
- [ ] **T1.4 (Bank of Canada Valet Connector):** Implement client for Bank of Canada Valet API (policy rate, inflation target, CPI series). *(Owner: Person 3 / Benjamin)*
- [ ] **T1.5 (DuckDB 1.2+ FastMCP Server):** Build FastMCP 2.0 server with tool annotations (`readOnly=True`, `idempotent=True`) exposing tools (`search_canadian_data`, `query_series`, `compare_regional_metrics`) using in-memory DuckDB Arrow streams to reduce 200MB payloads to <3KB. *(Owner: Benjamin)*
- [ ] **T1.6 (Benchmark Dataset V1):** Curate 15 ground-truth questions based on GTA housing, rent vs income, and inflation metrics with verified reference answers. *(Owner: Samir)*
- [ ] **T1.7 (Baseline Scorecard):** Benchmark vanilla frontier LLMs vs existing `mcp-statcan` vs CanData-MCP; log hallucinations, latency, token costs, and citation coverage. *(Owner: Samir / Person 3)*
- [ ] **T1.8 (API Security & Data Privacy Review):** Conduct security risk assessment of public API access, rate limits, caching integrity, and data provenance. *(Owner: Person 4)*
- [ ] **T1.9 (LinkedIn Milestone 1):** Publish Flagship Post #1: *"Why existing LLMs hallucinate on Canadian open data — and our benchmark scorecard proving it"* with comparative chart. *(Lead: Samir | Boosters: All)*

---

## Sprint 2: Multi-Agent Orchestration, LangGraph 0.2+ & Observability (Oct 9 – Oct 16)
**Goal:** LangGraph 0.2+ multi-agent system with durable state checkpointers (`AsyncSqliteSaver`), Supervisor, Query Planner, Data Analyst, and Verifier.

- [ ] **T2.1 (LangGraph Typed State Graph):** Define typed `AgentState` using Pydantic v2 models (user intent, sub-queries, retrieved tables, mathematical summaries, verification flags). *(Owner: Samir / Benjamin)*
- [ ] **T2.2 (Supervisor & Query Planner Node):** Build LangGraph supervisor agent that breaks complex queries (*"How has the rent-to-income ratio in Brampton changed relative to the Bank of Canada policy rate since 2021?"*) into distinct tool calls. *(Owner: Samir)*
- [ ] **T2.3 (Data Analyst & Calculation Node):** Implement agent tool node executing exact DuckDB aggregations rather than relying on LLM mental math. *(Owner: Benjamin)*
- [ ] **T2.4 (Citation & Ground-Truth Verifier Node):** Build deterministic verification step that validates every statistic against retrieved StatCan/BoC table IDs before final answer generation. *(Owner: Samir)*
- [ ] **T2.5 (Bilingual Schema Support & Data Governance):** Ensure tool metadata and prompt instructions support French and English data cubes; establish data lineage tracking. *(Owner: Person 4 / Person 3)*
- [ ] **T2.6 (OpenTelemetry Observability Setup):** Instrument OpenTelemetry-native Arize Phoenix and LangSmith v2 tracing across all LangGraph nodes (trace latency, tokens, tool call parameters). *(Owner: Person 3 / Benjamin)*
- [ ] **T2.7 (Screen Demo Capture):** Record 60-second video walkthrough showing sub-agent handoffs and LangGraph Studio execution graph. *(Owner: Samir / Person 3)*
- [ ] **T2.8 (LinkedIn Milestone 2):** Publish Flagship Post #2: *"How we built a 4-agent LangGraph workflow that queries 200MB of StatCan data in 1.4 seconds with zero mental math"* (Video + Architecture). *(Lead: Benjamin | Boosters: All)*

---

## Sprint 3: Modern Documentation Portal, Interactive UI & Human-in-the-Loop (Oct 16 – Oct 23)
**Goal:** Next.js 15 documentation portal (`/apps/docs-portal`) with interactive API sandbox, Streamlit analytical interface, and LangGraph `interrupt()` HITL.

- [ ] **T3.1 (Next.js 15 Docs Portal Scaffold):** Initialize Next.js 15 App Router + Fumadocs / Tailwind CSS v4 in `/apps/docs-portal` with dark-mode documentation and MCP quickstart. *(Owner: Benjamin)*
- [ ] **T3.2 (Streamlit Analytical App):** Build modern Streamlit UI with `astream_events` v2 real-time streaming, agent status badges, and source citation sidebars. *(Owner: Samir / Person 3)*
- [ ] **T3.3 (Dynamic Plotly Chart Engine):** Implement automated data-to-chart tool so agents generate interactive Canadian trend charts. *(Owner: Samir)*
- [ ] **T3.4 (Human-in-the-Loop Gate):** Add LangGraph `interrupt()` breakpoint when data ambiguities exist (e.g. choosing between Census Metropolitan Area vs. Municipal boundary). *(Owner: Samir / Benjamin)*
- [ ] **T3.5 (Open Canada CKAN Connector):** Add connector for federal Open Government CKAN portal (accessing additional municipal and federal datasets). *(Owner: Person 4)*
- [ ] **T3.6 (User Testing & Operational Pilot):** Run 3 external Canadian data analysts or policy researchers through the UI; log friction points and process improvements. *(Owner: Person 3)*
- [ ] **T3.7 (LinkedIn Milestone 3):** Publish Flagship Post #3: *"Why Human-in-the-loop is non-negotiable for enterprise public data: Building a HITL LangGraph UI"* (Carousel breakdown + UI Demo). *(Lead: Person 3 | Boosters: All)*

---

## Sprint 4: Automated CI/CD Evals, AI Security Guardrails & Docker (Oct 23 – Oct 30)
**Goal:** Automated regression evaluation suite in GitHub Actions scoring faithfulness, answer relevancy, and citation precision with DeepEval and NIST/Inspect AI standards.

- [ ] **T4.1 (DeepEval Test Harness):** Implement automated evaluation pipeline running against the full 30-question ground-truth suite. *(Owner: Samir)*
- [ ] **T4.2 (GitHub Actions CI Matrix):** Configure CI pipeline to run unit tests, MCP integration tests, and eval scoring on every Pull Request. *(Owner: Benjamin / Person 4)*
- [ ] **T4.3 (AI Security & Guardrails Audit):** Implement Pydantic v2 output validators and prompt injection defense; conduct vulnerability assessment on LLM tool execution. *(Owner: Person 4)*
- [ ] **T4.4 (Token Economics & Cost Optimization):** Benchmark prompt token caching and compressed JSON-LD serialization to slash query costs by 40%. *(Owner: Person 3 / Benjamin)*
- [ ] **T4.5 (Docker Containerization):** Containerize FastMCP server and LangGraph service; publish container images to GitHub Container Registry (GHCR). *(Owner: Person 4)*
- [ ] **T4.6 (LinkedIn Milestone 4):** Publish Flagship Post #4: *"Testing LLM Agents in CI/CD: How we automatically catch hallucinations before merging PRs"* (Code snippets + GitHub Actions report). *(Lead: Person 4 / Samir | Boosters: All)*

---

## Sprint 5: PyPI Release, Cloud Deployment & Public Launch (Oct 30 – Nov 6)
**Goal:** Public PyPI package (`pip install candata-mcp`), official MCP registry submission, live hosted Streamlit Cloud demo, and bilingual docs.

- [ ] **T5.1 (PyPI Package Publication):** Package CanData-MCP with `pyproject.toml`, publish to PyPI with automated GitHub release workflows. *(Owner: Benjamin)*
- [ ] **T5.2 (MCP Registry & Smithery Submission):** Submit server to official Anthropic MCP server list and Smithery.ai catalog. *(Owner: Benjamin / Person 3)*
- [ ] **T5.3 (Cloud Demo & Docs Deployment):** Deploy hosted Streamlit demo and Next.js 15 docs portal to Vercel / Streamlit Cloud. *(Owner: Benjamin / Person 3)*
- [ ] **T5.4 (Bilingual Technical Docs & README):** Build top-tier GitHub README with badges, architecture flowcharts, quickstart guide, and bilingual French summary. *(Owner: Person 4 / Samir)*
- [ ] **T5.5 (Enterprise Transformation Case Study):** Write 3-page markdown report comparing manual economic policy research vs. agentic synthesis (time-to-insight: 4 hours vs 12 seconds). *(Owner: Person 3 / Samir)*
- [ ] **T5.6 (LinkedIn Milestone 5):** Publish Flagship Post #5: *"We just published CanData-MCP to PyPI: Connect any Claude or Cursor agent to official Canadian data in 1 line of code"* (Release announcement + GIF). *(Lead: Benjamin | Boosters: All)*

---

## Sprint 6: Recruiter Blitz, Interview Artifacts & Career Launch (Nov 6 – Nov 13)
**Goal:** Career transition blitz, comprehensive portfolio website/case studies, personalized outreach to Canadian tech hiring managers.

- [ ] **T6.1 (Interactive Portfolio Case Study):** Finalize interactive web presentation (`frontend-slides`) showing system architecture, performance metrics, and team contributions. *(Owner: All)*
- [ ] **T6.2 (Resume & LinkedIn Transformation):** Update all 4 LinkedIn headlines, About sections, and featured project sections with exact keyword alignment to Senior AI Engineer / Agentic Developer roles. *(Owner: Individual / Benjamin review)*
- [ ] **T6.3 (Technical Interview Cheat Sheets):** Compile 1-page talking points for each member: architectural tradeoffs, DuckDB vs Pandas, LangGraph state management, eval metrics, and scaling bottlenecks. *(Owner: Benjamin / Samir / Person 4 / Person 3)*
- [ ] **T6.4 (Direct Outreach Campaign):** Target 30 Canadian AI Engineering leads, VP of Engineering, and Tech Recruiters at companies hiring for AI/Agentic roles (e.g. banks, consultancies, scale-ups). *(Owner: All)*
- [ ] **T6.5 (LinkedIn Milestone 6 - Grand Finale):** Publish Team Syndicate Post: *"What 6 weeks of building production agentic AI for Canada taught us: Open-sourcing CanData-MCP + what's next"* (Team photo/avatar collage + impact stats). *(Lead: All - Co-authored / Cross-tagged)*

---

## Daily Async Check-In Template (Post by 10:00 AM EST)
```markdown
**[Name] Daily Sync — [Date]**
✅ **Done Yesterday:** [Linear Issue CAN-XXX / PR #]
➡️ **Today's Focus:** [Linear Issue CAN-YYY]
🚧 **Blockers:** [API issue, architecture question, none]
🤖 **AI Assistant Used:** [Prompt role & learning takeaway]
```
