"""CAN-41: DeepEval harness scoring agent runs against the GTA ground truth in two tiers.

- Tier 1 (strict pass/fail): the Core Verification Tuples cited.
- Tier 2 (scored): metadata enrichment, and revision freshness.

The scoring is deterministic: no LLM judge, so grading needs no API key or network.
"""

from candata_agent.evals.ground_truth import Benchmark, GroundTruthQuestion, load_benchmark
from candata_agent.evals.run import AgentRun, read_runs, run_benchmark, run_question, write_runs
from candata_agent.evals.scoring import Score, covers, period_interval, score_core

__all__ = [
    "AgentRun",
    "Benchmark",
    "GroundTruthQuestion",
    "Score",
    "covers",
    "load_benchmark",
    "period_interval",
    "read_runs",
    "run_benchmark",
    "run_question",
    "score_core",
    "write_runs",
]
