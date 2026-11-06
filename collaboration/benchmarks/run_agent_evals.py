"""Run and grade the CAN-41 two-tier agent evaluation (DeepEval) against the GTA ground truth.

The harness lives in ``candata_agent.evals``; this script only puts the repo's packages on the
path (the monorepo doesn't install them) and calls its command line.

    # Ask the benchmark questions (needs ANTHROPIC_API_KEY; live StatCan and Bank of Canada APIs)
    uv run python collaboration/benchmarks/run_agent_evals.py run
    uv run python collaboration/benchmarks/run_agent_evals.py run --only GT-05 GT-12

    # Grade a recorded run offline (no key, no network); --require-tier1 exits 1 on a failure
    uv run python collaboration/benchmarks/run_agent_evals.py grade <runs.jsonl> --require-tier1
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for src in ("packages/candata-mcp/src", "packages/agent-orchestrator/src"):
    if str(REPO / src) not in sys.path:
        sys.path.insert(0, str(REPO / src))

from candata_agent.evals.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
