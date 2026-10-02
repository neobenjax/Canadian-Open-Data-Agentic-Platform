# Agent Orchestrator (LangGraph 0.2+ Suite)
**Package:** `agent-orchestrator`  
**Description:** Production-grade stateful multi-agent system built on LangGraph 0.2+ orchestrating complex queries across Canadian socioeconomic datasets.

## Multi-Agent Graph Architecture
- **Supervisor & Query Planner:** Decomposes complex user inquiries into deterministic tool-calling directives.
- **Analytical Calculation Node:** Executes exact DuckDB SQL aggregations (preventing LLM mental math errors).
- **Citation & Ground-Truth Verifier:** Matches all numbers against official StatCan/BoC table IDs and reference periods.
- **Human-in-the-Loop (`interrupt()`):** Resolves geographic and statistical boundary ambiguities interactively.
- **Durable State:** Checkpointing via `AsyncSqliteSaver` enabling time-travel debugging and execution resumption.
