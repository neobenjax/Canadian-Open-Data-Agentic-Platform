# CAN-23 (BEN-18): Data Analyst Node (Deterministic DuckDB SQL Math) — Walkthrough & Verification Guide

**Issue Key:** `BEN-18` (`CAN-23`)  
**Branch:** `feat/CAN-23-data-analyst-node`  
**Milestone:** Milestone 2: LangGraph Multi-Agent Orchestration & Observability (Sprint 2)  
**Author:** Benjamin Sanchez Zebadua (`neobenjax`) — Solutions Architect & Lead  
**Peer Reviewer:** Samir Ibrahim (`samiromer2`) — Data Visualization & Agent Evals Lead  

---

## 1. Executive Summary & Architecture Overview

In economic intelligence platforms, **Large Language Models routinely hallucinate arithmetic**:
- Year-over-Year (YoY) percentage changes are miscalculated due to integer rounding or token prediction errors.
- Spreads between the Bank of Canada policy rate and mortgage qualifying rates are confused between percentages (`%`) and basis points (`bps`).
- Multi-series calculations (e.g. shelter rent burden as a percentage of after-tax income) suffer from temporal misalignment and division-by-zero crashes.

**CAN-23** resolves this fundamental failure mode by implementing the **LangGraph Data Analyst Node** with **zero LLM mental math**. Every calculation is executed deterministically by an in-memory sandboxed DuckDB query engine operating over Apache Arrow tables, emitting immutable, auditable `SQLArtifact` objects into the LangGraph `AgentState`.

Furthermore, because LLMs in multi-agent environments can be targeted by indirect prompt injection or adversarial dataset descriptions, CAN-23 establishes a **5-layer Zero-Trust Security Sandbox** that eliminates Arbitrary File Reads (AFR), Server-Side Request Forgery (SSRF), and DDL/DML state mutation.

---

## 2. Key Architectural Deliverables

### A. 5-Layer Zero-Trust Embedded Sandbox (`candata_agent/analyst/sandbox.py`)
1. **C++ Driver-Level Lockdown:**
   Initialized with `duckdb.connect(":memory:", config={"enable_external_access": False, "lock_configuration": True, "max_memory": "256MB", "threads": 1})`. This ensures that even if an attacker crafts an undocumented DuckDB expression, the C++ runtime kernel strictly denies filesystem and network calls.
2. **Lexical & AST Static Guardrail:**
   Enforces single statements (rejects semicolon chaining `;`), strips comment masking (`--`, `/* */`), requires statements to start with `SELECT` or `WITH...SELECT`, and blocks DDL/DML (`DROP`, `INSERT`, `UPDATE`, `ATTACH`, `PRAGMA`, etc.) and dangerous table functions (`read_csv`, `read_parquet`, `read_text`, `read_blob`, `glob`, `scan_location`).
3. **Execution Circuit Breakers:**
   Enforces hard 2.0-second query timeouts, compulsory `LIMIT 1000` row caps, and `< 3KB` serialized output payloads.
4. **Ephemeral In-Memory Memory Lifecycle:**
   Mounts PyArrow tables as temporary views with deterministic cleanup in `finally:` blocks, preventing cross-thread state contamination.

### B. Catalog of 8 Core Deterministic Economic Recipes (`candata_agent/analyst/recipes.py`)
Directly verified against the 15 GTA Housing Ground-Truth benchmark questions (`gta_ground_truth_v1.md`):

| Recipe Function | Economic Metric | Benchmark Questions | Exact Units |
|:---|:---|:---|:---|
| `annual_inflation_rate` | Calendar-year average index YoY growth | `GT-10`, `GT-11` | `%` |
| `yoy_point_to_point` | 12-month lagged index or rent change | `GT-01`, `GT-06`, `GT-12` | `$`, `%` |
| `percentage_point_spread` | Rate differential (vacancy / policy rates) | `GT-02`, `GT-13` | `pp`, `bps` |
| `affordability_burden_ratio`| Annual shelter rent vs median annual income | `GT-07` | `%` |
| `multi_year_cagr` | Compound annual growth rate over $N$ years | `GT-08` | `%` |
| `cross_geography_ranking` | Regional ranking and gap to leader | `GT-03`, `GT-04` | Rank, `pp` |
| `calendar_year_aggregation` | Aggregating monthly flows (housing starts) | `GT-05` | Units count |
| `discrete_regime_change_counter` | Rate change counts, boundaries, min/max | `GT-13` | Count, `%` |

