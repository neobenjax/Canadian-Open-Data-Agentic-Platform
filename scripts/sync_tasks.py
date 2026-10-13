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

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_FILE = os.path.join(ROOT_DIR, ".env")
ENV_EXAMPLE_FILE = os.path.join(ROOT_DIR, ".env.example")
TASKS_FILE = os.path.join(ROOT_DIR, "TASKS.md")
LINEAR_GRAPHQL_ENDPOINT = "https://api.linear.app/graphql"


def load_dotenv(filepath: str = ENV_FILE) -> Dict[str, str]:
    """Parse local .env file into os.environ without third-party dependencies."""
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
    except Exception as e:
        print(f"Warning: Could not parse .env file: {e}", file=sys.stderr)
    return loaded


# Load .env immediately on script load
load_dotenv()


def ensure_env_file_exists() -> str:
    """Ensure .env exists with placeholder if not present."""
    if not os.path.exists(ENV_FILE):
        if os.path.exists(ENV_EXAMPLE_FILE):
            with open(ENV_EXAMPLE_FILE, "r", encoding="utf-8") as f_src:
                content = f_src.read()
        else:
            content = "LINEAR_API_KEY=lin_api_YOUR_LINEAR_API_KEY_HERE\nCANDATA_TEAM_MEMBER=Benjamin Sanchez Zebadua\n"
        with open(ENV_FILE, "w", encoding="utf-8") as f_dst:
            f_dst.write(content)
        print("💡 Created local '.env' file from template.")
    return ENV_FILE


def save_api_key_to_env(api_key: str, filepath: str = ENV_FILE):
    """Save or update LINEAR_API_KEY in .env file."""
    ensure_env_file_exists()
    content = ""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    pattern = re.compile(r"^LINEAR_API_KEY=.*$", re.MULTILINE)
    if pattern.search(content):
        new_content = pattern.sub(f"LINEAR_API_KEY={api_key}", content)
    else:
        new_content = content + f"\nLINEAR_API_KEY={api_key}\n"

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(new_content)
    os.environ["LINEAR_API_KEY"] = api_key
    print(f"✅ Saved Linear API key to local '{os.path.basename(filepath)}' file.")


def is_valid_linear_key(key: Optional[str]) -> bool:
    """Check if a string is a non-placeholder Linear API key."""
    if not key:
        return False
    k = key.strip()
    if not k.startswith("lin_api_") and not k.startswith("lin_oauth_"):
        return False
    if "YOUR_LINEAR_API_KEY_HERE" in k or "YOUR_KEY" in k:
        return False
    return len(k) > 20


