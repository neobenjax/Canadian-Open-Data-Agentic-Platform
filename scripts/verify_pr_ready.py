#!/usr/bin/env python3
"""
Canadian Open Data Agentic Platform — Pre-PR & Pre-Push Task Verification
-------------------------------------------------------------------------
Enforces the Bundled Task Completion Checkbox Guardrail:
1. Detects the current git branch or accepts a task key / branch via CLI.
2. If the branch is a feature task branch (e.g. `feat/CAN-08-...` or `feat/CAN-17`),
   verifies that `TASKS.md` has marked the corresponding task as completed (`- [x]`).
3. Non-task branches (`main`, `chore/*`, `docs/*`, `hotfix/*`) pass automatically.
4. Provides `--fix` to auto-check the task in `TASKS.md` and `--install-hook`
   to configure the `.git/hooks/pre-push` hook.
"""

import argparse
import os
import re
import subprocess
import sys

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASKS_FILE = os.path.join(ROOT_DIR, "TASKS.md")
HOOKS_DIR = os.path.join(ROOT_DIR, ".git", "hooks")
PRE_PUSH_HOOK = os.path.join(HOOKS_DIR, "pre-push")

# Non-task branch prefixes and exact branch names that bypass verification
BYPASS_BRANCH_PREFIXES = ("chore/", "docs/", "fix/", "hotfix/", "release/", "ci/", "infra/")
BYPASS_BRANCHES = ("main", "master", "develop", "staging")


def get_current_git_branch() -> str:
    """Retrieve the current active git branch name."""
    try:
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return branch
    except Exception:
        return ""


def extract_task_key(branch_or_identifier: str) -> str | None:
    """
    Extract canonical task key (e.g. 'CAN-08', 'CAN-17') from a branch name or identifier.
    Returns None if no task key is found.
    """
    if not branch_or_identifier:
        return None
    match = re.search(r"\bCAN-\d+\b", branch_or_identifier, re.IGNORECASE)
    if match:
        return match.group(0).upper()
    return None


def should_verify_branch(branch: str) -> bool:
    """Determine whether the specified branch requires task verification."""
    if not branch:
        return False
    branch_lower = branch.lower()
    if branch_lower in BYPASS_BRANCHES:
        return False
    if any(branch_lower.startswith(prefix) for prefix in BYPASS_BRANCHES):
        return False
    # If it starts with a bypass prefix and doesn't explicitly look like a feat task branch
    if any(branch_lower.startswith(p) for p in BYPASS_BRANCH_PREFIXES):
        return False
    # Feature branches with task keys require verification
    if extract_task_key(branch):
        return True
    return False


def is_task_checked_in_tasks_md(
    task_key: str, filepath: str | None = None
) -> tuple[bool, str | None]:
    """
    Check if the specified task is marked as completed (- [x]) in TASKS.md.
    Returns (is_checked, matched_line_text).
    """
    target_file = filepath or TASKS_FILE
    if not os.path.exists(target_file):
        return False, None

    # Matches: - [x] **CAN-XX...:** or - [X] **CAN-XX...:**
    pattern = re.compile(
        rf"^-\s+\[([ xX])\][ \t]+\*\*{re.escape(task_key)}(?:[ \t]*\([^)]+\))?:\*\*",
        re.MULTILINE,
    )

    with open(target_file, encoding="utf-8") as f:
        content = f.read()

    match = pattern.search(content)
    if not match:
        return False, None

    is_checked = match.group(1).lower() == "x"
    # Find full line for diagnostic display
    line = match.group(0)
    return is_checked, line


