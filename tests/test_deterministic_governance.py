"""Unit tests for Deterministic Governance modules.

Tests pr_triage.py, validate_commit_msg.py, and governance_config.py.
"""

import pytest

from scripts.governance_config import (
    get_area_label,
    get_commit_pattern,
    get_linear_team_prefix,
    get_milestone_number,
    get_repo_name,
    get_task_prefix,
    get_triangular_reviewer,
    load_governance_config,
)
from scripts.pr_triage import (
    build_dual_closing_lines,
    extract_task_key,
    resolve_milestone_and_labels,
    resolve_triangular_reviewer,
)
from scripts.validate_commit_msg import validate_commit_message


def test_validate_commit_message_valid():
    valid_samples = [
        "[CAN-17] feat: implement fastmcp discovery tools",
        "[CAN-08] chore: add automated onboarding wizard",
        "[CAN-26] docs: document bilingual translation",
        "[TECH-DEBT] refactor: optimize duckdb arrow stream",
        "docs: update developer setup guide",
        "chore: bump dependencies",
        "fix(connectors): handle valet 404 response",
    ]
    for msg in valid_samples:
        valid, err = validate_commit_message(msg)
        assert valid is True, f"Expected '{msg}' to be valid, got error: {err}"


def test_validate_commit_message_invalid():
    invalid_samples = [
        ("", "Empty commit message"),
        ("fixed bugs", "does not follow Conventional Commits"),
        ("WIP: working on stuff", "does not follow Conventional Commits"),
        ("random commit message", "does not follow Conventional Commits"),
    ]
    for msg, _ in invalid_samples:
        valid, err = validate_commit_message(msg)
        assert valid is False, f"Expected '{msg}' to be invalid"


def test_validate_commit_message_procedural_keywords_rejected():
    procedural_samples = [
        "[CAN-17] fix: address review comments",
        "[CAN-08] chore: updates per review",
        "docs: fix review feedback",
        "refactor: pr feedback changes",
    ]
    for msg in procedural_samples:
        valid, err = validate_commit_message(msg)
        assert valid is False
        assert "procedural" in (err or "").lower()


def test_triangular_reviewer_resolution():
    assert resolve_triangular_reviewer("neobenjax") == "samiromer2"
    assert resolve_triangular_reviewer("samiromer2") == "yassirtmk"
    assert resolve_triangular_reviewer("yassirtmk") == "neobenjax"
    assert resolve_triangular_reviewer("@neobenjax") == "samiromer2"
    assert resolve_triangular_reviewer("unknown_user") is None


def test_milestone_and_labels_resolution():
    milestone, labels = resolve_milestone_and_labels(
        task_key="CAN-17",
        branch="feat/CAN-17-fastmcp-engine",
        title="[CAN-17] feat: fastmcp engine slicing",
    )
    assert milestone == 3  # Milestone 2 is GitHub milestone #3
    assert "milestone:m2" in labels
    assert "type:feat" in labels
    assert "area:fastmcp-engine" in labels

    # Test Milestone 1 task
    m1, labels1 = resolve_milestone_and_labels(
        task_key="CAN-11",
        branch="feat/CAN-11-statcan-wds",
        title="[CAN-11] feat: statcan wds connector",
    )
    assert m1 == 2  # Milestone 1 is GitHub milestone #2
    assert "milestone:m1" in labels1
    assert "area:connectors" in labels1


def test_build_dual_closing_lines():
    lines = build_dual_closing_lines("CAN-17", current_body="")
    assert "Closes BEN-45" in lines
    assert "Closes CAN-17" in lines

    lines_c08 = build_dual_closing_lines("CAN-08", current_body="")
    assert "Closes BEN-42" in lines_c08
    assert "Closes CAN-08" in lines_c08


def test_extract_task_key():
    assert extract_task_key("feat/CAN-17-fastmcp-engine") == "CAN-17"
    assert extract_task_key("feat/CAN-08-wizard") == "CAN-08"
    assert extract_task_key("[CAN-26] chore: clean logs") == "CAN-26"
    assert extract_task_key("chore: general maintenance") is None


def test_governance_config_portability():
    """Verify that governance rules can be completely customized via configuration."""
    custom_config = {
        "project": {
            "name": "US-Open-Data-Platform",
            "repo": "us-data/US-Open-Data-Platform",
            "task_prefix": "USDATA",
            "linear_team_prefix": "USD",
        },
        "reviewers": {
            "triangular_matrix": {
                "alice": "bob",
                "bob": "carol",
                "carol": "alice",
            }
        },
        "milestones": {
            "ranges": [
                {"index": 0, "name": "Sprint A", "task_ids": [10, 20]},
                {"index": 1, "name": "Sprint B", "task_ids": [30, 40]},
            ]
        },
        "labels": {
            "area_keywords": {
                "area:census": ["census", "population"],
                "area:fed": ["rates", "inflation"],
            },
            "default_area": "area:core",
        },
        "commit_linter": {
            "allowed_types": ["feat", "fix", "chore"],
            "allowed_prefixes": ["USDATA", "TECH-DEBT"],
        },
    }

    # Verify custom getters
    assert get_repo_name(custom_config) == "us-data/US-Open-Data-Platform"
    assert get_task_prefix(custom_config) == "USDATA"
    assert get_linear_team_prefix(custom_config) == "USD"

    # Reviewer matrix
    assert get_triangular_reviewer("alice", custom_config) == "bob"
    assert get_triangular_reviewer("bob", custom_config) == "carol"
    assert get_triangular_reviewer("carol", custom_config) == "alice"

    # Milestones
    assert get_milestone_number("USDATA-10", custom_config) == 1
    assert get_milestone_number("USDATA-30", custom_config) == 2

    # Area keywords
    assert get_area_label("census data analysis", custom_config) == "area:census"
    assert get_area_label("fed rates update", custom_config) == "area:fed"
    assert get_area_label("unrelated text", custom_config) == "area:core"

    # Commit pattern regex with custom prefix
    custom_pattern = get_commit_pattern(custom_config)
    assert custom_pattern.match("[USDATA-10] feat: add census data") is not None
    assert custom_pattern.match("[CAN-10] feat: add census data") is None  # Rejects CAN


def test_load_governance_config_file_io():
    """Verify loading from real governance.json and error on missing file."""
    # Load actual repository governance.json
    cfg = load_governance_config(reload=True)
    assert cfg["project"]["task_prefix"] == "CAN"
    assert cfg["project"]["linear_team_prefix"] == "BEN"
    assert cfg["reviewers"]["triangular_matrix"]["neobenjax"] == "samiromer2"

    # Fail loud if file is missing
    with pytest.raises(FileNotFoundError, match="Governance configuration file not found"):
        load_governance_config(filepath="non_existent_governance.json")
