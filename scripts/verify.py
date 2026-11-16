#!/usr/bin/env python3
"""
Canadian Open Data Agentic Platform — Unified Fast Pre-Flight Verifier
----------------------------------------------------------------------
Replaces 4 repetitive CLI invocations (ruff check, ruff format, pyright, pytest)
with a single high-speed Python command that outputs a concise, low-token summary.
Saves ~1,850 tokens of terminal output context per verification turn.
"""

import argparse
import io
import os
import subprocess
import sys
import time
import tomllib

if isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout.reconfigure(encoding="utf-8")
if isinstance(sys.stderr, io.TextIOWrapper):
    sys.stderr.reconfigure(encoding="utf-8")

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def verify_packaging_parity() -> tuple[bool, str]:
    """Verify distribution/pyproject.toml matches candata-mcp pyproject.toml (Issue #82)."""
    pkg_toml_path = os.path.join(ROOT_DIR, "packages", "candata-mcp", "pyproject.toml")
    dist_toml_path = os.path.join(ROOT_DIR, "distribution", "pyproject.toml")

    if not os.path.exists(pkg_toml_path):
        return False, f"Missing file: {pkg_toml_path}"
    if not os.path.exists(dist_toml_path):
        return False, f"Missing file: {dist_toml_path}"

    try:
        with open(pkg_toml_path, "rb") as f:
            pkg_data = tomllib.load(f)
        with open(dist_toml_path, "rb") as f:
            dist_data = tomllib.load(f)
    except Exception as e:
        return False, f"Failed parsing pyproject.toml: {e}"

    pkg_proj = pkg_data.get("project", {})
    dist_proj = dist_data.get("project", {})

    diffs: list[str] = []
    for field in ("name", "version", "dependencies"):
        pkg_val = pkg_proj.get(field)
        dist_val = dist_proj.get(field)
        if pkg_val != dist_val:
            diffs.append(
                f"Field '{field}' mismatch between packages/candata-mcp and distribution:\n"
                f"  - packages/candata-mcp: {pkg_val}\n"
                f"  - distribution:         {dist_val}"
            )

    if diffs:
        return False, "\n".join(diffs)
    return True, ""


def run_command(cmd: list[str], cwd: str = ROOT_DIR) -> tuple[int, str, float]:
    """Execute command and return (exit_code, stdout+stderr, duration_seconds)."""
    start_time = time.time()
    env = os.environ.copy()
    for key in ("no_proxy", "NO_PROXY"):
        if key in env:
            env[key] = env[key].replace(",[::1]", "").replace("[::1]", "")
    try:
        env = os.environ.copy()
        if "NO_PROXY" in env:
            env["NO_PROXY"] = env["NO_PROXY"].replace(",[::1]", "").replace("[::1]", "")
        if "no_proxy" in env:
            env["no_proxy"] = env["no_proxy"].replace(",[::1]", "").replace("[::1]", "")
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        duration = time.time() - start_time
        return proc.returncode, proc.stdout, duration
    except Exception as e:
        duration = time.time() - start_time
        return 1, str(e), duration


def verify_all(auto_fix: bool = False, fast: bool = False, quiet: bool = False) -> int:
    """Run verification checks and print concise status report."""
    results: list[dict[str, object]] = []
    has_failure = False

    if auto_fix:
        if not quiet:
            print("🔧 Auto-fixing lint and formatting...")
        run_command(["uv", "run", "ruff", "check", "--fix", "."])
        run_command(["uv", "run", "ruff", "format", "."])

    # 0. Packaging Parity Check (Issue #82)
    parity_start = time.time()
    parity_passed, parity_diff = verify_packaging_parity()
    parity_duration = time.time() - parity_start
    results.append(
        {
            "name": "Packaging Parity (candata-mcp <-> distribution)",
            "passed": parity_passed,
            "duration": parity_duration,
            "output": parity_diff if not parity_passed else "",
        }
    )
    if not parity_passed:
        has_failure = True

    # 1. Ruff Lint
    code, output, duration = run_command(["uv", "run", "ruff", "check", "."])
    results.append(
        {
            "name": "Ruff Linter",
            "passed": code == 0,
            "duration": duration,
            "output": output if code != 0 else "",
        }
    )
    if code != 0:
        has_failure = True

    # 2. Ruff Format Check
    code, output, duration = run_command(["uv", "run", "ruff", "format", "--check", "."])
    results.append(
        {
            "name": "Ruff Formatter",
            "passed": code == 0,
            "duration": duration,
            "output": output if code != 0 else "",
        }
    )
    if code != 0:
        has_failure = True

    # 3. Pyright Type Checking
    code, output, duration = run_command(["uv", "run", "pyright"])
    results.append(
        {
            "name": "Pyright Type Checker",
            "passed": code == 0,
            "duration": duration,
            "output": output if code != 0 else "",
        }
    )
    if code != 0:
        has_failure = True

    # 4. Pytest Suite (unless --fast)
    if not fast:
        code, output, duration = run_command(["uv", "run", "pytest", "-q", "-m", "not live"])
        # Extract summary line from pytest output
        last_line = output.strip().splitlines()[-1] if output.strip() else ""
        summary = f" ({last_line})" if last_line and code == 0 else ""
        results.append(
            {
                "name": f"Pytest Suite{summary}",
                "passed": code == 0,
                "duration": duration,
                "output": output if code != 0 else "",
            }
        )
        if code != 0:
            has_failure = True

    # 5. DeepEval Two-Tier Scoring (CAN-42, unless --fast)
    if not fast:
        eval_run_file = os.path.join(
            ROOT_DIR,
            "collaboration",
            "benchmarks",
            "agent_evals",
            "runs",
            "agent_demo_live_20261104.jsonl",
        )
        if os.path.exists(eval_run_file):
            code, output, duration = run_command(
                [
                    "uv",
                    "run",
                    "python",
                    "collaboration/benchmarks/run_agent_evals.py",
                    "grade",
                    eval_run_file,
                    "--require-tier1",
                ]
            )
            results.append(
                {
                    "name": "DeepEval Two-Tier Scoring (CAN-42)",
                    "passed": code == 0,
                    "duration": duration,
                    "output": output if code != 0 else "",
                }
            )
            if code != 0:
                has_failure = True

    if quiet:
        return 1 if has_failure else 0

    print("=" * 74)
    if has_failure:
        print(" ❌ CANDATA PRE-FLIGHT VERIFICATION FAILED")
    else:
        print(" 🍁 CANDATA PRE-FLIGHT VERIFICATION: ALL CHECKS PASSED")
    print("=" * 74)

    for r in results:
        icon = "✅" if r["passed"] else "❌"
        dur = f"[{float(r['duration']):.1f}s]"  # type: ignore[arg-type]
        print(f" {icon} {dur:<7} {r['name']}")

    if has_failure:
        print("-" * 74)
        print("🔍 Diagnostic Details:")
        for r in results:
            out_str = str(r["output"]).strip()
            if not r["passed"] and out_str:
                print(f"\n--- {r['name']} Failure Output ---")
                print(out_str)
        print("=" * 74 + "\n")
        return 1

    print("-" * 74)
    print("✨ Codebase clean and ready for commit & PR!\n")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Unified fast pre-flight verification (ruff, pyright, pytest)"
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Automatically apply ruff fixes and formatting before checking",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Run only static analysis (lint, format, pyright); skip pytest",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress informational output; return exit code 0 or 1",
    )

    args = parser.parse_args()
    exit_code = verify_all(auto_fix=args.fix, fast=args.fast, quiet=args.quiet)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
