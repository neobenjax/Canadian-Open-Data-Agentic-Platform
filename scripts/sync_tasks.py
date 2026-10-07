#!/usr/bin/env python3
"""
Canadian Open Data Agentic Platform — Task Synchronization & Linear Mirror CLI
--------------------------------------------------------------------------------
Zero-dependency Python CLI that:
1. Parses TASKS.md to extract milestones, tasks, owners, and completion state.
2. Uploads all Milestones and Tasks into Linear.app via GraphQL API or CSV export.
3. Bidirectionally tracks lifecycle states (TODO -> IN PROGRESS -> IN REVIEW -> DONE).
4. Updates both Linear.app and TASKS.md synchronously.
"""

import os
import re
import sys
import csv
import json
import argparse
import urllib.request
from typing import Dict, List, Any, Optional, Tuple

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

TASKS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "TASKS.md")
LINEAR_GRAPHQL_ENDPOINT = "https://api.linear.app/graphql"


# ==============================================================================
# 1. TASKS.md PARSER & UPDATER
# ==============================================================================

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

    milestone_re = re.compile(r"^##\s+(?:🎯\s+)?(Milestone\s+\d+:[^\n]+)", re.MULTILINE)
    # Matches: - [ ] **CAN-01 (Benjamin's Chore):** [OPTIONAL_STATUS] description
    task_re = re.compile(
        r"^-\s+\[([ xX])\]\s+\*\*(CAN-\d+)(?:\s*\(([^)]+)\))?:\*\*\s*(?:\[(IN PROGRESS|IN REVIEW|DONE|TODO)\]\s*)?([^\n]+)",
        re.MULTILINE,
    )

    lines = content.splitlines()
    for idx, line in enumerate(lines):
        m_match = milestone_re.match(line)
        if m_match:
            current_milestone = m_match.group(1).strip()
            milestones.append(current_milestone)
            continue

        # Header match
        task_header_re = re.compile(
            r"^-\s+\[([ xX])\]\s+\*\*(CAN-\d+)(?:\s*\(([^)]+)\))?:\*\*\s*(?:\[(IN PROGRESS|IN REVIEW|DONE|TODO)\]\s*)?(.*)",
        )
        t_match = task_header_re.match(line)
        if t_match:
            is_checkbox_done = t_match.group(1).lower() == "x"
            issue_key = t_match.group(2)
            owner_info = t_match.group(3) or ""
            explicit_status = t_match.group(4)
            desc = t_match.group(5).strip()

            # If description is empty on the same line, check following lines for *Goal:*
            if not desc:
                for next_idx in range(idx + 1, min(idx + 4, len(lines))):
                    next_line = lines[next_idx].strip()
                    if next_line.startswith("- *Goal:*"):
                        desc = next_line.replace("- *Goal:*", "").strip()
                        break
                    elif next_line.startswith("- ["):
                        break
                if not desc and owner_info:
                    desc = owner_info

            status = "TODO"
            if is_checkbox_done:
                status = "DONE"
            elif explicit_status:
                status = explicit_status.upper()

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
                "owner_info": owner_info,
                "description": desc,
                "owner": owner,
                "status": status,
                "done": status == "DONE",
            })

    return {"milestones": milestones, "tasks": tasks}


