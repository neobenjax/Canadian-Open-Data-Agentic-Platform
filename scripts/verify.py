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

if isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout.reconfigure(encoding="utf-8")
if isinstance(sys.stderr, io.TextIOWrapper):
    sys.stderr.reconfigure(encoding="utf-8")

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_command(cmd: list[str], cwd: str = ROOT_DIR) -> tuple[int, str, float]:
    """Execute command and return (exit_code, stdout+stderr, duration_seconds)."""
    start_time = time.time()
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
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
