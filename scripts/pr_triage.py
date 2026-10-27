#!/usr/bin/env python3
"""
Canadian Open Data Agentic Platform — PR Triage & Automation Engine
-------------------------------------------------------------------
Deterministic server-side and local triage engine for Pull Requests:
1. Automatically assigns PR author as primary assignee.
2. Automatically assigns designated triangular peer reviewer.
3. Automatically resolves and attaches Sprint Milestone and Tri-Tier labels.
4. Ensures PR body contains Linear dual closing keys (Closes BEN-XX, Closes CAN-XXX)
   via static lookup in scripts/linear_keys.json (0ms offline lookup, 0 tokens).
Configured via `governance.json` for portability across different repositories.
"""

import argparse
import io
import json
import os
import re
import subprocess
import sys

# Ensure repository root is on sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from scripts.governance_config import (  # noqa: E402
    get_area_label,
    get_milestone_index,
    get_milestone_number,
    get_repo_name,
    get_task_prefix,
    get_triangular_matrix,
    get_triangular_reviewer,
)

# Backward-compatible alias
resolve_triangular_reviewer = get_triangular_reviewer

if isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout.reconfigure(encoding="utf-8")
if isinstance(sys.stderr, io.TextIOWrapper):
    sys.stderr.reconfigure(encoding="utf-8")

LINEAR_KEYS_FILE = os.path.join(ROOT_DIR, "scripts", "linear_keys.json")


