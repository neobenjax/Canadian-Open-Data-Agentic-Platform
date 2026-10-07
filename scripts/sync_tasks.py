#!/usr/bin/env python3
"""
Canadian Open Data Agentic Platform — Task Synchronization & Linear Mirror CLI
--------------------------------------------------------------------------------
Zero-dependency Python CLI that:
1. Parses TASKS.md to extract milestones, tasks, owners, and completion state.
2. Displays live progress summaries and owner-specific task lists.
3. Bidirectionally mirrors with Linear.app via GraphQL API when LINEAR_API_KEY is available.
4. Allows automated and agent-driven status updates (Todo -> In Progress -> Done).
"""

import os
import re
import sys
import json
import argparse
import urllib.request
from typing import Dict, List, Any, Optional

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

TASKS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "TASKS.md")
LINEAR_GRAPHQL_ENDPOINT = "https://api.linear.app/graphql"


def parse_tasks_md(filepath: str = TASKS_FILE) -> Dict[str, Any]:
    """Parse TASKS.md into structured milestone and task data."""
    if not os.path.exists(filepath):
        print(f"Error: {filepath} not found.", file=sys.stderr)
        return {"milestones": [], "tasks": []}

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    tasks = []
    milestones = []
    current_milestone = "General"

    # Regex patterns
    milestone_re = re.compile(r"^##\s+(?:🎯\s+)?(Milestone\s+\d+:[^\n]+)", re.MULTILINE)
    task_re = re.compile(
        r"^-\s+\[([ xX])\]\s+\*\*(CAN-\d+)(?:\s*\(([^)]+)\))?:\*\*\s*([^\n]+)",
        re.MULTILINE,
    )

    lines = content.splitlines()
    for line in lines:
        m_match = milestone_re.match(line)
        if m_match:
            current_milestone = m_match.group(1).strip()
            milestones.append(current_milestone)
            continue

        t_match = task_re.match(line)
        if t_match:
            is_done = t_match.group(1).lower() == "x"
            issue_key = t_match.group(2)
            owner_info = t_match.group(3) or ""
            desc = t_match.group(4).strip()

            owner = "Unassigned"
            if "Benjamin" in owner_info or "Benjamin" in desc:
                owner = "Benjamin Sanchez Zebadua"
            elif "Samir" in owner_info or "Samir" in desc:
                owner = "Samir Ibrahim"
            elif "Yassir" in owner_info or "Yassir" in desc:
                owner = "Yassir Tagelsir Khougali"
            elif "All" in owner_info:
                owner = "All Team Members"

            tasks.append({
                "key": issue_key,
                "milestone": current_milestone,
                "description": desc,
                "owner": owner,
                "done": is_done,
            })

    return {"milestones": milestones, "tasks": tasks}


def update_task_state_in_file(issue_key: str, mark_done: bool, filepath: str = TASKS_FILE) -> bool:
    """Update checkbox state for a specific task key in TASKS.md."""
    if not os.path.exists(filepath):
        return False

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    target_char = "x" if mark_done else " "
    pattern = re.compile(rf"^-\s+\[([ xX])\](\s+\*\*{issue_key}\b)", re.MULTILINE)

    if not pattern.search(content):
        print(f"Task {issue_key} not found in {filepath}.", file=sys.stderr)
        return False

    new_content = pattern.sub(rf"- [{target_char}]\2", content)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"Updated {issue_key} in TASKS.md to [{'x' if mark_done else ' '}].")
    return True


