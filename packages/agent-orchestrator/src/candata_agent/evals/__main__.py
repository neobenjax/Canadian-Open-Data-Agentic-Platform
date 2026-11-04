# pyright: reportMissingTypeStubs=false
"""CAN-41 command line: run the benchmark through the agent, then grade the run file.

Call it through ``collaboration/benchmarks/run_agent_evals.py``, which puts the packages on
the path:

    # Ask every question (needs ANTHROPIC_API_KEY; hits live StatCan and Bank of Canada APIs)
    uv run python collaboration/benchmarks/run_agent_evals.py run [--only GT-05 GT-12]

    # Grade a recorded run offline (no key, no network); exit 1 on a Tier 1 failure
    uv run python collaboration/benchmarks/run_agent_evals.py grade <runs.jsonl> --require-tier1
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from candata_agent.evals.ground_truth import DEFAULT_GROUND_TRUTH, REPO_ROOT, load_benchmark

OUT_DIR: Final = REPO_ROOT / "collaboration" / "benchmarks" / "agent_evals"


async def _run(only: list[str] | None, ground_truth: Path, out: Path | None) -> Path:
    from anthropic import AsyncAnthropic

    from candata_agent.checkpoint import AsyncSqliteSaver
    from candata_agent.evals.run import run_benchmark, write_runs
    from candata_agent.supervisor import build_agent_graph
    from candata_agent.supervisor.planner import DEFAULT_MODEL, ClaudePlanner
    from candata_mcp.connectors.boc_valet import ValetClient
    from candata_mcp.connectors.statcan_wds import StatCanClient

    questions = load_benchmark(ground_truth).select(only)
    label = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    with tempfile.TemporaryDirectory() as scratch:
        async with (
            StatCanClient() as statcan,
            ValetClient() as valet,
            AsyncSqliteSaver(Path(scratch) / "eval_threads.db") as saver,
        ):
            planner = ClaudePlanner(AsyncAnthropic(), statcan)
            app = build_agent_graph(
                planner=planner, statcan=statcan, valet=valet, checkpointer=saver
            )
            runs = await run_benchmark(
                app, questions, planner=f"claude:{DEFAULT_MODEL}", run_label=label
            )
    return write_runs(runs, out or OUT_DIR / "runs" / f"agent_{label}.jsonl")


def _grade(runs_file: Path, ground_truth: Path, out_dir: Path, *, require_tier1: bool) -> int:
    from candata_agent.evals.report import grade, render_markdown
    from candata_agent.evals.run import read_runs

    benchmark = load_benchmark(ground_truth)
    runs = read_runs(runs_file)
    report = grade(runs, benchmark)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = runs_file.stem
    (out_dir / f"{stem}_report.json").write_text(
        json.dumps(report.to_json(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    markdown = render_markdown(report, runs)
    (out_dir / f"{stem}_report.md").write_text(markdown, encoding="utf-8")
    print(markdown)
    if require_tier1 and report.tier1_passed < report.graded:
        print(f"Tier 1 failed on {report.graded - report.tier1_passed} question(s).")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="run_agent_evals.py", description=__doc__)
    parser.add_argument("--ground-truth", type=Path, default=DEFAULT_GROUND_TRUTH)
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="ask the benchmark questions and record the answers")
    run.add_argument("--only", nargs="+", metavar="ID", help="question IDs, e.g. GT-05 GT-12")
    run.add_argument("--out", type=Path, help="run file to write (JSONL)")

    grade = commands.add_parser("grade", help="score a recorded run file with DeepEval")
    grade.add_argument("runs", type=Path, help="run file (JSONL) written by `run`")
    grade.add_argument("--out-dir", type=Path, default=OUT_DIR)
    grade.add_argument(
        "--require-tier1", action="store_true", help="exit 1 if any question fails Tier 1"
    )

    args = parser.parse_args(argv)
    if args.command == "run":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            parser.error("`run` needs ANTHROPIC_API_KEY for the Claude planner")
        path = asyncio.run(_run(args.only, args.ground_truth, args.out))
        print(f"Wrote {path}. Grade it with: run_agent_evals.py grade {path}")
        return 0
    return _grade(args.runs, args.ground_truth, args.out_dir, require_tier1=args.require_tier1)


if __name__ == "__main__":
    sys.exit(main())
