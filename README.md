# Canadian Open Data Agentic Platform — Engineering Monorepo

[![MCP Server Distribution](https://img.shields.io/badge/MCP-Distribution%20Repo-orange.svg)](https://github.com/neobenjax/Canadian-Open-Data-Agentic-Platform-MCP-Server)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![FastMCP 2.0](https://img.shields.io/badge/protocol-FastMCP%202.0-yellow.svg)](https://modelcontextprotocol.io/)
[![DuckDB 1.2+](https://img.shields.io/badge/engine-DuckDB%201.2+-yellow.svg)](https://duckdb.org/)
[![LangGraph 0.2+](https://img.shields.io/badge/orchestrator-LangGraph%200.2+-green.svg)](https://langchain-ai.github.io/langgraph/)
[![Architecture Status](https://img.shields.io/badge/status-Active%20Sprint-success.svg)]()

Welcome to the **Canadian Open Data Agentic Platform** primary engineering monorepo and collaborative knowledge hub.

This repository serves as the **Single Source of Truth** for the core engineering team: containing the FastMCP 2.0 server codebase, LangGraph 0.2+ agent orchestrator, GTA housing evaluation benchmarks, team portfolio web applications, interactive 16:9 demo presentations, and agile sprint tracking.

---

> [!TIP]
> ### 🚀 Looking for the Standalone MCP Server?
> If you are an AI developer or external agent looking to install, configure, or use the **CanData-MCP** server in **Claude Desktop**, **Cursor IDE**, or **Google Antigravity**, visit our dedicated zero-bloat distribution repository:  
> **👉 [Canadian-Open-Data-Agentic-Platform-MCP-Server](https://github.com/neobenjax/Canadian-Open-Data-Agentic-Platform-MCP-Server)**

---

## 🧭 Monorepo Architecture & Directory Map

```mermaid
graph TD
    Root["Canadian Open Data Agentic Platform (Monorepo)"]

    subgraph Core ["⚡ Production Packages & Engines"]
        P1["packages/candata-mcp/ (FastMCP 2.0 Server)"]
        P2["packages/agent-orchestrator/ (LangGraph Multi-Agent)"]
        P3["tests/ (Test Suites & CI)"]
    end

    subgraph Hub ["👥 Collaboration & Knowledge Hub"]
        T1["ABOUT_THE_TEAM.md (Collective Profiles)"]
        T2["collaboration/team/ (Detailed Dossiers)"]
        T3["collaboration/meetings/ (Sprint 0 Sync Notes)"]
        T4["collaboration/benchmarks/ (GTA Housing Ground Truth)"]
    end

    subgraph Apps ["🖥️ Interactive Web Apps & Presentations"]
        A1["presentation/ (16:9 Interactive HTML Slides)"]
        A2["apps/portfolio-site/ (Responsive Team Showcase)"]
        A3["apps/docs-portal/ (Documentation Site)"]
    end

    subgraph Governance ["🛡️ Architecture & Agile Sprints"]
        G1["TASKS.md (Linear Sprint Backlog)"]
        G2["AGENTS.md & .cursorrules (Agent Guardrails)"]
        G3["docs/ (Engineering & Automation Guides)"]
    end

    Root --> Core
    Root --> Hub
    Root --> Apps
    Root --> Governance
```

---

## 📚 Section Index

### 1. ⚡ Production Packages
- **[`packages/candata-mcp/`](packages/candata-mcp/):** Official FastMCP 2.0 server connecting LLMs to Statistics Canada, Bank of Canada, and Open Government Canada via server-side DuckDB 1.2+ Arrow vectorized memory buffers.
- **[`packages/agent-orchestrator/`](packages/agent-orchestrator/):** LangGraph 0.2+ stateful multi-agent system with SQL calculation nodes, citation validators, and Human-in-the-Loop (`interrupt()`) boundary checkpoints.
- **[`tests/`](tests/):** Pytest test suites and automated branch protection verification.

### 2. 👥 Team Dynamics & Collaboration
- **[`ABOUT_THE_TEAM.md`](ABOUT_THE_TEAM.md):** The core 3-person collective profile of Benjamin, Samir, and Yassir.
- **[`collaboration/team/benjamin_sanchez_profile.md`](collaboration/team/benjamin_sanchez_profile.md):** Benjamin's solutions architecture dossier.
- **[`collaboration/team-archive/martin_torres_profile.md`](collaboration/team-archive/martin_torres_profile.md):** Future phase contributor archive.
- **[`collaboration/meetings/sprint_0_trial_notes.md`](collaboration/meetings/sprint_0_trial_notes.md):** Weekly sync notes, onboarding trials, and team agreements.
- **[`collaboration/TASKS_3_PERSON_ALIGNMENT.md`](collaboration/TASKS_3_PERSON_ALIGNMENT.md):** Architectural boundaries and sprint responsibilities.

### 3. 📊 Ground-Truth Benchmarks
- **[`collaboration/benchmarks/benchmark_questions_draft.md`](collaboration/benchmarks/benchmark_questions_draft.md):** CMHC rent and StatCan income benchmark questions across 25 Greater Toronto Area municipalities to eliminate LLM hallucinations.
- **[`collaboration/tests/sandbox.md`](collaboration/tests/sandbox.md):** Sandbox trial entries and onboarding test logs.

### 4. 🖥️ Interactive Web Apps & Presentations
- **[`presentation/index.html`](presentation/index.html):** Zero-dependency, fixed 16:9 presentation deck built for weekly demos and stakeholder presentations.
- **[`apps/portfolio-site/index.html`](apps/portfolio-site/index.html):** Modern responsive web showcase displaying core team profiles, experience cards, and live project demos.
- **[`apps/docs-portal/`](apps/docs-portal/):** Dedicated documentation portal structure.

### 5. 🛡️ Architecture & Automation Guides
- **[`docs/DEVELOPER_SETUP_AND_AUTOMATION_GUIDE.md`](docs/DEVELOPER_SETUP_AND_AUTOMATION_GUIDE.md):** Guide to SSH commit signing, git automation, and Linear sync.
- **[`docs/CAN_08_ONBOARDING_AND_ENV_AUTOMATION.md`](docs/CAN_08_ONBOARDING_AND_ENV_AUTOMATION.md):** Zero-dependency `.env` wizard, Linear project hierarchy, and automated PR creation protocol.
- **[`docs/CAN_05_BRANCH_PROTECTION_AND_PEER_REVIEW_VERIFICATION.md`](docs/CAN_05_BRANCH_PROTECTION_AND_PEER_REVIEW_VERIFICATION.md):** Verification of triangular peer review loops (`Benjamin -> Samir -> Yassir -> Benjamin`).
- **[`CANADIAN_AGENTIC_DATA_PLATFORM_PLAN.md`](CANADIAN_AGENTIC_DATA_PLATFORM_PLAN.md):** Full multi-phase architectural roadmap.

---

## 🔄 Automated MCP Server Distribution

This monorepo automatically maintains the public standalone MCP server repository:

1. **Source of Truth:** All development on `candata-mcp` and `agent-orchestrator` takes place directly within this monorepo.
2. **Automated Publishing Workflow:** When changes merge into `main` touching `packages/**`, `tests/**`, or `MCP_README.md`, GitHub Actions (`.github/workflows/publish-mcp-server.yml`):
   - Extracts the original commit author (preserving your GitHub avatar, name, and profile link).
   - Publishes the updated MCP server package and maps `MCP_README.md` $\rightarrow$ `README.md` on the public [Canadian-Open-Data-Agentic-Platform-MCP-Server](https://github.com/neobenjax/Canadian-Open-Data-Agentic-Platform-MCP-Server) repository.
3. **Zero Bloat for End-Users:** Internal sprint logs, demo slides, and web apps stay safely inside this monorepo.

---

## 🤝 The Core Collective

- **[Benjamin Sanchez Zebadua](https://github.com/neobenjax)** — *Project Lead & Solutions Architect*
- **[Samir Ibrahim](https://www.linkedin.com/in/samiroibrahim/)** — *Co-Lead, Data Visualization & Agent Evals Lead*
- **[Yassir Tagelsir Khougali](https://www.linkedin.com/in/yassir-tagelsir-khougali/)** — *Technology Delivery & HITL Transformation Lead*

---

## 📄 License

Licensed under the [Apache 2.0 License](LICENSE).