def query_linear_api(query: str, variables: Optional[Dict[str, Any]] = None, api_key: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Query the Linear GraphQL API using Personal API Key."""
    key = api_key or os.environ.get("LINEAR_API_KEY")
    if not key:
        return None

    headers = {
        "Content-Type": "application/json",
        "Authorization": key,
        "User-Agent": "CanData-Sync/1.0",
    }

    payload = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    req = urllib.request.Request(LINEAR_GRAPHQL_ENDPOINT, data=payload, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if "errors" in data:
                print(f"Linear GraphQL error: {data['errors']}", file=sys.stderr)
                return None
            return data.get("data")
    except Exception as e:
        print(f"Linear connection error: {e}", file=sys.stderr)
        return None


def fetch_linear_issues(team_key: str = "CAN", api_key: Optional[str] = None) -> List[Dict[str, Any]]:
    """Fetch issues from Linear for team CAN."""
    query = """
    query GetTeamIssues($teamKey: String!) {
        teams(filter: { key: { eq: $teamKey } }) {
            nodes {
                id
                name
                key
                issues(first: 100) {
                    nodes {
                        id
                        identifier
                        title
                        state {
                            name
                            type
                        }
                        assignee {
                            name
                        }
                    }
                }
            }
        }
    }
    """
    data = query_linear_api(query, {"teamKey": team_key}, api_key=api_key)
    if not data or not data.get("teams", {}).get("nodes"):
        return []

    team_nodes = data["teams"]["nodes"]
    if not team_nodes:
        return []
    return team_nodes[0].get("issues", {}).get("nodes", [])


def mutate_linear_issue_state(issue_identifier: str, state_name: str, api_key: Optional[str] = None) -> bool:
    """Transition an issue's state on Linear (e.g. In Progress, Done)."""
    key = api_key or os.environ.get("LINEAR_API_KEY")
    if not key:
        print("Note: Set LINEAR_API_KEY in environment to auto-sync with Linear cloud.", file=sys.stderr)
        return False

    # 1. Fetch issue ID and team workflow states
    lookup_query = """
    query LookupIssue($identifier: String!) {
        issue(id: $identifier) {
            id
            team {
                states {
                    nodes {
                        id
                        name
                    }
                }
            }
        }
    }
    """
    data = query_linear_api(lookup_query, {"identifier": issue_identifier}, api_key=key)
    if not data or not data.get("issue"):
        print(f"Could not find issue {issue_identifier} in Linear.", file=sys.stderr)
        return False

    issue_id = data["issue"]["id"]
    states = data["issue"]["team"]["states"]["nodes"]

    target_state_id = None
    for s in states:
        if s["name"].lower() == state_name.lower():
            target_state_id = s["id"]
            break

    if not target_state_id:
        print(f"Workflow state '{state_name}' not found in team workflow.", file=sys.stderr)
        return False

    # 2. Update issue
    mutation = """
    mutation UpdateIssueState($id: String!, $stateId: String!) {
        issueUpdate(id: $id, input: { stateId: $stateId }) {
            success
            issue {
                identifier
                state {
                    name
                }
            }
        }
    }
    """
    res = query_linear_api(mutation, {"id": issue_id, "stateId": target_state_id}, api_key=key)
    if res and res.get("issueUpdate", {}).get("success"):
        print(f"Linear: {issue_identifier} transitioned to '{state_name}'.")
        return True
    return False


def print_status_dashboard(parsed: Dict[str, Any], linear_issues: Optional[List[Dict[str, Any]]] = None):
    """Print an executive status report of tasks and mirror status."""
    tasks = parsed["tasks"]
    total = len(tasks)
    done_count = sum(1 for t in tasks if t["done"])
    pct = (done_count / total * 100) if total > 0 else 0

    print("=" * 72)
    print(" 🍁 CANADIAN OPEN DATA AGENTIC PLATFORM — TASK STATUS DASHBOARD")
    print("=" * 72)
    print(f"Total Tasks Tracked: {total} | Completed: {done_count} | Pending: {total - done_count}")
    print(f"Overall Progress:    [{'#' * int(pct // 5)}{'.' * (20 - int(pct // 5))}] {pct:.1f}%\n")

    # Group by Milestone
    milestone_groups: Dict[str, List[Dict[str, Any]]] = {}
    for t in tasks:
        milestone_groups.setdefault(t["milestone"], []).append(t)

    for m_name, m_tasks in milestone_groups.items():
        m_done = sum(1 for t in m_tasks if t["done"])
        print(f"📌 {m_name} ({m_done}/{len(m_tasks)} completed)")
        for t in m_tasks:
            icon = "✅" if t["done"] else "⏳"
            owner_initials = t["owner"].split()[0] if t["owner"] != "Unassigned" else "Team"
            print(f"   {icon} {t['key']:<7} [{owner_initials:<8}] {t['description'][:52]}")
        print()

    # Linear comparison if available
    if linear_issues is not None:
        print("-" * 72)
        print("🔗 LINEAR.APP CLOUD MIRROR STATUS")
        print("-" * 72)
        if not linear_issues:
            print("No Linear issues found or API key not configured.")
        else:
            linear_map = {i["identifier"]: i for i in linear_issues}
            print(f"Found {len(linear_issues)} issues in Linear workspace:")
            for t in tasks[:10]: # sample top 10
                lin_issue = linear_map.get(t["key"])
                if lin_issue:
                    state = lin_issue["state"]["name"]
                    match = "MATCH" if (t["done"] and state in ["Done", "Completed"]) or (not t["done"] and state not in ["Done", "Completed"]) else "DIFF"
                    print(f"   {t['key']}: TASKS.md={'Done' if t['done'] else 'Todo':<5} | Linear={state:<12} [{match}]")
                else:
                    print(f"   {t['key']}: TASKS.md={'Done' if t['done'] else 'Todo':<5} | Linear=Not Created")
    else:
        print("💡 Tip: Export LINEAR_API_KEY='lin_api_...' to enable live Linear cloud sync.\n")


def main():
    parser = argparse.ArgumentParser(description="CanData Task & Linear Synchronization CLI")
    parser.add_argument("--status", action="store_true", help="Print overall task dashboard")
    parser.add_argument("--owner", type=str, help="Filter tasks by owner name (Benjamin, Samir, Yassir)")
    parser.add_argument("--mark-done", type=str, metavar="KEY", help="Mark task as done in TASKS.md and Linear")
    parser.add_argument("--mark-in-progress", type=str, metavar="KEY", help="Mark task as In Progress in Linear")
    parser.add_argument("--sync-linear", action="store_true", help="Fetch live state from Linear workspace")
    parser.add_argument("--api-key", type=str, help="Linear personal API key")

    args = parser.parse_args()
    parsed = parse_tasks_md()

    if args.mark_done:
        key = args.mark_done.upper()
        update_task_state_in_file(key, mark_done=True)
        mutate_linear_issue_state(key, "Done", api_key=args.api_key)
        return

    if args.mark_in_progress:
        key = args.mark_in_progress.upper()
        mutate_linear_issue_state(key, "In Progress", api_key=args.api_key)
        return

    if args.owner:
        owner_filter = args.owner.lower()
        matched = [t for t in parsed["tasks"] if owner_filter in t["owner"].lower()]
        print(f"\nTasks assigned to '{args.owner}' ({len(matched)} total):")
        for t in matched:
            icon = "✅" if t["done"] else "⏳"
            print(f"  {icon} {t['key']:<7} [{t['milestone']}] {t['description']}")
        return

    # Default to dashboard
    linear_issues = None
    if args.sync_linear or os.environ.get("LINEAR_API_KEY") or args.api_key:
        linear_issues = fetch_linear_issues(team_key="CAN", api_key=args.api_key)

    print_status_dashboard(parsed, linear_issues)


if __name__ == "__main__":
    main()