def update_task_state_in_file(issue_key: str, new_status: str, filepath: str = TASKS_FILE) -> bool:
    """
    Update checkbox and status tag for an issue in TASKS.md.
    Statuses supported: 'TODO', 'IN PROGRESS', 'IN REVIEW', 'DONE'
    """
    if not os.path.exists(filepath):
        return False

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    status_upper = new_status.upper()
    is_done = status_upper == "DONE"
    check_char = "x" if is_done else " "

    # Matches: - [ ] **CAN-01...:** [STATUS]
    pattern = re.compile(
        rf"^-\s+\[([ xX])\]([ \t]+\*\*{issue_key}(?:[ \t]*\([^)]+\))?:\*\*)[ \t]*(?:\[(IN PROGRESS|IN REVIEW|DONE|TODO)\][ \t]*)?",
        re.MULTILINE,
    )

    if not pattern.search(content):
        print(f"Task {issue_key} not found in {filepath}.", file=sys.stderr)
        return False

    status_tag = f"[{status_upper}] " if status_upper not in ["TODO", "DONE"] else ""
    replacement = rf"- [{check_char}]\2 {status_tag}"

    new_content = pattern.sub(replacement, content)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"Updated {issue_key} in TASKS.md -> [{check_char}] {status_upper}")
    return True


# ==============================================================================
# 2. LINEAR GRAPHQL API CLIENT
# ==============================================================================

