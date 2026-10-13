"""Unit test suite for scripts/verify_branch_protection.py."""

from unittest.mock import patch

from scripts.verify_branch_protection import (
    TRIANGULAR_REVIEW_MAP,
    check_branch_protection,
    check_triangular_prs,
    load_dotenv,
)


def test_load_dotenv_parses_content(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("GITHUB_TOKEN=ghp_test123\n# A comment\nCUSTOM_VAR=value_test\n", encoding="utf-8")
    loaded = load_dotenv(str(env_file))
    assert loaded.get("GITHUB_TOKEN") == "ghp_test123"
    assert loaded.get("CUSTOM_VAR") == "value_test"


def test_load_dotenv_non_existent():
    loaded = load_dotenv("non_existent_file.env")
    assert loaded == {}


@patch("scripts.verify_branch_protection.github_api_get")
def test_check_branch_protection_success(mock_api_get):
    mock_payload = {
        "required_pull_request_reviews": {"required_approving_review_count": 1},
        "enforce_admins": {"enabled": True},
        "allow_force_pushes": {"enabled": False},
        "allow_deletions": {"enabled": False},
    }
    mock_api_get.return_value = (200, mock_payload)

    res = check_branch_protection("test/repo", branch="main")
    assert res["passed"] is True
    assert res["checks"]["min_1_approval"]["passed"] is True
    assert res["checks"]["enforce_admins"]["passed"] is True
    assert res["checks"]["block_force_push"]["passed"] is True
    assert res["checks"]["block_deletion"]["passed"] is True


@patch("scripts.verify_branch_protection.github_api_get")
def test_check_branch_protection_fails_without_admin_enforcement(mock_api_get):
    mock_payload = {
        "required_pull_request_reviews": {"required_approving_review_count": 1},
        "enforce_admins": {"enabled": False},
        "allow_force_pushes": {"enabled": False},
        "allow_deletions": {"enabled": False},
    }
    mock_api_get.return_value = (200, mock_payload)

    res = check_branch_protection("test/repo", branch="main")
    assert res["passed"] is False
    assert res["checks"]["enforce_admins"]["passed"] is False


@patch("scripts.verify_branch_protection.github_api_get")
def test_check_branch_protection_handles_api_error(mock_api_get):
    mock_api_get.return_value = (404, {"message": "Branch not protected"})

    res = check_branch_protection("test/repo", branch="main")
    assert res["passed"] is False
    assert res["protected"] is False
    assert "Branch not protected" in res["errors"][0]


@patch("scripts.verify_branch_protection.github_api_get")
def test_check_triangular_prs_compliant(mock_api_get):
    mock_prs = [
        {
            "number": 10,
            "title": "Feature 1",
            "user": {"login": "neobenjax"},
            "head": {"ref": "feat/CAN-01"},
            "html_url": "https://github.com/test/pull/10",
            "requested_reviewers": [{"login": "samiromer2"}],
        }
    ]

    def side_effect(endpoint, token=None):
        if "pulls?state=open" in endpoint:
            return 200, mock_prs
        if "pulls/10/reviews" in endpoint:
            return 200, []
        return 404, {}

    mock_api_get.side_effect = side_effect

    res = check_triangular_prs("test/repo")
    assert res["open_prs_count"] == 1
    assert res["all_compliant"] is True
    assert res["prs"][0]["compliant"] is True
    assert res["prs"][0]["expected_reviewer"] == "samiromer2"


@patch("scripts.verify_branch_protection.github_api_get")
def test_check_triangular_prs_non_compliant(mock_api_get):
    mock_prs = [
        {
            "number": 11,
            "title": "Feature 2",
            "user": {"login": "neobenjax"},
            "head": {"ref": "feat/CAN-02"},
            "html_url": "https://github.com/test/pull/11",
            "requested_reviewers": [{"login": "random_user"}],
        }
    ]

    def side_effect(endpoint, token=None):
        if "pulls?state=open" in endpoint:
            return 200, mock_prs
        if "pulls/11/reviews" in endpoint:
            return 200, []
        return 404, {}

    mock_api_get.side_effect = side_effect

    res = check_triangular_prs("test/repo")
    assert res["open_prs_count"] == 1
    assert res["all_compliant"] is False
    assert res["prs"][0]["compliant"] is False


def test_triangular_map_integrity():
    assert TRIANGULAR_REVIEW_MAP["neobenjax"] == "samiromer2"
    assert TRIANGULAR_REVIEW_MAP["samiromer2"] == "yassirtmk"
    assert TRIANGULAR_REVIEW_MAP["yassirtmk"] == "neobenjax"
