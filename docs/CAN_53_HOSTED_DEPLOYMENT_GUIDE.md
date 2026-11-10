# CAN-53: Hosted Demo and Documentation Portal Deployment Guide

**Task:** CAN-53 (Sprint 5, Milestone 5)  
**Owners:** Benjamin Sanchez Zebadua (Lead) / Yassir Tagelsir Khougali  
**Target URLs:**
- **Documentation & Playground Portal:** [candata-mcp.vercel.app](https://candata-mcp.vercel.app) (Alias: [candata-docs.vercel.app](https://candata-docs.vercel.app))
- **Interactive Presentation Deck:** [canadian-open-data-agentic-platform.vercel.app](https://canadian-open-data-agentic-platform.vercel.app)
- **Portfolio Showcase Site:** [canadian-open-data-agentic-platform-kappa.vercel.app](https://canadian-open-data-agentic-platform-kappa.vercel.app)
- **Streamlit Interactive Multi-Agent Demo:** [candata-agent.streamlit.app](https://candata-agent.streamlit.app)

---

## 1. Architecture Overview

```
                                  [ Public Internet ]
                                           │
                    ┌──────────────────────┴──────────────────────┐
                    ▼                                             ▼
          [ candata.vercel.app ]                      [ candata-agent.streamlit.app ]
        Vercel Global Edge Network                     Streamlit Community Cloud
                    │                                             │
      ┌─────────────┴─────────────┐                 ┌─────────────┴─────────────┐
      ▼                           ▼                 ▼                           ▼
Next.js 16.4.6 App Router Interactive API     Streamlit 1.40 UI       LangGraph 0.2+ Agent
Fumadocs MDX Portal       Sandbox Playground  Plotly Dynamic Charts   Supervisor / Analyst
```

The platform provides two zero-install, live cloud endpoints:

1. **`apps/docs-portal` (Vercel):** Modern, high-grade Next.js 16.4.6 + Fumadocs developer documentation portal styled after `fumadocs.dev` with Canadian Maple Red (`#D80621`), warm off-white paper (`#FDFCFB`), and dark tone (`#0B0F19`) design system tokens, floating sidebar navigation, search modal (`Ctrl+K`), right-hand Table of Contents, animated landing page with quickstart snippet, and client-side sandbox query testing.
2. **`apps/agent-ui` (Streamlit Community Cloud):** Interactive multi-agent analytics app streaming live events via `astream_events` v2, generating dynamic Plotly charts, and displaying verifiable two-tier citation envelopes from Statistics Canada and the Bank of Canada.

---

## 2. Vercel Deployment Configuration

### Monorepo Setup on Vercel Dashboard

When connecting the GitHub repository (`neobenjax/Canadian-Open-Data-Agentic-Platform`) to Vercel:

| Setting | Recommended Value | Notes |
|---|---|---|
| **Framework Preset** | `Next.js` | Automatically detected |
| **Root Directory** | `apps/docs-portal` | Critical for monorepo isolation |
| **Build Command** | `next build` | Enforced by `vercel.json` |
| **Output Directory** | `.next` | Standard Next.js production build |
| **Install Command** | `npm ci` | Strict lockfile reproducibility |
| **Node.js Version** | `22.x` | Matches production runtime |

### Dual Monorepo Configuration (`vercel.json`)

To prevent deployment failures if a developer leaves the root directory default or selects `apps/docs-portal`, the repository provides two configuration contracts:

1. **`apps/docs-portal/vercel.json`:** Direct project configuration with security headers (`X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`).
2. **`vercel.json` (Root):** Monorepo fallback routing builds directly to `apps/docs-portal` via `cd apps/docs-portal && npm run build`.

---

## 3. Streamlit Community Cloud Deployment Configuration

### Setup on Streamlit Community Cloud Dashboard

1. Navigate to [share.streamlit.io](https://share.streamlit.io).
2. Click **New app** and select:
   - **Repository:** `neobenjax/Canadian-Open-Data-Agentic-Platform`
   - **Branch:** `main`
   - **Main file path:** `apps/agent-ui/app.py`
   - **App URL:** `candata-agent` (`candata-agent.streamlit.app`)
3. Click **Advanced settings** -> **Secrets** and configure optional production environment variables:
   ```toml
   # Optional: System Anthropic key for default live mode
   ANTHROPIC_API_KEY = "sk-ant-..."

   # Optional: OpenTelemetry & LangSmith tracing
   LANGSMITH_API_KEY = "lsv2_..."
   LANGSMITH_PROJECT = "candata-platform"
   ```

### Cloud Runtime Hardening Profile

- **Branding & Theme (`.streamlit/config.toml`):** Configures primary color `#D80621` (Canadian Maple Red), background `#0B0F19`, secondary background `#151D2F`, headless operation, and telemetry opt-out.
- **Dependency Resolution (`requirements-cloud.txt`):** Pins all runtime packages and installs local packages editable (`-e ./packages/candata-mcp`, `-e ./packages/agent-orchestrator`).
- **Ephemeral SQLite Checkpointing:** `open_agent()` auto-provisions non-existent checkpoint directories (`db_path.parent.mkdir(parents=True, exist_ok=True)`), preventing startup crashes on fresh ephemeral serverless instances.
- **Anonymous Public Visitors (Safe Demo Mode):** Without `ANTHROPIC_API_KEY`, the app executes 3 pre-planned benchmark questions against live Statistics Canada and Bank of Canada endpoints with zero errors.
- **In-Session User Key Input:** Visitors can optionally enter their own Anthropic API key in the sidebar for custom live queries. The key is stored only in ephemeral `st.session_state` and never persisted.

---

## 4. CI / Integration Pipeline Verification

Every Pull Request automatically executes:

1. **Next.js Production Build Simulation:** Installs dependencies and runs `npm run build` in `apps/docs-portal` on Node.js 22 LTS.
2. **Streamlit Headless Smoke Check:** Verifies Streamlit CLI and configuration loading.
3. **Automated Deployment Contract Tests (`tests/test_hosted_deployment.py`):**
   - Validates `vercel.json` schemas and security headers.
   - Validates `.streamlit/config.toml` theme colors and telemetry opt-out.
   - Validates `requirements-cloud.txt` completeness.
   - Asserts checkpoint directory auto-provisioning.