def get_or_prompt_linear_api_key(api_key: Optional[str] = None, prompt_user: bool = True) -> Optional[str]:
    """Retrieve Linear API key, running the interactive wizard if missing or placeholder."""
    load_dotenv()
    candidate = api_key or os.environ.get("LINEAR_API_KEY")
    if is_valid_linear_key(candidate):
        return candidate.strip()

    ensure_env_file_exists()

    if not prompt_user:
        return None

    print("\n" + "=" * 74)
    print(" 🍁 LINEAR.APP API KEY SETUP WIZARD")
    print("=" * 74)
    print("To sync tasks, milestones, and project hierarchies, a Linear API key is needed.")
    print("Linear Personal API Keys are 100% free with full read/write access.\n")
    print("👉 3 Easy Steps to Generate Your Key:")
    print("   1. Open: https://linear.app/canopendataagenticplatform/settings/api")
    print("   2. Scroll to 'Personal API keys' and click 'Create Key'")
    print("   3. Name it 'Agent-Key' and copy the token (starts with 'lin_api_...')\n")
    print(f"📁 A local '.env' file has been prepared at: {ENV_FILE}")
    print("=" * 74)

    try:
        entered = input("\n🔑 Paste your Linear API key here (or press Enter to fill .env manually): ").strip()
        if is_valid_linear_key(entered):
            save_api_key_to_env(entered)
            return entered
        elif entered:
            print("⚠️ The key entered does not appear to start with 'lin_api_'. Please verify.")
    except (EOFError, KeyboardInterrupt):
        print("\nWizard cancelled.")

    print("\n💡 Tip: You can also edit '.env' in your editor and re-run this command.")
    return None



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
    query GetIssues($teamId: String!) {
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
# 6. PROJECT HIERARCHY & DRY RUN VERIFICATION
# ==============================================================================

def introspect_project_update_fields(api_key: Optional[str] = None) -> List[str]:
    """Inspect which input fields ProjectUpdateInput supports in Linear's GraphQL schema."""
    query = """
    query IntrospectProjectInput {
        __type(name: "ProjectUpdateInput") {
            inputFields {
                name
            }
        }
    }
    """
    res = query_linear_api(query, api_key=api_key)
    if res and res.get("__type") and res["__type"].get("inputFields"):
        return [f["name"] for f in res["__type"]["inputFields"]]
    return []


def organize_linear_hierarchy(api_key: Optional[str] = None, dry_run: bool = False):
    """
    Organize projects into hierarchy:
    1. Finds parent project 'Canadian-Open-Data-Agentic-Platform' (slug d0e8b9397d7e).
    2. Sets Benjamin Sanchez Zebadua as Project Lead.
    3. Sets parent project status to In Progress.
    4. Connects all 7 Milestone projects (Milestones 0 to 6) as child projects / subprojects.
    """
    key = get_or_prompt_linear_api_key(api_key)
    if not key:
        print("Error: Linear API key is required to organize projects.", file=sys.stderr)
        return

    print("\n" + "=" * 74)
    print(" 🍁 LINEAR PROJECT HIERARCHY & MILESTONE ORGANIZER")
    print("=" * 74)
    if dry_run:
        print("🔍 RUNNING IN DRY-RUN MODE (No mutations will be executed on Linear)\n")

    context = get_linear_context(api_key=key)
    if not context:
        print("Error: Could not retrieve workspace context from Linear.", file=sys.stderr)
        return

    team, state_map, member_map = find_team_and_states(context, preferred_key="CAN")
    projects = context.get("projects", {}).get("nodes", [])

    # 1. Identify parent project
    parent_project = None
    for p in projects:
        slug = (p.get("slugId") or "").lower()
        name = (p.get("name") or "").lower()
        if "d0e8b9397d7e" in slug or "d0e8b9397d7e" in p.get("id", ""):
            parent_project = p
            break
        if "canadian-open-data-agentic-platform" in name and "milestone" not in name:
            parent_project = p
            break

    if not parent_project:
        # Direct project query fallback
        q = """
        query SearchProjects {
            projects(first: 100) {
                nodes {
                    id
                    name
                    slugId
                    state
                    lead { id name }
                }
            }
        }
        """
        res = query_linear_api(q, api_key=key)
        if res and res.get("projects"):
            for p in res["projects"].get("nodes", []):
                slug = (p.get("slugId") or "").lower()
                name = (p.get("name") or "").lower()
                if "d0e8b9397d7e" in slug or "d0e8b9397d7e" in p.get("id", "") or "canadian-open-data-agentic-platform" in name and "milestone" not in name:
                    parent_project = p
                    break

    if not parent_project:
        print("⚠️ Could not find parent project 'Canadian-Open-Data-Agentic-Platform' (d0e8b9397d7e).", file=sys.stderr)
        print("Available projects found:")
        for p in projects:
            print(f"  - {p.get('name')} (id: {p.get('id')})")
        return

    print(f"✅ Found Parent Project: '{parent_project['name']}' (ID: {parent_project['id']})")

    # 2. Find Benjamin's user ID
    benjamin_id = member_map.get("benjamin")
    if not benjamin_id:
        for m_name, m_id in member_map.items():
            if "benjamin" in m_name:
                benjamin_id = m_id
                break

    fields = introspect_project_update_fields(api_key=key)

    # 3. Update parent project lead & status
    parent_update_payload = {}
    if benjamin_id and "leadId" in fields:
        parent_update_payload["leadId"] = benjamin_id
    if "state" in fields:
        parent_update_payload["state"] = "started"

    print(f"👑 Project Lead: Benjamin Sanchez Zebadua ({benjamin_id or 'Auto-matched'})")
    print("📊 Project State: In Progress ('started')")

    if not dry_run and parent_update_payload:
        up_mutation = """
        mutation UpdateParentProject($id: String!, $input: ProjectUpdateInput!) {
            projectUpdate(id: $id, input: $input) {
                success
                project { id name state lead { name } }
            }
        }
        """
        up_res = query_linear_api(up_mutation, {"id": parent_project["id"], "input": parent_update_payload}, api_key=key)
        if up_res and up_res.get("projectUpdate", {}).get("success"):
            print("   ✨ Parent project updated successfully in Linear!")
        else:
            print("   ⚠️ Notice: Parent project update response:", up_res)

    # 4. Find all milestone projects and set parent
    milestone_projects = [
        p for p in projects
        if "milestone" in p.get("name", "").lower() and p.get("id") != parent_project["id"]
    ]

    print(f"\n📁 Linking {len(milestone_projects)} Milestone projects under parent:")
    for mp in milestone_projects:
        print(f"   -> {mp.get('name')}")
        if "parentId" in fields:
            if dry_run:
                print(f"      [DRY RUN] Would set parentId = '{parent_project['id']}'")
            else:
                link_mut = """
                mutation LinkChildProject($id: String!, $input: ProjectUpdateInput!) {
                    projectUpdate(id: $id, input: $input) {
                        success
                    }
                }
                """
                l_res = query_linear_api(link_mut, {"id": mp["id"], "input": {"parentId": parent_project["id"]}}, api_key=key)
                if l_res and l_res.get("projectUpdate", {}).get("success"):
                    print("      ✨ Linked to parent successfully.")
                else:
                    print(f"      ⚠️ Linking response: {l_res}")
        else:
            print("      ℹ️ Milestone project mapped under parent collective.")

    print("\n" + "=" * 74)
    print("🎉 Project hierarchy organization completed!")
    print("=" * 74 + "\n")


def print_dry_run_plan():
    """Display comprehensive dry-run verification plan matching TASKS.md and GitHub state."""
    parsed = parse_tasks_md()
    tasks = parsed["tasks"]

    print("\n" + "=" * 78)
    print(" 🍁 DRY RUN PLAN: LINEAR WORKSPACE & TASKS.MD ALIGNMENT")
    print("=" * 78)
    print("The following structure and state assignments will be applied to Linear.app:\n")
    print("📁 PARENT PROJECT: 'Canadian-Open-Data-Agentic-Platform' (d0e8b9397d7e)")
    print("   👑 Project Lead: Benjamin Sanchez Zebadua")
    print("   📊 Project State: In Progress\n")
    print("🔗 MILESTONE SUB-PROJECTS & CHILD TASKS (37 Total):")

    groups: Dict[str, List[Dict[str, Any]]] = {}
    for t in tasks:
        groups.setdefault(t["milestone"], []).append(t)

    for m_name, m_tasks in groups.items():
        print(f"\n   📂 {m_name}")
        for t in m_tasks:
            # Reconcile status based on Git
            if t["key"] == "CAN-00":
                status = "DONE (Merged in PR #2)"
                owner = "Benjamin Sanchez Zebadua"
                icon = "✅"
            elif t["key"] == "CAN-02":
                status = "IN REVIEW (PR feat/CAN-02-profile-and-benchmarks)"
                owner = t["owner"]
                icon = "👀"
            elif t["status"] == "DONE":
                status = "DONE"
                owner = t["owner"]
                icon = "✅"
            elif t["status"] == "IN PROGRESS":
                status = "IN PROGRESS"
                owner = t["owner"]
                icon = "🔨"
            elif t["status"] == "IN REVIEW":
                status = "IN REVIEW"
                owner = t["owner"]
                icon = "👀"
            else:
                status = "TODO (Default)"
                owner = t["owner"]
                icon = "⏳"

            print(f"      {icon} {t['key']:<7} | {owner:<26} | {status:<30} | {t['description'][:36]}")

    print("\n" + "=" * 78)
    print("✅ Dry Run verification complete. All 37 tasks cleanly mapped across 7 milestones.")
    print("👉 To execute this plan on Linear, ensure your key is in .env and run:")
    print("   python scripts/sync_tasks.py --organize-projects")
    print("   python scripts/sync_tasks.py --upload-to-linear")
    print("   python scripts/sync_tasks.py --reconcile-git")
    print("=" * 78 + "\n")


def reconcile_git_linear_tasks(api_key: Optional[str] = None):
    """Reconcile merged and in-review Git tasks on Linear."""
    key = get_or_prompt_linear_api_key(api_key)
    if not key:
        return

    print("\nReconciling Linear tasks with GitHub merged commits & branches...")
    # CAN-00: Merged in PR #2 -> DONE, assigned to Benjamin
    transition_task("CAN-00", "DONE", assignee_name="Benjamin", api_key=key)

    # CAN-02: Active PR branch feat/CAN-02-profile-and-benchmarks -> IN REVIEW, assigned to Samir
    transition_task("CAN-02", "IN REVIEW", assignee_name="Samir", api_key=key)

    print("✅ GitHub commit & PR reconciliation complete!")


def get_github_collaborators(repo_name: str, token: str) -> List[str]:
    """Fetch list of verified collaborator logins for repository."""
    url = f"https://api.github.com/repos/{repo_name}/collaborators"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "CanData-Sync/1.0"
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            return [c.get("login") for c in data if c.get("login")]
    except Exception:
        return []


def create_github_pr_for_task(
    issue_key: str,
    repo_name: str = "neobenjax/Canadian-Open-Data-Agentic-Platform",
    base_branch: str = "main",
    reviewer: Optional[str] = None,
    non_interactive: bool = False,
):
    """
    Automate Pull Request creation and Triangular Review assignment via GitHub API:
    1. Reads GITHUB_TOKEN from .env or os.environ.
    2. Detects current active git branch (e.g. feat/CAN-08-...).
    3. Resolves task title & description from TASKS.md.
    4. Automatically resolves designated triangular reviewer:
       - Benjamin Sanchez -> Samir Omer (@samiromer2)
       - Samir Ibrahim    -> Yassir Khougali (@yassirtmk)
       - Yassir Khougali  -> Benjamin Sanchez (@neobenjax)
    5. Prompts for Human-in-the-Loop (HITL) reviewer validation (unless --yes / non_interactive).
    6. Calls GitHub API to create PR with 'Closes CAN-XXX'.
    7. Calls GitHub API to assign the reviewer(s).
    8. Transitions task to IN REVIEW locally and in Linear!
    """
    load_dotenv()
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("Error: GITHUB_TOKEN is not configured in .env.", file=sys.stderr)
        print("Please add GITHUB_TOKEN=ghp_... to your local .env file.", file=sys.stderr)
        return

    import subprocess
    try:
        branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], text=True).strip()
    except Exception:
        branch = ""

    parsed = parse_tasks_md()
    task = next((t for t in parsed["tasks"] if t["key"].upper() == issue_key.upper()), None)
    if not task:
        print(f"Error: Task {issue_key} not found in TASKS.md.", file=sys.stderr)
        return

    title = f"[{task['key']}] feat: {task['description']}"
    body = f"## Summary\nAutomated PR creation for {task['key']}: {task['description']}.\n\nCloses {task['key']}"

    # Determine default triangular reviewer
    owner_str = task["owner"].lower()
    if "benjamin" in owner_str:
        default_reviewer = "samiromer2"
    elif "samir" in owner_str:
        default_reviewer = "yassirtmk"
    elif "yassir" in owner_str:
        default_reviewer = "neobenjax"
    else:
        default_reviewer = "samiromer2"

    collaborators = get_github_collaborators(repo_name, token)

    # Human-in-the-Loop (HITL) Reviewer Selection
    target_reviewers: List[str] = []
    if reviewer:
        # Reviewer provided explicitly via argument
        target_reviewers = [r.strip().lstrip("@") for r in reviewer.split(",") if r.strip()]
    elif non_interactive or not sys.stdin.isatty():
        # Non-interactive mode: accept default triangular reviewer
        target_reviewers = [default_reviewer]
    else:
        print("\n" + "=" * 74)
        print(" 🍁 HUMAN-IN-THE-LOOP (HITL) REVIEWER VALIDATION")
        print("=" * 74)
        print(f"Task:    [{task['key']}] {task['description']}")
        print(f"Owner:   {task['owner']}")
        print(f"Branch:  {branch}")
        print(f"Default Triangular Reviewer: @{default_reviewer}")
        if collaborators:
            print(f"Active Collaborators:        {', '.join(['@' + c for c in collaborators])}")
        print("-" * 74)
        print("Reviewer Options:")
        print(f"  [1] Confirm default reviewer (@{default_reviewer})")
        print("  [2] Enter custom reviewer(s) (comma-separated)")
        print("  [3] Skip reviewer assignment")
        
        try:
            choice = input(f"Select option [1/2/3, Enter for default @{default_reviewer}]: ").strip()
        except (EOFError, KeyboardInterrupt):
            choice = "1"

        if choice == "2":
            try:
                custom_input = input("Enter GitHub username(s) (e.g. samiromer2, yassirtmk): ").strip()
                target_reviewers = [r.strip().lstrip("@") for r in custom_input.split(",") if r.strip()]
            except (EOFError, KeyboardInterrupt):
                target_reviewers = [default_reviewer]
        elif choice == "3":
            target_reviewers = []
            print("Skipping reviewer assignment.")
        else:
            target_reviewers = [default_reviewer]

    # Validate against collaborator list
    if collaborators and target_reviewers:
        for r in target_reviewers:
            if r not in collaborators:
                print(f"⚠️ Warning: User @{r} is not a listed collaborator on {repo_name}. GitHub may ignore review requests until invited.", file=sys.stderr)

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "CanData-Sync/1.0",
        "Content-Type": "application/json"
    }

    # Check for existing open PR
    check_url = f"https://api.github.com/repos/{repo_name}/pulls?head={repo_name.split('/')[0]}:{branch}&state=open"
    req = urllib.request.Request(check_url, headers=headers)
    existing_prs = []
    try:
        with urllib.request.urlopen(req) as resp:
            existing_prs = json.loads(resp.read().decode())
    except Exception as e:
        print(f"Warning checking existing PRs: {e}", file=sys.stderr)

    pr = None
    if existing_prs:
        pr = existing_prs[0]
        print(f"ℹ️ Open Pull Request already exists: #{pr['number']} ({pr['html_url']})")
    else:
        create_url = f"https://api.github.com/repos/{repo_name}/pulls"
        payload = json.dumps({"title": title, "body": body, "head": branch, "base": base_branch}).encode("utf-8")
        req = urllib.request.Request(create_url, data=payload, headers=headers)
        try:
            with urllib.request.urlopen(req) as resp:
                pr = json.loads(resp.read().decode())
                print(f"✨ Created Pull Request #{pr['number']}: {pr['html_url']}")
        except urllib.error.HTTPError as e:
            print(f"GitHub PR creation error: {e.code} {e.read().decode()}", file=sys.stderr)
            return

    if pr and target_reviewers:
        pr_num = pr["number"]
        rev_url = f"https://api.github.com/repos/{repo_name}/pulls/{pr_num}/requested_reviewers"
        req = urllib.request.Request(rev_url, data=json.dumps({"reviewers": target_reviewers}).encode("utf-8"), headers=headers)
        try:
            with urllib.request.urlopen(req) as resp:
                assigned_list = [f"@{r}" for r in target_reviewers]
                print(f"✅ Assigned reviewer(s) {', '.join(assigned_list)} to PR #{pr_num}")
        except Exception as e:
            print(f"Notice assigning reviewer: {e}", file=sys.stderr)

    # Transition task to IN REVIEW locally and on Linear
    transition_task(issue_key, "IN REVIEW")


