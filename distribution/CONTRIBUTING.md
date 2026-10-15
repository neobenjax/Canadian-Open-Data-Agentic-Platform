# Contributing to CanData-MCP

Welcome to the **Canadian Open Data Agentic Platform (CanData-MCP)** distribution repository!

---

> [!IMPORTANT]
> ### ⚠️ This Repository is a Standalone Distribution Mirror
> **Issues and Pull Requests are disabled on this repository.**  
> All active development, issue tracking, discussions, and pull requests are managed centrally in our primary engineering monorepo:  
> **👉 [Canadian-Open-Data-Agentic-Platform](https://github.com/neobenjax/Canadian-Open-Data-Agentic-Platform)**

---

## 🚀 How to Contribute

We welcome open-source contributions from the AI and data engineering community! To submit bug fixes, new REST adapters, or MCP tool enhancements:

### 1. Fork & Clone the Primary Monorepo
Do not clone this distribution repository for development. Instead, fork and clone the primary monorepo:
```bash
git clone https://github.com/<your-username>/Canadian-Open-Data-Agentic-Platform.git
cd Canadian-Open-Data-Agentic-Platform
```

### 2. Create a Feature Branch
Always work on a clean feature branch created from `main`:
```bash
git checkout -b feat/your-feature-name
```

### 3. Implement Your Changes
- Core FastMCP server tools and adapters live in [`packages/candata-mcp/`](https://github.com/neobenjax/Canadian-Open-Data-Agentic-Platform/tree/main/packages/candata-mcp).
- Multi-agent LangGraph orchestrator components live in [`packages/agent-orchestrator/`](https://github.com/neobenjax/Canadian-Open-Data-Agentic-Platform/tree/main/packages/agent-orchestrator).
- Add or update tests in [`tests/`](https://github.com/neobenjax/Canadian-Open-Data-Agentic-Platform/tree/main/tests).

### 4. Run Pre-Flight Verification
Verify that your changes pass all linters and unit tests:
```bash
# Run test suite
python -m pytest

# Run linter (if uv is installed)
uv run ruff check .
```

### 5. Open a Pull Request
1. Push your branch to your fork on GitHub.
2. Open a Pull Request against `main` on the **primary monorepo**:  
   👉 [https://github.com/neobenjax/Canadian-Open-Data-Agentic-Platform/pulls](https://github.com/neobenjax/Canadian-Open-Data-Agentic-Platform/pulls).
3. The core engineering collective (**Benjamin**, **Samir**, and **Yassir**) will review your contribution.

### 6. Automated Publishing & Attribution
Once your Pull Request is approved and merged into `main` on the monorepo:
- Our automated GitHub Actions workflow will immediately build and publish your changes to this distribution repository.
- **Your git commit authorship, avatar, and GitHub profile will be preserved and attributed directly on this repository!**

Thank you for helping build open-access AI infrastructure for Canadian public data!
