"""Unit tests for CAN-42 CI Pipeline with DeepEval Two-Tier Automated Scoring Gate."""

from pathlib import Path

import yaml

from candata_agent.evals.ground_truth import DEFAULT_GROUND_TRUTH, load_benchmark
from candata_agent.evals.report import grade
from candata_agent.evals.run import read_runs

REPO_ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"
COMMITTED_RUN_PATH = (
    REPO_ROOT
    / "collaboration"
    / "benchmarks"
    / "agent_evals"
    / "runs"
    / "agent_demo_live_20261104.jsonl"
)


def test_ci_workflow_yaml_structure_and_steps():
    """Verify that ci.yml is valid YAML and includes all required verification steps."""
    assert CI_WORKFLOW_PATH.exists(), f"Missing workflow file at {CI_WORKFLOW_PATH}"
    content = CI_WORKFLOW_PATH.read_text(encoding="utf-8")
    parsed = yaml.safe_load(content)

    assert "jobs" in parsed
    assert "verify" in parsed["jobs"]
    steps = parsed["jobs"]["verify"]["steps"]

    step_names = [s.get("name") for s in steps if "name" in s]

    # Verify lint, format, typecheck, pytest
    assert any("Lint" in name for name in step_names), "Missing Lint step in ci.yml"
    assert any("Format" in name for name in step_names), "Missing Format step in ci.yml"
    assert any("Type Check" in name for name in step_names), "Missing Type Check step in ci.yml"
    assert any("Pytest" in name for name in step_names), "Missing Pytest step in ci.yml"

    # Verify DeepEval scoring gate (CAN-42)
    deepeval_step = next((s for s in steps if "DeepEval" in s.get("name", "")), None)
    assert deepeval_step is not None, "Missing DeepEval scoring step in ci.yml"
    assert "--require-tier1" in deepeval_step["run"], (
        "DeepEval CI step must enforce --require-tier1 gate"
    )
    assert "run_agent_evals.py grade" in deepeval_step["run"]

    # Verify Guardrail 25 check
    guardrail_step = next((s for s in steps if "Guardrail 25" in s.get("name", "")), None)
    assert guardrail_step is not None, "Missing Guardrail 25 step in ci.yml"


def test_verify_script_includes_deepeval_step():
    """Verify scripts/verify.py includes DeepEval Two-Tier Scoring."""
    verify_script = REPO_ROOT / "scripts" / "verify.py"
    assert verify_script.exists()
    content = verify_script.read_text(encoding="utf-8")

    assert "DeepEval Two-Tier Scoring (CAN-42)" in content
    assert "--require-tier1" in content
    assert "run_agent_evals.py" in content


def test_committed_live_run_file_passes_tier1_offline():
    """Verify that the committed live run file exists and satisfies Tier 1 and Tier 2."""
    assert COMMITTED_RUN_PATH.exists(), f"Committed run file missing: {COMMITTED_RUN_PATH}"
    runs = read_runs(COMMITTED_RUN_PATH)
    assert len(runs) >= 3, "Expected at least 3 runs in committed run file"

    benchmark = load_benchmark(DEFAULT_GROUND_TRUTH)
    report = grade(runs, benchmark)

    # Must pass Tier 1 completely for CI gate to succeed
    assert report.tier1_passed == report.graded == len(runs)
    assert report.mean("Tier 2 · Metadata enrichment") >= 0.7
    assert report.mean("Tier 2 · Revision freshness") == 1.0
