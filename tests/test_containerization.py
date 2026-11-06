"""Unit tests for CAN-45 Containerization & Docker Security Hardening.

Verifies Dockerfiles, docker-compose.yml, and GHCR publishing configuration.
"""

import os
import re

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_dockerignore_structure():
    """Verify .dockerignore excludes sensitive paths."""
    dockerignore_path = os.path.join(ROOT_DIR, ".dockerignore")
    assert os.path.exists(dockerignore_path), ".dockerignore must exist"
    with open(dockerignore_path, encoding="utf-8") as f:
        content = f.read()

    assert ".git" in content
    assert ".venv/" in content
    assert ".env" in content
    assert ".pytest_cache/" in content


def test_fastmcp_dockerfile_security():
    """Verify Dockerfile.fastmcp enforces multi-stage build, non-root user, and healthcheck."""
    dockerfile_path = os.path.join(ROOT_DIR, "docker", "Dockerfile.fastmcp")
    assert os.path.exists(dockerfile_path), "docker/Dockerfile.fastmcp must exist"
    with open(dockerfile_path, encoding="utf-8") as f:
        content = f.read()

    # Multi-stage check
    assert "AS builder" in content
    assert "AS runtime" in content

    # Non-root UID/GID 10001 check
    assert "10001" in content
    assert re.search(r"USER\s+10001:10001", content) is not None

    # Hardening flags
    assert "PYTHONUNBUFFERED=1" in content
    assert "PYTHONDONTWRITEBYTECODE=1" in content

    # Healthcheck check
    assert "HEALTHCHECK" in content
    assert "candata_mcp.server" in content


def test_orchestrator_dockerfile_security():
    """Verify Dockerfile.orchestrator enforces non-root user, SQLite volume, and healthcheck."""
    dockerfile_path = os.path.join(ROOT_DIR, "docker", "Dockerfile.orchestrator")
    assert os.path.exists(dockerfile_path), "docker/Dockerfile.orchestrator must exist"
    with open(dockerfile_path, encoding="utf-8") as f:
        content = f.read()

    # Multi-stage check
    assert "AS builder" in content
    assert "AS runtime" in content

    # Non-root user check
    assert re.search(r"USER\s+10001:10001", content) is not None

    # Persistent volume for checkpoints
    assert 'VOLUME ["/app/.candata"]' in content or "VOLUME" in content

    # Streamlit port and healthcheck
    assert "8501" in content
    assert "HEALTHCHECK" in content


def test_docker_compose_security_hardening():
    """Verify docker-compose.yml defines services with defense-in-depth hardening."""
    compose_path = os.path.join(ROOT_DIR, "docker-compose.yml")
    assert os.path.exists(compose_path), "docker-compose.yml must exist"
    with open(compose_path, encoding="utf-8") as f:
        content = f.read()

    # Both services must be defined
    assert "candata-mcp:" in content
    assert "candata-orchestrator:" in content

    # Security options
    assert 'user: "10001:10001"' in content
    assert "no-new-privileges:true" in content
    assert "ALL" in content  # cap_drop
    assert "/tmp:rw,noexec,nosuid" in content
    assert "read_only: true" in content

    # Resource constraints
    assert "cpus:" in content
    assert "memory:" in content


def test_ghcr_workflow_configuration():
    """Verify .github/workflows/docker-publish.yml exists and targets GHCR."""
    wf_path = os.path.join(ROOT_DIR, ".github", "workflows", "docker-publish.yml")
    assert os.path.exists(wf_path), "docker-publish.yml workflow must exist"
    with open(wf_path, encoding="utf-8") as f:
        content = f.read()

    assert "ghcr.io" in content
    assert "candata-mcp" in content
    assert "candata-orchestrator" in content
    assert "packages: write" in content
