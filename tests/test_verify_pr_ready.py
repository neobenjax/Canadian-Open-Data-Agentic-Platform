"""Unit tests for the Pre-PR & Pre-Push Task Verification module (scripts/verify_pr_ready.py)."""

from pathlib import Path
from unittest.mock import patch

from scripts.verify_pr_ready import (
    extract_task_key,
    install_pre_push_hook,
    is_task_checked_in_tasks_md,
    mark_task_checked_in_tasks_md,
    should_verify_branch,
    verify_pr_ready,
)

SAMPLE_TASKS_MD = """# Project Task Board

## Milestone 1: FastMCP 2.0 Core
- [x] **CAN-11:** Implement async HTTPX client for Statistics Canada WDS API.
- [ ] **CAN-15:** Run baseline benchmark comparing frontier LLMs without tools.
- [x] **CAN-16:** Conduct API security, rate limit audit.

## Milestone 2: Multi-Agent Orchestration
- [ ] **CAN-17:** Connector & FastMCP Server Hardening.
- [x] **CAN-26:** Bilingual French/English metadata mapping.
"""


def test_extract_task_key():
    assert extract_task_key("feat/CAN-08-onboarding-wizard") == "CAN-08"
    assert extract_task_key("feat/can-17-fastmcp-hardening") == "CAN-17"
    assert extract_task_key("CAN-26") == "CAN-26"
    assert extract_task_key("can-15") == "CAN-15"
    assert extract_task_key("main") is None
    assert extract_task_key("chore/workflow-tasks-pr-enforcement") is None
    assert extract_task_key("docs/setup-guide") is None


def test_should_verify_branch():
    # Feature task branches must be verified
    assert should_verify_branch("feat/CAN-08-onboarding") is True
    assert should_verify_branch("feat/CAN-17-hardening") is True

    # Non-task branches and standard system branches must bypass verification
    assert should_verify_branch("main") is False
    assert should_verify_branch("master") is False
    assert should_verify_branch("chore/workflow-tasks-pr-enforcement") is False
    assert should_verify_branch("docs/readme-update") is False
    assert should_verify_branch("fix/minor-typo") is False
    assert should_verify_branch("hotfix/security-patch") is False


def test_is_task_checked_in_tasks_md(tmp_path: Path):
    tasks_file = tmp_path / "TASKS.md"
    tasks_file.write_text(SAMPLE_TASKS_MD, encoding="utf-8")

    # CAN-11 and CAN-26 are checked
    checked, line = is_task_checked_in_tasks_md("CAN-11", filepath=str(tasks_file))
    assert checked is True
    assert line is not None
    assert "CAN-11" in line

    checked, line = is_task_checked_in_tasks_md("CAN-26", filepath=str(tasks_file))
    assert checked is True

    # CAN-15 and CAN-17 are unchecked
    checked, line = is_task_checked_in_tasks_md("CAN-15", filepath=str(tasks_file))
    assert checked is False
    assert line is not None
    assert "CAN-15" in line

    # Non-existent task
    checked, line = is_task_checked_in_tasks_md("CAN-99", filepath=str(tasks_file))
    assert checked is False
    assert line is None


def test_mark_task_checked_in_tasks_md(tmp_path: Path):
    tasks_file = tmp_path / "TASKS.md"
    tasks_file.write_text(SAMPLE_TASKS_MD, encoding="utf-8")

    # Before fix
    checked_before, _ = is_task_checked_in_tasks_md("CAN-17", filepath=str(tasks_file))
    assert checked_before is False

    # Apply auto-check
    success = mark_task_checked_in_tasks_md("CAN-17", filepath=str(tasks_file))
    assert success is True

    # After fix
    checked_after, line = is_task_checked_in_tasks_md("CAN-17", filepath=str(tasks_file))
    assert checked_after is True
    assert line is not None
    assert "- [x] **CAN-17:**" in line


def test_verify_pr_ready_checked_task(tmp_path: Path):
    tasks_file = tmp_path / "TASKS.md"
    tasks_file.write_text(SAMPLE_TASKS_MD, encoding="utf-8")

    with patch("scripts.verify_pr_ready.TASKS_FILE", str(tasks_file)):
        # Checked task passes with exit code 0
        code = verify_pr_ready(task_key="CAN-26", branch="feat/CAN-26-bilingual", quiet=True)
        assert code == 0


def test_verify_pr_ready_unchecked_task(tmp_path: Path):
    tasks_file = tmp_path / "TASKS.md"
    tasks_file.write_text(SAMPLE_TASKS_MD, encoding="utf-8")

    with patch("scripts.verify_pr_ready.TASKS_FILE", str(tasks_file)):
        # Unchecked task fails with exit code 1
        code = verify_pr_ready(task_key="CAN-15", branch="feat/CAN-15-benchmarks", quiet=True)
        assert code == 1

        # With auto_fix=True, it updates TASKS.md and returns 0
        fix_code = verify_pr_ready(
            task_key="CAN-15",
            branch="feat/CAN-15-benchmarks",
            auto_fix=True,
            quiet=True,
        )
        assert fix_code == 0

        # Verify it is now checked in the file
        checked, _ = is_task_checked_in_tasks_md("CAN-15", filepath=str(tasks_file))
        assert checked is True


def test_verify_pr_ready_bypass_branch(tmp_path: Path):
    tasks_file = tmp_path / "TASKS.md"
    tasks_file.write_text(SAMPLE_TASKS_MD, encoding="utf-8")

    with patch("scripts.verify_pr_ready.TASKS_FILE", str(tasks_file)):
        # Non-task branch passes automatically with code 0
        code = verify_pr_ready(branch="chore/workflow-tasks-pr-enforcement", quiet=True)
        assert code == 0

        code_main = verify_pr_ready(branch="main", quiet=True)
        assert code_main == 0


def test_install_pre_push_hook(tmp_path: Path):
    fake_hook = tmp_path / "pre-push"
    fake_hooks_dir = tmp_path

    with (
        patch("scripts.verify_pr_ready.HOOKS_DIR", str(fake_hooks_dir)),
        patch("scripts.verify_pr_ready.PRE_PUSH_HOOK", str(fake_hook)),
    ):
        success = install_pre_push_hook(target_file=str(fake_hook))
        assert success is True
        assert fake_hook.exists()
        content = fake_hook.read_text(encoding="utf-8")
        assert "verify_pr_ready.py" in content
        assert "CanData-MCP Pre-Push Hook" in content