def load_linear_keys(filepath: str = LINEAR_KEYS_FILE) -> dict[str, str]:
    """Load local static mapping of CAN-XX -> BEN-XX keys."""
    if os.path.exists(filepath):
        try:
            with open(filepath, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def extract_task_key(text: str, prefix: str | None = None) -> str | None:
    """Extract <PREFIX>-XX key from branch or title."""
    if not text:
        return None
    p = prefix or get_task_prefix()
    match = re.search(rf"\b{re.escape(p)}-\d+\b", text, re.IGNORECASE)
    if match:
        return match.group(0).upper()
    return None


def resolve_milestone_and_labels(
    task_key: str | None,
    branch: str,
    title: str,
) -> tuple[int | None, list[str]]:
    """
    Resolve GitHub Milestone number (1-7) and Tri-Tier labels
    (milestone:mX, type:*, area:*) deterministically via governance config.
    """
    labels: list[str] = []
    milestone_num = get_milestone_number(task_key)
    m_idx = get_milestone_index(task_key)

    if m_idx is not None:
        labels.append(f"milestone:m{m_idx}")

    # Determine type label
    b_lower = branch.lower()
    t_lower = title.lower()
    search_context = f"{b_lower} {t_lower}"

    if b_lower.startswith("feat/") or "feat:" in t_lower:
        labels.append("type:feat")
    elif b_lower.startswith("fix/") or "fix:" in t_lower:
        labels.append("type:fix")
    elif b_lower.startswith("docs/") or "docs:" in t_lower:
        labels.append("type:docs")
    elif b_lower.startswith("chore/") or "chore:" in t_lower:
        labels.append("type:chore")
    elif "benchmark" in search_context or "eval" in search_context:
        labels.append("type:eval")
    elif any(k in search_context for k in ["security", "guardrail", "audit"]):
        labels.append("type:security")
    else:
        labels.append("type:feat")

    # Determine area label via centralized governance config
    area = get_area_label(search_context)
    labels.append(area)

    return milestone_num, sorted(list(set(labels)))


def build_dual_closing_lines(task_key: str | None, current_body: str) -> list[str]:
    """Generate missing closing keys (Closes BEN-XX, Closes CAN-XXX)."""
    if not task_key:
        return []

    lines_to_add: list[str] = []
    linear_keys = load_linear_keys()
    ben_key = linear_keys.get(task_key)

    if ben_key and f"closes {ben_key.lower()}" not in current_body.lower():
        lines_to_add.append(f"Closes {ben_key}")

    if f"closes {task_key.lower()}" not in current_body.lower():
        lines_to_add.append(f"Closes {task_key}")

    return lines_to_add


def run_pr_triage(
    pr_number: int,
    branch: str,
    author: str,
    title: str,
    body: str = "",
    repo_name: str | None = None,
    dry_run: bool = False,
    token: str | None = None,
) -> dict[str, object]:
    """Execute triage operations on a pull request."""
    effective_repo = repo_name or get_repo_name()
    task_key = extract_task_key(branch) or extract_task_key(title)
    reviewer = get_triangular_reviewer(author)
    milestone_num, labels = resolve_milestone_and_labels(task_key, branch, title)
    closing_lines = build_dual_closing_lines(task_key, body)

    clean_author = author.lower().lstrip("@")
    valid_authors = set(get_triangular_matrix().keys())
    assignee = clean_author if clean_author in valid_authors else None

    result = {
        "pr_number": pr_number,
        "task_key": task_key,
        "author": author,
        "assignee": assignee,
        "reviewer": reviewer,
        "milestone": milestone_num,
        "labels": labels,
        "closing_lines": closing_lines,
        "repo": effective_repo,
    }

    print("=" * 74)
    print(" 🍁 CANDATA PR TRIAGE ENGINE")
    print("=" * 74)
    print(f"PR Number:       #{pr_number}")
    print(f"Repository:      {effective_repo}")
    print(f"Branch:          {branch}")
    print(f"Author:          @{author}")
    print(f"Detected Task:   {task_key or 'None (Non-task PR)'}")
    print(f"Primary Assignee: @{assignee or 'None'}")
    print(f"Reviewer:        @{reviewer or 'None'}")
    print(f"Milestone:       #{milestone_num or 'None'}")
    print(f"Labels:          {', '.join(labels)}")
    if closing_lines:
        print(f"Closing Keys:    {', '.join(closing_lines)}")
    print("-" * 74)

    if dry_run:
        print("🔍 DRY RUN: No modifications made to GitHub.\n")
        return result

    github_token = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not github_token:
        print("Notice: GITHUB_TOKEN not present. Trying 'gh' CLI...")

    # 1. Update PR metadata via gh CLI
    try:
        edit_args = ["gh", "pr", "edit", str(pr_number), "--repo", effective_repo]
        if assignee:
            edit_args.extend(["--add-assignee", assignee])
        if milestone_num:
            edit_args.extend(["--milestone", str(milestone_num)])
        if labels:
            for lbl in labels:
                edit_args.extend(["--add-label", lbl])
        if closing_lines:
            new_body = (body.strip() + "\n\n" + "\n".join(closing_lines)).strip()
            edit_args.extend(["--body", new_body])

        subprocess.run(edit_args, check=True, capture_output=True)
        print("✨ Updated PR metadata (assignee, milestone, labels, body) via gh CLI.")
    except Exception as e:
        print(f"Notice using gh pr edit: {e}", file=sys.stderr)

    # 2. Request Reviewer via gh api
    if reviewer:
        try:
            rev_cmd = [
                "gh",
                "api",
                f"repos/{effective_repo}/pulls/{pr_number}/requested_reviewers",
                "--method",
                "POST",
                "-f",
                f"reviewers[]={reviewer}",
            ]
            subprocess.run(rev_cmd, check=True, capture_output=True)
            print(f"✅ Requested triangular review from @{reviewer}.")
        except Exception as e:
            print(f"Notice requesting reviewer via gh api: {e}", file=sys.stderr)

    print("=" * 74 + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description="Deterministic PR Triage Engine")
    parser.add_argument("--pr-number", type=int, required=True, help="PR number")
    parser.add_argument("--branch", type=str, required=True, help="Git branch name")
    parser.add_argument("--author", type=str, required=True, help="PR author GitHub username")
    parser.add_argument("--title", type=str, default="", help="PR title")
    parser.add_argument("--body", type=str, default="", help="PR body")
    parser.add_argument(
        "--repo", type=str, default="", help="GitHub repo (defaults to governance.json)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Print actions without modifying PR")

    args = parser.parse_args()
    run_pr_triage(
        pr_number=args.pr_number,
        branch=args.branch,
        author=args.author,
        title=args.title,
        body=args.body,
        repo_name=args.repo or None,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