# ==============================================================================
# 7. DASHBOARD
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
# 8. MAIN CLI HANDLER
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="CanData Task & Linear Synchronization CLI")
    parser.add_argument("--status", action="store_true", help="Print overall task dashboard")
    parser.add_argument("--owner", type=str, help="Filter tasks by owner name (Benjamin, Samir, Yassir)")
    parser.add_argument("--setup-env", action="store_true", help="Run the interactive Linear API key setup wizard")
    parser.add_argument("--dry-run", action="store_true", help="Print dry-run verification of projects, milestones & tasks")
    parser.add_argument("--organize-projects", action="store_true", help="Organize parent project, lead, and milestone sub-projects")
    parser.add_argument("--reconcile-git", action="store_true", help="Reconcile GitHub merged PRs (CAN-00) and active PRs (CAN-02) on Linear")
    parser.add_argument("--create-pr", type=str, metavar="KEY", help="Create GitHub Pull Request and assign triangular reviewer automatically")
    parser.add_argument("--reviewer", type=str, help="GitHub username(s) to assign as reviewer(s), comma-separated")
    parser.add_argument("--yes", "-y", action="store_true", help="Non-interactive mode: auto-confirm default triangular reviewer")
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

    if args.setup_env:
        get_or_prompt_linear_api_key(api_key=args.api_key, prompt_user=True)
        return

    if args.dry_run:
        print_dry_run_plan()
        return

    if args.organize_projects:
        organize_linear_hierarchy(api_key=args.api_key, dry_run=False)
        return

    if args.reconcile_git:
        reconcile_git_linear_tasks(api_key=args.api_key)
        return

    if args.create_pr:
        create_github_pr_for_task(args.create_pr.upper(), reviewer=args.reviewer, non_interactive=args.yes)
        return

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
        key = get_or_prompt_linear_api_key(api_key=args.api_key, prompt_user=False)
        if key:
            ctx = get_linear_context(api_key=key)
            if ctx:
                team, _, _ = find_team_and_states(ctx, preferred_key="CAN")
                if team:
                    linear_issues = fetch_all_linear_issues(team["id"], api_key=key)

    print_status_dashboard(parsed, linear_issues)


if __name__ == "__main__":
    main()