def query_linear_api(query: str, variables: Optional[Dict[str, Any]] = None, api_key: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Execute a GraphQL query against Linear API."""
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
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if "errors" in data:
                print(f"Linear GraphQL error: {data['errors']}", file=sys.stderr)
                return None
            return data.get("data")
    except Exception as e:
        print(f"Linear API connection error: {e}", file=sys.stderr)
        return None


def get_linear_context(api_key: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Fetch teams, members, workflow states, and projects from Linear."""
    query = """
    query GetLinearContext {
        teams {
            nodes {
                id
                name
                key
                members {
                    nodes {
                        id
                        name
                        displayName
                        email
                    }
                }
                states {
                    nodes {
                        id
                        name
                        type
                    }
                }
            }
        }
        projects {
            nodes {
                id
                name
            }
        }
    }
    """
    return query_linear_api(query, api_key=api_key)


def find_team_and_states(context: Dict[str, Any], preferred_key: str = "CAN") -> Tuple[Optional[Dict[str, Any]], Dict[str, str], Dict[str, str]]:
    """Locate the target team, mapping of state names -> state IDs, and member names -> member IDs."""
    teams = context.get("teams", {}).get("nodes", [])
    if not teams:
        return None, {}, {}

    # Prefer team matching CAN, or fallback to first available team (e.g. BEN)
    team = None
    for t in teams:
        if t["key"].upper() == preferred_key.upper():
            team = t
            break
    if not team and teams:
        team = teams[0]

    state_map = {}
    for s in team.get("states", {}).get("nodes", []):
        name_lower = s["name"].lower()
        state_map[name_lower] = s["id"]
        # Standardize synonyms
        if s["type"] == "started" and "progress" in name_lower:
            state_map["in progress"] = s["id"]
        elif s["type"] == "started" and "review" in name_lower:
            state_map["in review"] = s["id"]
        elif s["type"] == "unstarted" or "todo" in name_lower or "backlog" in name_lower:
            state_map["todo"] = s["id"]
        elif s["type"] == "completed" or "done" in name_lower:
            state_map["done"] = s["id"]

    member_map = {}
    for m in team.get("members", {}).get("nodes", []):
        m_name = (m.get("name") or m.get("displayName") or "").lower()
        member_map[m_name] = m["id"]
        if "benjamin" in m_name:
            member_map["benjamin"] = m["id"]
        elif "samir" in m_name:
            member_map["samir"] = m["id"]
        elif "yassir" in m_name:
            member_map["yassir"] = m["id"]

    return team, state_map, member_map


def ensure_linear_project(name: str, team_id: str, existing_projects: List[Dict[str, Any]], api_key: Optional[str] = None) -> Optional[str]:
    """Get or create a Project in Linear for a Milestone."""
    for p in existing_projects:
        if p["name"].strip().lower() == name.strip().lower():
            return p["id"]

    # Create project
    mutation = """
    mutation CreateProject($input: ProjectCreateInput!) {
        projectCreate(input: $input) {
            success
            project {
                id
                name
            }
        }
    }
    """
    res = query_linear_api(mutation, {"input": {"name": name, "teamIds": [team_id]}}, api_key=api_key)
    if res and res.get("projectCreate", {}).get("success"):
        p_id = res["projectCreate"]["project"]["id"]
        existing_projects.append({"id": p_id, "name": name})
        return p_id
    return None


def fetch_all_linear_issues(team_id: str, api_key: Optional[str] = None) -> List[Dict[str, Any]]:
    """Fetch all issues for a team."""
    query = """
    query GetIssues($teamId: ID!) {
        team(id: $teamId) {
            issues(first: 200) {
                nodes {
                    id
                    identifier
                    title
                    state {
                        name
                        type
                    }
                    assignee {
                        id
                        name
                    }
                }
            }
        }
    }
    """
    res = query_linear_api(query, {"teamId": team_id}, api_key=api_key)
    if res and res.get("team"):
        return res["team"].get("issues", {}).get("nodes", [])
    return []


# ==============================================================================
# 3. INTERACTIVE / BULK UPLOAD TO LINEAR
# ==============================================================================

def upload_all_tasks_to_linear(api_key: Optional[str] = None):
    """Guide the user to upload all Milestones and Tasks from TASKS.md to Linear."""
    parsed = parse_tasks_md()
    tasks = parsed["tasks"]
    milestones = parsed["milestones"]

    print("\n" + "=" * 74)
    print(" 🚀 CANADIAN OPEN DATA AGENTIC PLATFORM — LINEAR BULK UPLOADER")
    print("=" * 74)
    print(f"Found {len(tasks)} tasks across {len(milestones)} milestones in TASKS.md.\n")

    key = api_key or os.environ.get("LINEAR_API_KEY")
    if not key:
        print("A Linear Personal API Key is required to create issues.")
        print("👉 How to get your API Key in 30 seconds (Free Plan supported):")
        print("   1. Open: https://linear.app/canopendataagenticplatform")
        print("   2. Click avatar (bottom left) -> Settings -> Account -> Security & Access")
        print("   3. Under 'Personal API keys', click 'Create Key', name it 'TaskUploader'")
        print("   4. Copy the 'lin_api_...' token.\n")
        try:
            key = input("Enter your Linear API Key (or press Enter to cancel): ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nCancelled.")
            return

        if not key:
            print("No key provided. You can also generate a CSV file using: python scripts/sync_tasks.py --export-csv")
            return

    print("\nConnecting to Linear.app...")
    context = get_linear_context(api_key=key)
    if not context:
        print("Error: Could not connect to Linear with the provided key.", file=sys.stderr)
        return

    team, state_map, member_map = find_team_and_states(context, preferred_key="CAN")
    if not team:
        print("Error: No teams found in your Linear workspace.", file=sys.stderr)
        return

    print(f"✅ Connected to Team: '{team['name']}' (Key: {team['key']})")
    print(f"   Available workflow states: {', '.join(state_map.keys())}")
    print(f"   Detected team members: {', '.join(member_map.keys())}\n")

    # Fetch existing issues to avoid duplicates
    existing_issues = fetch_all_linear_issues(team["id"], api_key=key)
    existing_keys = set()
    for iss in existing_issues:
        # Check if title starts with CAN-XX or contains it
        m = re.search(r"\bCAN-\d+\b", iss["title"])
        if m:
            existing_keys.add(m.group(0))

    projects = context.get("projects", {}).get("nodes", [])

    created_count = 0
    skipped_count = 0

    print("Uploading Milestones and Tasks:")
    for task in tasks:
        key_id = task["key"]
        if key_id in existing_keys:
            print(f"   ⏭️  [EXISTS]  {key_id:<7} {task['description'][:50]}")
            skipped_count += 1
            continue

        # Find or create project for milestone
        project_id = ensure_linear_project(task["milestone"], team["id"], projects, api_key=key)

        # Match assignee
        assignee_id = None
        for member_name, m_id in member_map.items():
            if member_name in task["owner"].lower():
                assignee_id = m_id
                break

        # State ID
        state_id = state_map.get(task["status"].lower()) or state_map.get("todo")

        title = f"[{key_id}] {task['description'][:80]}"
        desc_body = (
            f"**Milestone:** {task['milestone']}\n\n"
            f"**Owner:** {task['owner']}\n\n"
            f"**Description:** {task['description']}\n\n"
            f"**Task Key:** `{key_id}`\n\n"
            f"Tracked from `TASKS.md`."
        )

        create_mutation = """
        mutation CreateIssue($input: IssueCreateInput!) {
            issueCreate(input: $input) {
                success
                issue {
                    id
                    identifier
                    url
                }
            }
        }
        """

        input_payload = {
            "teamId": team["id"],
            "title": title,
            "description": desc_body,
            "projectId": project_id,
            "stateId": state_id,
        }
        if assignee_id:
            input_payload["assigneeId"] = assignee_id

        res = query_linear_api(create_mutation, {"input": input_payload}, api_key=key)
        if res and res.get("issueCreate", {}).get("success"):
            iss = res["issueCreate"]["issue"]
            print(f"   ✨ [CREATED] {key_id:<7} -> {iss['identifier']} ({task['owner'].split()[0]})")
            created_count += 1
        else:
            print(f"   ❌ [FAILED]  {key_id:<7}")

    print("\n" + "=" * 74)
    print(f"🎉 Upload Complete! Created: {created_count} | Already Existing: {skipped_count}")
    print(f"👉 View your active board: https://linear.app/canopendataagenticplatform/team/{team['key']}/active")
    print("=" * 74 + "\n")


# ==============================================================================
# 4. CSV EXPORT FOR 1-CLICK NATIVE LINEAR IMPORT
# ==============================================================================

def export_tasks_to_csv(output_file: str = "linear_tasks_import.csv"):
    """Export TASKS.md into a Linear-compatible CSV import format."""
    parsed = parse_tasks_md()
    tasks = parsed["tasks"]

    fieldnames = ["Title", "Description", "Status", "Assignee", "Project"]
    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for t in tasks:
            status_str = "Done" if t["status"] == "DONE" else ("In Progress" if t["status"] == "IN PROGRESS" else "Todo")
            writer.writerow({
                "Title": f"[{t['key']}] {t['description']}",
                "Description": f"Milestone: {t['milestone']}\nOwner: {t['owner']}\nKey: {t['key']}",
                "Status": status_str,
                "Assignee": t["owner"] if t["owner"] != "All Team Members" else "",
                "Project": t["milestone"],
            })

    print(f"✅ Exported {len(tasks)} tasks to '{output_file}'.")
    print("👉 To import via web: Linear -> Settings -> Import / Export -> Import CSV.")


# ==============================================================================
# 5. TRANSITION WORKFLOW (IN PROGRESS, IN REVIEW, DONE)
# ==============================================================================

def transition_task(issue_key: str, new_status: str, assignee_name: Optional[str] = None, api_key: Optional[str] = None):
    """
    Transition a task across the full lifecycle:
    1. Updates TASKS.md with [STATUS] and checkbox state.
    2. Synchronizes with Linear API if API key is present.
    """
    status_upper = new_status.upper()
    valid_statuses = ["TODO", "IN PROGRESS", "IN REVIEW", "DONE"]
    if status_upper not in valid_statuses:
        print(f"Invalid status '{new_status}'. Choose from: {valid_statuses}", file=sys.stderr)
        return

    # 1. Update TASKS.md locally
    update_task_state_in_file(issue_key, status_upper)

    # 2. Update Linear API
    key = api_key or os.environ.get("LINEAR_API_KEY")
    if not key:
        print("Note: Set LINEAR_API_KEY to mirror status changes to Linear cloud.", file=sys.stderr)
        return

    context = get_linear_context(api_key=key)
    if not context:
        return

    team, state_map, member_map = find_team_and_states(context, preferred_key="CAN")
    if not team:
        return

    # Find the issue in Linear
    issues = fetch_all_linear_issues(team["id"], api_key=key)
    linear_issue = None
    for iss in issues:
        if issue_key.upper() in iss["title"].upper() or issue_key.upper() == iss["identifier"].upper():
            linear_issue = iss
            break

    if not linear_issue:
        print(f"Issue matching '{issue_key}' not found in Linear.", file=sys.stderr)
        return

    target_state_id = state_map.get(status_upper.lower())
    if not target_state_id:
        print(f"Workflow state for '{status_upper}' not mapped in Linear team.", file=sys.stderr)
        return

    input_payload = {"stateId": target_state_id}

    # Optionally reassign
    if assignee_name:
        for m_name, m_id in member_map.items():
            if assignee_name.lower() in m_name:
                input_payload["assigneeId"] = m_id
                break

    mutation = """
    mutation UpdateIssue($id: String!, $input: IssueUpdateInput!) {
        issueUpdate(id: $id, input: $input) {
            success
            issue {
                identifier
                state {
                    name
                }
                assignee {
                    name
                }
            }
        }
    }
    """

    res = query_linear_api(mutation, {"id": linear_issue["id"], "input": input_payload}, api_key=key)
    if res and res.get("issueUpdate", {}).get("success"):
        updated = res["issueUpdate"]["issue"]
        assignee_str = f" (Assigned: {updated['assignee']['name']})" if updated.get("assignee") else ""
        print(f"Linear: {updated['identifier']} is now [{updated['state']['name']}]{assignee_str}")


# ==============================================================================
# 6. DASHBOARD
# ==============================================================================

def print_status_dashboard(parsed: Dict[str, Any], linear_issues: Optional[List[Dict[str, Any]]] = None):
    """Print an executive status report of tasks and mirror status."""
    tasks = parsed["tasks"]
    total = len(tasks)
    done_count = sum(1 for t in tasks if t["status"] == "DONE")
    in_progress_count = sum(1 for t in tasks if t["status"] == "IN PROGRESS")
    in_review_count = sum(1 for t in tasks if t["status"] == "IN REVIEW")
    todo_count = total - done_count - in_progress_count - in_review_count
    pct = (done_count / total * 100) if total > 0 else 0

    print("=" * 74)
    print(" 🍁 CANADIAN OPEN DATA AGENTIC PLATFORM — TASK STATUS DASHBOARD")
    print("=" * 74)
    print(f"Total Tasks: {total} | Done: {done_count} | In Review: {in_review_count} | In Progress: {in_progress_count} | Todo: {todo_count}")
    print(f"Overall Progress: [{'#' * int(pct // 5)}{'.' * (20 - int(pct // 5))}] {pct:.1f}%\n")

    milestone_groups: Dict[str, List[Dict[str, Any]]] = {}
    for t in tasks:
        milestone_groups.setdefault(t["milestone"], []).append(t)

    for m_name, m_tasks in milestone_groups.items():
        m_done = sum(1 for t in m_tasks if t["status"] == "DONE")
        print(f"📌 {m_name} ({m_done}/{len(m_tasks)} completed)")
        for t in m_tasks:
            icon = "✅" if t["status"] == "DONE" else ("👀" if t["status"] == "IN REVIEW" else ("🔨" if t["status"] == "IN PROGRESS" else "⏳"))
            owner_initials = t["owner"].split()[0] if t["owner"] != "Unassigned" else "Team"
            status_tag = f"[{t['status']}]" if t['status'] != "TODO" and t['status'] != "DONE" else ""
            print(f"   {icon} {t['key']:<7} [{owner_initials:<8}] {status_tag:<13} {t['description'][:46]}")
        print()

    if linear_issues:
        print("-" * 74)
        print("🔗 LINEAR.APP CLOUD MIRROR STATUS")
        print("-" * 74)
        linear_map = {i["title"]: i for i in linear_issues}
        for t in tasks[:8]:
            matched = None
            for title, iss in linear_map.items():
                if t["key"] in title:
                    matched = iss
                    break
            if matched:
                state = matched["state"]["name"]
                print(f"   {t['key']}: TASKS.md={t['status']:<11} | Linear={state:<12}")
            else:
                print(f"   {t['key']}: TASKS.md={t['status']:<11} | Linear=Not Created")
    else:
        print("💡 Tip: Run 'python scripts/sync_tasks.py --upload-to-linear' to populate your Linear board.\n")


# ==============================================================================
# 7. MAIN CLI HANDLER
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="CanData Task & Linear Synchronization CLI")
    parser.add_argument("--status", action="store_true", help="Print overall task dashboard")
    parser.add_argument("--owner", type=str, help="Filter tasks by owner name (Benjamin, Samir, Yassir)")
    parser.add_argument("--upload-to-linear", action="store_true", help="Interactively upload all TASKS.md tasks to Linear")
    parser.add_argument("--export-csv", type=str, nargs="?", const="linear_tasks_import.csv", help="Export tasks to CSV for Linear import")
    parser.add_argument("--mark-todo", type=str, metavar="KEY", help="Set task state to TODO")
    parser.add_argument("--mark-in-progress", type=str, metavar="KEY", help="Set task state to IN PROGRESS on Linear & TASKS.md")
    parser.add_argument("--mark-in-review", type=str, metavar="KEY", help="Set task state to IN REVIEW on Linear & TASKS.md")
    parser.add_argument("--mark-done", type=str, metavar="KEY", help="Set task state to DONE on Linear & TASKS.md")
    parser.add_argument("--assignee", type=str, help="Assignee name to assign on Linear")
    parser.add_argument("--sync-linear", action="store_true", help="Fetch live state from Linear workspace")
    parser.add_argument("--api-key", type=str, help="Linear personal API key")

    args = parser.parse_args()

    if args.upload_to_linear:
        upload_all_tasks_to_linear(api_key=args.api_key)
        return

    if args.export_csv:
        export_tasks_to_csv(output_file=args.export_csv)
        return

    if args.mark_todo:
        transition_task(args.mark_todo.upper(), "TODO", assignee_name=args.assignee, api_key=args.api_key)
        return

    if args.mark_in_progress:
        transition_task(args.mark_in_progress.upper(), "IN PROGRESS", assignee_name=args.assignee, api_key=args.api_key)
        return

    if args.mark_in_review:
        transition_task(args.mark_in_review.upper(), "IN REVIEW", assignee_name=args.assignee, api_key=args.api_key)
        return

    if args.mark_done:
        transition_task(args.mark_done.upper(), "DONE", assignee_name=args.assignee, api_key=args.api_key)
        return

    parsed = parse_tasks_md()

    if args.owner:
        owner_filter = args.owner.lower()
        matched = [t for t in parsed["tasks"] if owner_filter in t["owner"].lower()]
        print(f"\nTasks assigned to '{args.owner}' ({len(matched)} total):")
        for t in matched:
            icon = "✅" if t["status"] == "DONE" else ("🔨" if t["status"] == "IN PROGRESS" else "⏳")
            print(f"  {icon} {t['key']:<7} [{t['status']:<11}] {t['description']}")
        return

    linear_issues = None
    if args.sync_linear:
        key = args.api_key or os.environ.get("LINEAR_API_KEY")
        if key:
            ctx = get_linear_context(api_key=key)
            if ctx:
                team, _, _ = find_team_and_states(ctx, preferred_key="CAN")
                if team:
                    linear_issues = fetch_all_linear_issues(team["id"], api_key=key)

    print_status_dashboard(parsed, linear_issues)


if __name__ == "__main__":
    main()
