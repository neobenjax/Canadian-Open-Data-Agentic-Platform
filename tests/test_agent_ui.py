"""Tests for Streamlit UI environment loading and live/demo mode status (Issue #91).

Verifies that:
- .env is loaded safely without overriding existing environment variables.
- live_planner_available() correctly detects keys from .env or session.
- The UI sidebar accurately informs the user whether live mode is active via session or .env.
- API key values are never exposed or rendered in UI elements.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from dotenv import load_dotenv
from streamlit.testing.v1 import AppTest

from candata_agent.ui.session import live_planner_available

APP_PATH = Path(__file__).resolve().parents[1] / "apps" / "agent-ui" / "app.py"


def test_dotenv_populates_key_when_unset_and_activates_live_planner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When ANTHROPIC_API_KEY is not in os.environ, loading .env populates it."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert not live_planner_available()

    env_file = tmp_path / ".env"
    env_file.write_text("ANTHROPIC_API_KEY=test-saved-key\n", encoding="utf-8")

    loaded = load_dotenv(env_file, override=False)
    assert loaded is True
    assert os.environ.get("ANTHROPIC_API_KEY") == "test-saved-key"
    assert live_planner_available() is True


def test_exported_env_var_not_overridden_by_dotenv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Explicitly exported environment variables must not be overridden (override=False)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "already-exported-key")
    assert live_planner_available() is True

    env_file = tmp_path / ".env"
    env_file.write_text("ANTHROPIC_API_KEY=file-override-attempt\n", encoding="utf-8")

    load_dotenv(env_file, override=False)
    assert os.environ.get("ANTHROPIC_API_KEY") == "already-exported-key"
    assert live_planner_available() is True


def test_live_planner_without_keys_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without session key or environment key, live_planner_available returns False."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert live_planner_available() is False
    assert live_planner_available(None) is False
    assert live_planner_available("") is False


def test_live_planner_with_session_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Session-provided key enables live planner regardless of os.environ."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert live_planner_available("session-secret-key") is True


def test_ui_sidebar_demo_mode_when_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """When no key is configured, UI displays demo mode info banner."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    # Patch load_dotenv in app to prevent reading local developer .env during test
    with patch("dotenv.load_dotenv"):
        at = AppTest.from_file(str(APP_PATH), default_timeout=60).run()

    assert not at.exception
    info_texts = [info.value for info in at.info]
    assert any(
        "Demo mode" in t and "No `ANTHROPIC_API_KEY` detected in `.env` or session" in t
        for t in info_texts
    )


def test_ui_sidebar_live_mode_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """When ANTHROPIC_API_KEY is present in environment, sidebar shows .env / environment source."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-env-key")

    with patch("dotenv.load_dotenv"):
        at = AppTest.from_file(str(APP_PATH), default_timeout=60).run()

    assert not at.exception
    success_texts = [s.value for s in at.success]
    assert any("Live mode" in t and "Active (.env / environment)" in t for t in success_texts)
    # Ensure key secret is never rendered
    all_text = " ".join(m.value for m in at.markdown) + " " + " ".join(s.value for s in at.success)
    assert "test-env-key" not in all_text


def test_ui_sidebar_live_mode_from_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """When user inputs session key, sidebar displays 'session' as the active source."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with patch("dotenv.load_dotenv"):
        at = AppTest.from_file(str(APP_PATH), default_timeout=60)
        at.session_state["custom_api_key"] = "session-custom-key"
        at.run()

    assert not at.exception
    success_texts = [s.value for s in at.success]
    assert any("Live mode" in t and "Active (session)" in t for t in success_texts)
    all_text = " ".join(m.value for m in at.markdown) + " " + " ".join(s.value for s in at.success)
    assert "session-custom-key" not in all_text
