#!/usr/bin/env python3
"""
Canadian Open Data Agentic Platform — Branch Protection & Triangular Review Verifier
-------------------------------------------------------------------------------------
Zero-dependency Python CLI that:
1. Verifies GitHub branch protection settings on `main` (enforce_admins, 1+ approval required).
2. Verifies Triangular Peer Review protocol compliance on active Pull Requests:
   - Benjamin Sanchez (@neobenjax) -> Samir Omer (@samiromer2)
   - Samir Omer (@samiromer2)       -> Yassir Khougali (@yassirtmk)
   - Yassir Khougali (@yassirtmk)   -> Benjamin Sanchez (@neobenjax)
3. Reports compliance status and provides structured JSON or terminal output.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_FILE = os.path.join(ROOT_DIR, ".env")
DEFAULT_REPO = "neobenjax/Canadian-Open-Data-Agentic-Platform"

TRIANGULAR_REVIEW_MAP = {
    "neobenjax": "samiromer2",
    "samiromer2": "yassirtmk",
    "yassirtmk": "neobenjax",
}

TEAM_MEMBER_NAMES = {
    "neobenjax": "Benjamin Sanchez Zebadua (Solutions Architect & Lead)",
    "samiromer2": "Samir Omer (Data Visualization & Agent Evals Lead)",
    "yassirtmk": "Yassir Khougali (Technology Delivery & Transformation Lead)",
}


def load_dotenv(filepath: str = ENV_FILE) -> dict[str, str]:
    """Parse local .env file into os.environ without external dependencies."""
    loaded = {}
    if not os.path.exists(filepath):
        return loaded
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("'\"")
                    if key:
                        loaded[key] = val
                        if key not in os.environ:
                            os.environ[key] = val
    except OSError as e:
        print(f"Warning: Could not parse .env file: {e}", file=sys.stderr)
    return loaded


def github_api_get(endpoint: str, token: str | None = None) -> tuple[int, Any]:
    """Make authenticated GET request to GitHub REST API."""
    url = f"https://api.github.com/{endpoint.lstrip('/')}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "CanData-BranchProtectionVerifier",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req) as response:
            status = response.getcode()
            body = response.read().decode("utf-8")
            return status, json.loads(body)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"message": body}
        return e.code, parsed
    except (urllib.error.URLError, OSError) as e:
        return 500, {"message": str(e)}


def check_branch_protection(repo: str, branch: str = "main", token: str | None = None) -> dict[str, Any]:
    """Verify branch protection settings for target branch."""
    status, data = github_api_get(f"repos/{repo}/branches/{branch}/protection", token=token)
    
    result = {
        "repo": repo,
        "branch": branch,
        "http_status": status,
        "protected": status == 200,
        "checks": {},
        "errors": [],
        "passed": False,
    }

    if status != 200:
        result["errors"].append(data.get("message", f"HTTP {status} fetching branch protection"))
        return result

    # 1. Required approvals
    req_reviews = data.get("required_pull_request_reviews", {})
    approvals = req_reviews.get("required_approving_review_count", 0) if req_reviews else 0
    result["checks"]["min_1_approval"] = {
        "required": 1,
        "actual": approvals,
        "passed": approvals >= 1,
    }

    # 2. Enforce admins
    enforce_admins = data.get("enforce_admins", {}).get("enabled", False)
    result["checks"]["enforce_admins"] = {
        "required": True,
        "actual": enforce_admins,
        "passed": enforce_admins is True,
    }

    # 3. Prevent force pushes
    allow_force = data.get("allow_force_pushes", {}).get("enabled", False)
    result["checks"]["block_force_push"] = {
        "required": True,
        "actual": not allow_force,
        "passed": not allow_force,
    }

    # 4. Prevent branch deletion
    allow_delete = data.get("allow_deletions", {}).get("enabled", False)
    result["checks"]["block_deletion"] = {
        "required": True,
        "actual": not allow_delete,
        "passed": not allow_delete,
    }

    result["passed"] = all(c["passed"] for c in result["checks"].values())
    return result


def check_triangular_prs(repo: str, token: str | None = None) -> dict[str, Any]:
    """Inspect all open Pull Requests and check triangular review assignment."""
    status, data = github_api_get(f"repos/{repo}/pulls?state=open", token=token)
    
    result = {
        "repo": repo,
        "http_status": status,
        "open_prs_count": 0,
        "prs": [],
        "errors": [],
        "all_compliant": True,
    }

    if status != 200:
        result["errors"].append(data.get("message", f"HTTP {status} fetching PRs"))
        result["all_compliant"] = False
        return result

    result["open_prs_count"] = len(data)

    for pr in data:
        pr_number = pr.get("number")
        title = pr.get("title")
        author = pr.get("user", {}).get("login", "").lower()
        head_branch = pr.get("head", {}).get("ref", "")
        html_url = pr.get("html_url", "")
        
        # Requested reviewers
        requested_reviewers = [
            r.get("login", "").lower() for r in pr.get("requested_reviewers", [])
        ]
        
        expected_reviewer = TRIANGULAR_REVIEW_MAP.get(author, "unknown")
        
        # Query reviews on this PR
        r_status, r_data = github_api_get(f"repos/{repo}/pulls/{pr_number}/reviews", token=token)
        reviews = []
        approved_by = []
        if r_status == 200 and isinstance(r_data, list):
            for rev in r_data:
                rev_user = rev.get("user", {}).get("login", "").lower()
                rev_state = rev.get("state", "")
                reviews.append({"user": rev_user, "state": rev_state})
                if rev_state == "APPROVED":
                    approved_by.append(rev_user)

        is_assigned_or_approved = (
            expected_reviewer in requested_reviewers or expected_reviewer in approved_by
        )

        pr_info = {
            "number": pr_number,
            "title": title,
            "head_branch": head_branch,
            "html_url": html_url,
            "author": author,
            "expected_reviewer": expected_reviewer,
            "requested_reviewers": requested_reviewers,
            "approved_by": approved_by,
            "compliant": is_assigned_or_approved,
        }
        result["prs"].append(pr_info)
        if not is_assigned_or_approved and author in TRIANGULAR_REVIEW_MAP:
            result["all_compliant"] = False

    return result


def print_report(protection_res: dict[str, Any] | None, pr_res: dict[str, Any] | None):
    """Render terminal report with status indicators."""
    print("=" * 74)
    print(" 🍁 CANADIAN OPEN DATA AGENTIC PLATFORM — BRANCH PROTECTION & REVIEW AUDIT")
    print("=" * 74)

    if protection_res:
        repo = protection_res["repo"]
        branch = protection_res["branch"]
        print(f"\n🛡️ Branch Protection Audit: {repo} -> [{branch}]")
        print("-" * 74)
        if not protection_res["protected"]:
            print(f"❌ Branch protection query failed (HTTP {protection_res['http_status']})")
            for err in protection_res["errors"]:
                print(f"   Details: {err}")
        else:
            for name, chk in protection_res["checks"].items():
                mark = "✅ PASS" if chk["passed"] else "❌ FAIL"
                print(f"  {mark} - {name.replace('_', ' ').title():<24} (Expected: {chk['required']}, Actual: {chk['actual']})")
            
            if protection_res["passed"]:
                print("\n  🌟 All branch protection constraints are strictly enforced.")
            else:
                print("\n  ⚠️ Some branch protection constraints are NOT satisfied.")

    if pr_res:
        print(f"\n👥 Triangular Peer Review Audit: ({pr_res['open_prs_count']} Open Pull Requests)")
        print("-" * 74)
        if pr_res["errors"]:
            print(f"❌ Error fetching PRs: {pr_res['errors']}")
        elif not pr_res["prs"]:
            print("  ℹ️ No active pull requests found.")
        else:
            for p in pr_res["prs"]:
                author_name = TEAM_MEMBER_NAMES.get(p["author"], p["author"])
                exp_rev = p["expected_reviewer"]
                status_icon = "✅" if p["compliant"] else "⚠️"
                
                print(f"  PR #{p['number']}: {p['title']}")
                print(f"    Branch: {p['head_branch']} | URL: {p['html_url']}")
                print(f"    Author: @{p['author']} ({author_name})")
                print(f"    Assigned/Expected Reviewer: @{exp_rev}")
                if p["approved_by"]:
                    print(f"    Approved by: {', '.join(['@' + u for u in p['approved_by']])}")
                else:
                    req = [f"@{r}" for r in p["requested_reviewers"]]
                    print(f"    Pending Review From: {', '.join(req) if req else 'None explicitly requested'}")
                print(f"    Triangular Protocol Status: {status_icon} {'Compliant' if p['compliant'] else 'Missing Reviewer Assignment'}\n")

    print("=" * 74)


def main():
    parser = argparse.ArgumentParser(
        description="Verify GitHub branch protection and triangular review assignments."
    )
    parser.add_argument(
        "--repo",
        default=DEFAULT_REPO,
        help=f"Target GitHub repository (default: {DEFAULT_REPO})",
    )
    parser.add_argument(
        "--branch",
        default="main",
        help="Branch to verify (default: main)",
    )
    parser.add_argument(
        "--skip-prs",
        action="store_true",
        help="Skip checking open pull requests",
    )
    parser.add_argument(
        "--skip-protection",
        action="store_true",
        help="Skip checking branch protection",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON results",
    )
    args = parser.parse_args()

    env = load_dotenv()
    token = env.get("GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN")

    if not token and not args.json:
        print("⚠️ Warning: GITHUB_TOKEN not found in .env or environment. API rate limits will be restricted.", file=sys.stderr)

    prot_res = None
    if not args.skip_protection:
        prot_res = check_branch_protection(args.repo, branch=args.branch, token=token)

    pr_res = None
    if not args.skip_prs:
        pr_res = check_triangular_prs(args.repo, token=token)

    if args.json:
        out = {"branch_protection": prot_res, "pull_requests": pr_res}
        print(json.dumps(out, indent=2))
    else:
        print_report(prot_res, pr_res)

    # Return exit code based on branch protection
    if prot_res and not prot_res["passed"]:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