def mark_task_checked_in_tasks_md(task_key: str, filepath: str | None = None) -> bool:
    """Auto-check the task checkbox in TASKS.md (- [x])."""
    target_file = filepath or TASKS_FILE
    if not os.path.exists(target_file):
        return False

    pattern_str = (
        rf"^-\s+\[([ xX])\]([ \t]+\*\*{re.escape(task_key)}(?:[ \t]*\([^)]+\))?:\*\*)"
        rf"[ \t]*(?:\[(IN PROGRESS|IN REVIEW|DONE|TODO)\][ \t]*)?"
    )
    pattern = re.compile(pattern_str, re.MULTILINE)

    with open(target_file, encoding="utf-8") as f:
        content = f.read()

    if not pattern.search(content):
        return False

    replacement = r"- [x]\2 "
    new_content = pattern.sub(replacement, content)

    with open(target_file, "w", encoding="utf-8") as f:
        f.write(new_content)

    return True


def install_pre_push_hook(target_file: str | None = None) -> bool:
    """Install or update the git pre-push hook to run verify_pr_ready.py before pushing."""
    hook_path = target_file or PRE_PUSH_HOOK
    hook_dir = os.path.dirname(hook_path)
    if not os.path.exists(hook_dir):
        try:
            os.makedirs(hook_dir, exist_ok=True)
        except Exception as e:
            print(f"Error creating hooks directory {hook_dir}: {e}", file=sys.stderr)
            return False

    hook_content = (
        "#!/bin/sh\n"
        "# CanData-MCP Pre-Push Hook: Verify feature branch bundles TASKS.md completion checkbox\n"
        "# Non-task branches (main, chore/*, docs/*) pass automatically.\n"
        "\n"
        "if command -v py >/dev/null 2>&1; then\n"
        '    PY_CMD="py"\n'
        "elif command -v python >/dev/null 2>&1 && python -c '' >/dev/null 2>&1; then\n"
        '    PY_CMD="python"\n'
        "elif command -v python3 >/dev/null 2>&1 && python3 -c '' >/dev/null 2>&1; then\n"
        '    PY_CMD="python3"\n'
        "else\n"
        '    echo "Warning: Working Python not found in PATH for pre-push hook. Skipping check."\n'
        "    exit 0\n"
        "fi\n"
        "\n"
        "$PY_CMD scripts/verify_pr_ready.py\n"
        "EXIT_CODE=$?\n"
        "if [ $EXIT_CODE -ne 0 ]; then\n"
        '    echo ""\n'
        '    echo "❌ Push aborted: Task verification failed."\n'
        '    echo "   Bundle the task checkbox into TASKS.md before pushing or opening a PR."\n'
        '    echo ""\n'
        "    exit 1\n"
        "fi\n"
        "exit 0\n"
    )

    try:
        with open(hook_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(hook_content)

        # Attempt to set executable permissions on Unix-like platforms
        try:
            current_mode = os.stat(hook_path).st_mode
            os.chmod(hook_path, current_mode | 0o755)
        except Exception:
            pass

        print(f"✅ Pre-push hook successfully installed at: {hook_path}")
        return True
    except Exception as e:
        print(f"Error installing pre-push hook: {e}", file=sys.stderr)
        return False


def verify_pr_ready(
    task_key: str | None = None,
    branch: str | None = None,
    auto_fix: bool = False,
    quiet: bool = False,
    filepath: str | None = None,
) -> int:
    """
    Main verification logic.
    Returns 0 if verified / bypassed, 1 if verification fails.
    """
    active_branch = branch or get_current_git_branch()
    resolved_key = task_key or extract_task_key(active_branch)

    # 1. Determine if this branch should be verified
    if not task_key and not should_verify_branch(active_branch):
        if not quiet:
            print(f"ℹ️ Branch '{active_branch}' is not a task feature branch. Pre-PR check skipped.")
        return 0

    if not resolved_key:
        if not quiet:
            print(f"ℹ️ No task key found in branch '{active_branch}'. Pre-PR check skipped.")
        return 0

    # 2. Check if the task is checked in TASKS.md
    is_checked, matched_line = is_task_checked_in_tasks_md(resolved_key, filepath=filepath)

    if is_checked:
        if not quiet:
            print("=" * 74)
            print(" 🍁 CANDATA PRE-PR TASK VERIFICATION PASSED")
            print("=" * 74)
            print(f"Branch:   {active_branch}")
            print(f"Task:     {resolved_key}")
            print("Status:   Completed (- [x]) in TASKS.md")
            print(f"Entry:    {matched_line}")
            print("✅ Bundled task completion checkbox verified. Ready for PR!\n")
        return 0

    # 3. Task is not checked off
    if auto_fix:
        if mark_task_checked_in_tasks_md(resolved_key, filepath=filepath):
            if not quiet:
                print(f"🔧 Auto-checked task {resolved_key} in TASKS.md (- [x]).")
                print("   Remember to stage and commit TASKS.md to this branch before pushing:")
                msg = f"[{resolved_key}] chore: check off completed task in TASKS.md"
                print(f'   git add TASKS.md && git commit -m "{msg}"')
            return 0
        else:
            if not quiet:
                target_file = filepath or TASKS_FILE
                print(
                    f"❌ Failed to auto-fix: Task {resolved_key} not found in {target_file}.",
                    file=sys.stderr,
                )
            return 1

    # 4. Verification failed loud
    if not quiet:
        print("\n" + "=" * 74, file=sys.stderr)
        print(" ❌ PRE-PR VERIFICATION FAILED: UNCHECKED TASK IN TASKS.MD", file=sys.stderr)
        print("=" * 74, file=sys.stderr)
        print(f"Branch:   {active_branch}", file=sys.stderr)
        print(f"Task:     {resolved_key}", file=sys.stderr)
        print("Status:   Uncompleted (- [ ]) in TASKS.md", file=sys.stderr)
        print("-" * 74, file=sys.stderr)
        print("🛡️ Guardrail 25 (Bundled Task Completion Checkbox Guardrail):", file=sys.stderr)
        print(
            "Feature PR branches must bundle their task completion checkbox (- [x])",
            file=sys.stderr,
        )
        print(
            "directly inside TASKS.md within the feature branch before opening a PR.",
            file=sys.stderr,
        )
        print(
            "This guarantees that merging the PR into main automatically marks the task",
            file=sys.stderr,
        )
        print(
            "as completed without requiring isolated 1-line chore PRs or branch unlock.",
            file=sys.stderr,
        )
        print("-" * 74, file=sys.stderr)
        print("👉 Actionable Fixes:", file=sys.stderr)
        print("   Option A (Auto-fix & commit):", file=sys.stderr)
        print(f"      python scripts/verify_pr_ready.py --fix {resolved_key}", file=sys.stderr)
        print("      git add TASKS.md", file=sys.stderr)
        cm1 = f"[{resolved_key}] chore: check off completed task in TASKS.md"
        print(f'      git commit -m "{cm1}"', file=sys.stderr)
        print("   Option B (CLI Transition):", file=sys.stderr)
        print(f"      python scripts/sync_tasks.py --mark-done {resolved_key}", file=sys.stderr)
        print("      git add TASKS.md", file=sys.stderr)
        print(f'      git commit -m "{cm1}"', file=sys.stderr)
        print("=" * 74 + "\n", file=sys.stderr)
    return 1


def main():
    parser = argparse.ArgumentParser(
        description="Verify that a feature PR branch bundles its TASKS.md completion checkbox"
    )
    parser.add_argument(
        "task_key",
        nargs="?",
        type=str,
        help="Task key to verify (e.g. CAN-08, CAN-17). Defaults to parsing active branch.",
    )
    parser.add_argument(
        "--branch",
        type=str,
        help="Branch name to verify instead of active git branch.",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Automatically check off the task in TASKS.md (- [x]) if currently unchecked.",
    )
    parser.add_argument(
        "--install-hook",
        action="store_true",
        help="Install .git/hooks/pre-push to automatically enforce this check on git push.",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress informational output and only exit with return code.",
    )

    args = parser.parse_args()

    if args.install_hook:
        success = install_pre_push_hook()
        sys.exit(0 if success else 1)

    exit_code = verify_pr_ready(
        task_key=args.task_key,
        branch=args.branch,
        auto_fix=args.fix,
        quiet=args.quiet,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
