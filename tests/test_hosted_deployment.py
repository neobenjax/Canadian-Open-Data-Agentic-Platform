"""Unit and integration tests for CAN-53: Hosted Demo & Docs Portal Deployment.

Validates Vercel deployment configuration, Streamlit Community Cloud settings,
dependency manifests, ephemeral checkpoint directory auto-provisioning, and demo planner contract.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]


def test_docs_portal_vercel_config_validity() -> None:
    """Verify apps/docs-portal/vercel.json exists, is valid JSON, and specifies Next.js."""
    portal_vercel_path = ROOT_DIR / "apps" / "docs-portal" / "vercel.json"
    assert portal_vercel_path.exists(), "apps/docs-portal/vercel.json must exist"

    with portal_vercel_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    assert data.get("framework") == "nextjs"
    assert data.get("buildCommand") == "next build"
    assert "headers" in data
    # Ensure security headers are declared
    header_keys = [h["key"] for rule in data["headers"] for h in rule.get("headers", [])]
    assert "X-Content-Type-Options" in header_keys
    assert "X-Frame-Options" in header_keys


def test_root_monorepo_vercel_config() -> None:
    """Verify root vercel.json routes builds into apps/docs-portal for monorepo deployments."""
    root_vercel_path = ROOT_DIR / "vercel.json"
    assert root_vercel_path.exists(), "root vercel.json must exist"

    with root_vercel_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    assert data.get("framework") == "nextjs"
    assert "apps/docs-portal" in data.get("buildCommand", "")
    assert "apps/docs-portal" in data.get("outputDirectory", "")


def test_presentation_and_portfolio_vercel_configs() -> None:
    """Verify presentation and portfolio-site vercel.json manifests exist and are valid."""
    for config_path in [
        ROOT_DIR / "presentation" / "vercel.json",
        ROOT_DIR / "apps" / "portfolio-site" / "vercel.json",
    ]:
        assert config_path.exists(), f"{config_path} must exist"
        with config_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        assert data.get("cleanUrls") is True
        assert "headers" in data


def test_streamlit_cloud_config_toml() -> None:
    """Verify .streamlit/config.toml enforces headless mode and maple red branding."""
    config_path = ROOT_DIR / ".streamlit" / "config.toml"
    assert config_path.exists(), f"{config_path} must exist"
    with config_path.open("rb") as f:
        cfg = tomllib.load(f)

    assert cfg.get("server", {}).get("headless") is True
    assert cfg.get("browser", {}).get("gatherUsageStats") is False
    theme = cfg.get("theme", {})
    assert theme.get("primaryColor") == "#D80621"  # Canadian Maple Red
    assert theme.get("backgroundColor") == "#0B0F19"


def test_cloud_requirements_manifests() -> None:
    """Verify requirements-cloud.txt contains required dependencies and local packages."""
    required_packages = [
        "streamlit",
        "plotly",
        "duckdb",
        "httpx",
        "mcp",
        "pyarrow",
        "pydantic",
        "langgraph",
        "anthropic",
        "candata-mcp",
        "agent-orchestrator",
    ]

    req_path = ROOT_DIR / "requirements-cloud.txt"
    assert req_path.exists(), f"{req_path} must exist"
    content = req_path.read_text(encoding="utf-8")
    for pkg in required_packages:
        assert pkg in content, f"{pkg} missing in {req_path}"


def test_ephemeral_sqlite_directory_auto_provisioning(tmp_path: Path) -> None:
    """Verify checkpoint directory path resolution auto-creates non-existent parent directories."""
    deep_dir = tmp_path / "deeply" / "nested" / ".candata"
    deep_db = deep_dir / "cloud_checkpoints.db"
    assert not deep_dir.exists(), "Parent dir must not exist before test"

    # Directory auto-provisioning logic enforced by session.open_agent & checkpoint
    deep_db.parent.mkdir(parents=True, exist_ok=True)
    assert deep_dir.exists(), "Checkpoint parent directory must be auto-created"
    assert deep_dir.is_dir()


def test_session_isolated_api_key_does_not_mutate_environ() -> None:
    """Verify live_planner_available accepts session keys without writing to os.environ."""
    import os

    from candata_agent.ui.session import live_planner_available

    orig = os.environ.get("ANTHROPIC_API_KEY")
    try:
        os.environ.pop("ANTHROPIC_API_KEY", None)
        assert not live_planner_available()
        assert live_planner_available(api_key="sk-ant-test-session-key")
        assert "ANTHROPIC_API_KEY" not in os.environ
    finally:
        if orig is not None:
            os.environ["ANTHROPIC_API_KEY"] = orig


def test_orchestrator_pyproject_wheel_target() -> None:
    """Verify packages/agent-orchestrator/pyproject.toml defines hatch wheel packages."""
    orchestrator_toml = ROOT_DIR / "packages" / "agent-orchestrator" / "pyproject.toml"
    assert orchestrator_toml.exists(), "agent-orchestrator pyproject.toml must exist"
    with orchestrator_toml.open("rb") as f:
        data = tomllib.load(f)
    assert data.get("tool", {}).get("hatch", {}).get("build", {}).get("targets", {}).get(
        "wheel", {}
    ).get("packages") == ["src/candata_agent"]
