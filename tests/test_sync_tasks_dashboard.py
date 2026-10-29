"""Tests for the Linear mirror dashboard and the label/cycle applied to newly uploaded issues."""

import datetime
from typing import Any

import pytest

from scripts import sync_tasks
from scripts.sync_tasks import (
    cycle_id_for_task,
    infer_area_label,
    milestone_sprint,
    summarize_linear_mirror,
)

TODAY = datetime.date(2026, 10, 29)


def _issue(
    identifier: str,
    title: str,
    state: str = "Todo",
    state_type: str = "unstarted",
    assignee: str | None = "Yassir Khougali",
    due: str | None = None,
    priority: int = 0,
    estimate: float | None = None,
    cycle: str | None = None,
    labels: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "identifier": identifier,
        "title": title,
        "state": {"name": state, "type": state_type},
        "assignee": {"name": assignee} if assignee else None,
        "dueDate": due,
        "priority": priority,
        "estimate": estimate,
        "cycle": {"name": cycle} if cycle else None,
        "labels": {"nodes": [{"name": n} for n in labels]},
    }


def _task(
    key: str, status: str = "TODO", milestone: str = "Milestone 3 (Sprint 3)"
) -> dict[str, Any]:
    return {
        "key": key,
        "status": status,
        "milestone": milestone,
        "description": "x",
        "owner": "Yassir",
    }


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("Set up OpenTelemetry-native Arize Phoenix & LangSmith tracing", "area:governance"),
        ("Bilingual French/English metadata mapping and data lineage tracking.", "area:governance"),
        ("User testing session with 3 external Canadian policy/data researchers", "area:research"),
        ("Add connector for Open Government Canada CKAN federal datasets.", "area:data"),
        ("Connector & FastMCP Server Hardening: Valet fixes", "area:data"),
        ("Containerize FastMCP server and LangGraph service; publish images to GHCR", "area:mcp"),
        ("Implement Supervisor agent node that decomposes complex queries", "area:agent"),
        ("Build modern Streamlit UI with astream_events", "area:agent"),
        ("Scaffold Next.js 15 App Router + Fumadocs in /apps/docs-portal", "docs"),
        ("Launch portfolio site showcasing team cards", None),
    ],
)
def test_area_label_is_inferred_from_the_task_description(
    description: str, expected: str | None
) -> None:
    assert infer_area_label(description) == expected


def test_milestone_sprint_is_read_from_the_milestone_title() -> None:
    assert milestone_sprint("Milestone 3: Interactive Docs (Sprint 3)") == "sprint 3"
    assert milestone_sprint("Milestone 0: Onboarding (Sprint  0)") == "sprint 0"
    assert milestone_sprint("General") is None


def test_only_tasks_of_the_active_sprint_join_the_current_cycle() -> None:
    cycle = {"id": "cyc-3", "name": "Sprint 3"}

    assert (
        cycle_id_for_task(_task("CAN-34", milestone="Milestone 3: Docs (Sprint 3)"), cycle)
        == "cyc-3"
    )
    assert (
        cycle_id_for_task(_task("CAN-61", milestone="Milestone 6: Showcase (Sprint 6)"), cycle)
        is None
    )
    assert cycle_id_for_task(_task("CAN-34", milestone="General"), cycle) is None
    assert cycle_id_for_task(_task("CAN-34"), None) is None


def test_every_task_is_listed_not_only_the_first_eight() -> None:
    tasks = [_task(f"CAN-{n}") for n in range(20, 40)]
    issues = [_issue(f"BEN-{n}", f"[CAN-{n}] task") for n in range(20, 40)]

    rows = summarize_linear_mirror(tasks, issues, TODAY)["rows"]

    assert [r["key"] for r in rows] == [t["key"] for t in tasks]
    assert all(r["linear_state"] == "Todo" for r in rows)


def test_a_follow_up_that_only_mentions_a_task_is_not_matched_to_it() -> None:
    tasks = [_task("CAN-22")]
    issues = [_issue("BEN-50", "[TECH-DEBT] Decorate the Supervisor node (CAN-22, CAN-24)")]

    (row,) = summarize_linear_mirror(tasks, issues, TODAY)["rows"]

    assert row["linear_state"] == "Not Created"


def test_columns_carry_priority_estimate_due_date_cycle_and_labels() -> None:
    issue = _issue(
        "BEN-25",
        "[CAN-34] CKAN",
        due="2026-11-04",
        priority=3,
        estimate=5,
        cycle="Sprint 3",
        labels=("area:data", "Feature"),
    )

    (row,) = summarize_linear_mirror([_task("CAN-34")], [issue], TODAY)["rows"]

    assert (row["priority"], row["estimate"], row["due"], row["cycle"]) == (
        "Medium",
        "5",
        "2026-11-04",
        "Sprint 3",
    )
    assert row["labels"] == ["area:data", "Feature"]