### C. LangGraph 0.2+ Agent Node (`candata_agent/analyst/node.py`)
- Dispatches calculation requests from the supervisor's active `PlanStep` or `scratchpad`.
- Converts incoming Arrow tables, dictionaries, or observation record batches into ephemeral views.
- Dispatches to pre-compiled recipes or validates custom SQL queries through the sandbox.
- Produces typed `SQLArtifact(artifact_id, source_series_id, sql_query, row_count, rows)`.
- Appends an `AgentMessage` with role `ASSISTANT`, displaying a truthful markdown table with explicit units.
- Updates the active `PlanStep` to `COMPLETED` (or `FAILED` with descriptive error diagnostics) and advances the plan.

---

## 3. Summary of Deliverables

| File Path | Description |
|:---|:---|
| [`packages/agent-orchestrator/src/candata_agent/analyst/sandbox.py`](file:///d:/AI/PARTY%20PROJECTS/AI%20Engineer%20-%20Collaboration/packages/agent-orchestrator/src/candata_agent/analyst/sandbox.py) | 5-layer sandboxed DuckDB query runner and query security validator. |
| [`packages/agent-orchestrator/src/candata_agent/analyst/recipes.py`](file:///d:/AI/PARTY%20PROJECTS/AI%20Engineer%20-%20Collaboration/packages/agent-orchestrator/src/candata_agent/analyst/recipes.py) | 8 deterministic Canadian macroeconomic and housing SQL recipes. |
| [`packages/agent-orchestrator/src/candata_agent/analyst/node.py`](file:///d:/AI/PARTY%20PROJECTS/AI%20Engineer%20-%20Collaboration/packages/agent-orchestrator/src/candata_agent/analyst/node.py) | LangGraph 0.2+ `data_analyst_node` state transition handler. |
| [`packages/agent-orchestrator/src/candata_agent/analyst/__init__.py`](file:///d:/AI/PARTY%20PROJECTS/AI%20Engineer%20-%20Collaboration/packages/agent-orchestrator/src/candata_agent/analyst/__init__.py) | Module exports for node, sandbox, exceptions, and recipes. |
| [`packages/agent-orchestrator/src/candata_agent/__init__.py`](file:///d:/AI/PARTY%20PROJECTS/AI%20Engineer%20-%20Collaboration/packages/agent-orchestrator/src/candata_agent/__init__.py) | Exposes `data_analyst_node` and `SandboxedDuckDB` at top level. |
| [`tests/test_analyst_node.py`](file:///d:/AI/PARTY%20PROJECTS/AI%20Engineer%20-%20Collaboration/tests/test_analyst_node.py) | 16 unit and security tests verifying sandbox, recipes, and node integration. |
| [`scripts/demo_data_analyst_node.py`](file:///d:/AI/PARTY%20PROJECTS/AI%20Engineer%20-%20Collaboration/scripts/demo_data_analyst_node.py) | Interactive CLI verification demo illustrating security, math, and state updates. |
| [`TASKS.md`](file:///d:/AI/PARTY%20PROJECTS/AI%20Engineer%20-%20Collaboration/TASKS.md) | Bundled completion checkbox for `CAN-23` under Milestone 2. |

---

## 4. Manual Verification & Testing Guide

To test and verify the implementation locally, execute the following commands in sequence:

### Step 1: Run the Interactive CLI Demo
```bash
python scripts/demo_data_analyst_node.py
```
**Expected Output:**
- **Demo 1:** Confirms that `read_csv`, `; DROP TABLE`, `read_parquet`, and `PRAGMA` injection attempts are blocked by security guardrails.
- **Demo 2:** Computes exact answers matching GTA Ground-Truth baselines:
  - `GT-01`: Rent change $1,972 \to $2,045 ($+\$73$, $+3.70\%$).
  - `GT-02`: Vacancy spread $3.0\% - 1.4\% = +1.6\text{ pp}$ ($+160.0\text{ bps}$).
  - `GT-08`: 5-year CAGR ($5.62\%/\text{year}$, $+31.47\%$ cumulative).
- **Demo 3:** Demonstrates LangGraph state delta updating `sql_artifacts`, formatting a markdown table, and advancing `PlanStep` to `COMPLETED`.

### Step 2: Run the Unit & Security Test Suite
```bash
python -m pytest tests/test_analyst_node.py
```
**Expected Output:**
```
tests/test_analyst_node.py ................ [100%]
16 passed in ~0.86s
```

### Step 3: Run the Full Test Suite Across All Milestones
```bash
python -m pytest
```
**Expected Output:**
```
212 passed, 2 deselected in ~28s
```

### Step 4: Run Static Type Checking & Code Quality
```bash
uv run --offline ruff check .
uv run --offline ruff format --check .
uv run --offline pyright
```
**Expected Output:**
- Ruff check: `All checks passed!`
- Ruff format: `82 files already formatted`
- Pyright: `0 errors, 0 warnings, 0 informations`