def test_status_mismatch_between_tasks_md_and_linear_is_flagged() -> None:
    tasks = [_task("CAN-24", "DONE"), _task("CAN-25", "IN REVIEW"), _task("CAN-31", "TODO")]
    issues = [
        _issue("BEN-19", "[CAN-24] verifier", "Done", "completed"),
        _issue("BEN-20", "[CAN-25] tracing", "In Progress", "started"),
        _issue("BEN-22", "[CAN-31] portal", "Backlog", "backlog"),  # Backlog reads as TODO
    ]

    summary = summarize_linear_mirror(tasks, issues, TODAY)

    assert [r["key"] for r in summary["mismatches"]] == ["CAN-25"]


def test_overdue_lists_open_issues_past_their_due_date_oldest_first() -> None:
    issues = [
        _issue("BEN-1", "[CAN-1] late", "In Progress", "started", due="2026-10-28"),
        _issue("BEN-2", "[CAN-2] later", "Todo", "unstarted", due="2026-10-27"),
        _issue("BEN-3", "[CAN-3] done late", "Done", "completed", due="2026-10-20"),
        _issue("BEN-4", "[CAN-4] due today", "Todo", "unstarted", due="2026-10-29"),
        _issue("BEN-5", "[CAN-5] no date", "Todo", "unstarted"),
    ]

    overdue = summarize_linear_mirror([], issues, TODAY)["overdue"]

    assert [i["identifier"] for i in overdue] == ["BEN-2", "BEN-1"]


def test_waiting_on_reviewer_and_open_issues_per_owner() -> None:
    issues = [
        _issue("BEN-16", "[CAN-21] state", "In Review", "started", assignee="Benjamin Sanchez"),
        _issue("BEN-20", "[CAN-25] tracing", "In Review", "started", assignee="Yassir Khougali"),
        _issue("BEN-17", "[CAN-22] supervisor", "Todo", "unstarted", assignee="samir omer"),
        _issue("BEN-19", "[CAN-24] verifier", "Done", "completed", assignee="samir omer"),
        _issue("BEN-60", "orphan", "Todo", "unstarted", assignee=None),
    ]

    summary = summarize_linear_mirror([], issues, TODAY)

    assert [i["identifier"] for i in summary["in_review"]] == ["BEN-16", "BEN-20"]
    assert summary["open_by_owner"] == {
        "Benjamin Sanchez": 1,
        "Yassir Khougali": 1,
        "samir omer": 1,
        "Unassigned": 1,
    }


def test_uploaded_issue_gets_its_area_label_and_the_current_cycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tasks = [
        _task("CAN-34", milestone="Milestone 3: Docs (Sprint 3)")
        | {
            "description": "Add connector for Open Government Canada CKAN federal datasets.",
            "owner": "Yassir Tagelsir Khougali",
        },
        _task("CAN-61", milestone="Milestone 6: Showcase (Sprint 6)")
        | {
            "description": "Launch portfolio site",
            "owner": "Benjamin Sanchez Zebadua",
        },
    ]
    created: list[dict[str, Any]] = []

    def fake_query(query: str, variables: dict[str, Any] | None = None, api_key: str | None = None):
        if "issueCreate" in query and variables:
            created.append(variables["input"])
            return {
                "issueCreate": {
                    "success": True,
                    "issue": {"id": "i", "identifier": "BEN-99", "url": ""},
                }
            }
        return None

    team = {"id": "team-1", "name": "Team", "key": "BEN"}
    monkeypatch.setattr(sync_tasks, "parse_tasks_md", lambda: {"tasks": tasks, "milestones": []})
    monkeypatch.setattr(
        sync_tasks, "get_linear_context", lambda api_key=None: {"projects": {"nodes": []}}
    )
    monkeypatch.setattr(
        sync_tasks,
        "find_team_and_states",
        lambda ctx, preferred_key="CAN": (team, {"todo": "s1"}, {"yassir": "u1"}),
    )
    monkeypatch.setattr(sync_tasks, "fetch_all_linear_issues", lambda team_id, api_key=None: [])
    monkeypatch.setattr(
        sync_tasks,
        "fetch_team_labels_and_active_cycle",
        lambda team_id, api_key=None: (
            {"area:data": "lbl-data"},
            {"id": "cyc-3", "name": "Sprint 3"},
        ),
    )
    monkeypatch.setattr(sync_tasks, "ensure_linear_project", lambda *a, **k: "proj-1")
    monkeypatch.setattr(sync_tasks, "query_linear_api", fake_query)

    sync_tasks.upload_all_tasks_to_linear(api_key="lin_api_test")

    sprint3, sprint6 = created
    assert sprint3["labelIds"] == ["lbl-data"]
    assert sprint3["cycleId"] == "cyc-3"
    assert "labelIds" not in sprint6  # no matching area label
    assert "cycleId" not in sprint6  # Sprint 6 is not the active cycle
