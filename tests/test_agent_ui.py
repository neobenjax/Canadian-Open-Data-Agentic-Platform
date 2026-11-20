"""Tests for Streamlit UI environment loading and live/demo mode status (Issue #91).

Verifies that:
- .env is loaded safely without overriding existing environment variables.
- live_planner_available() correctly detects keys from .env or session.
- App startup loads .env from file (via _load_env) and activates live mode in the UI.
- The UI sidebar accurately informs the user whether live mode is active via session or .env.
- API key values are never exposed or rendered in UI elements.
- Tests isolate environment state without leaking keys into the session.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Any
from unittest.mock import patch

from dotenv import load_dotenv
from streamlit.testing.v1 import AppTest

from candata_agent.ui.session import live_planner_available

APP_PATH = Path(__file__).resolve().parents[1] / "apps" / "agent-ui" / "app.py"


def _load_app_module() -> Any:
    spec = importlib.util.spec_from_file_location("agent_ui_app", APP_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load spec from {APP_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_dotenv_populates_key_when_unset_and_activates_live_planner(tmp_path: Path) -> None:
    """When ANTHROPIC_API_KEY is not in os.environ, loading .env populates it."""
    env_file = tmp_path / ".env"
    env_file.write_text("ANTHROPIC_API_KEY=test-saved-key\n", encoding="utf-8")

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("ANTHROPIC_API_KEY", None)
        assert not live_planner_available()

        loaded = load_dotenv(env_file, override=False)
        assert loaded is True
        assert os.environ.get("ANTHROPIC_API_KEY") == "test-saved-key"
        assert live_planner_available() is True

    # Assert no environment leakage outside context
    assert os.environ.get("ANTHROPIC_API_KEY") != "test-saved-key"


def test_exported_env_var_not_overridden_by_dotenv(tmp_path: Path) -> None:
    """Explicitly exported environment variables must not be overridden (override=False)."""
    env_file = tmp_path / ".env"
    env_file.write_text("ANTHROPIC_API_KEY=file-override-attempt\n", encoding="utf-8")

    with patch.dict(os.environ, {}, clear=False):
        os.environ["ANTHROPIC_API_KEY"] = "already-exported-key"
        assert live_planner_available() is True

        load_dotenv(env_file, override=False)
        assert os.environ.get("ANTHROPIC_API_KEY") == "already-exported-key"
        assert live_planner_available() is True


def test_app_loads_env_file_on_startup_and_enables_live_mode(tmp_path: Path) -> None:
    """Running app.py with a real .env file activates live mode and labels the source."""
    env_file = tmp_path / ".env"
    env_file.write_text("ANTHROPIC_API_KEY=test-app-loaded-key\n", encoding="utf-8")

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("ANTHROPIC_API_KEY", None)
        os.environ["CANDATA_ENV_FILE"] = str(env_file)

        at = AppTest.from_file(str(APP_PATH), default_timeout=60).run()
        assert not at.exception
        assert os.environ.get("ANTHROPIC_API_KEY") == "test-app-loaded-key"

        success_texts = [s.value for s in at.success]
        assert any("Live mode" in t and "Active (.env / environment)" in t for t in success_texts)
        # Ensure secret is never rendered
        all_text = (
            " ".join(m.value for m in at.markdown) + " " + " ".join(s.value for s in at.success)
        )
        assert "test-app-loaded-key" not in all_text


def test_app_startup_preserves_exported_env_over_env_file(tmp_path: Path) -> None:
    """App startup does not override an already-exported ANTHROPIC_API_KEY."""
    env_file = tmp_path / ".env"
    env_file.write_text("ANTHROPIC_API_KEY=file-key\n", encoding="utf-8")

    with patch.dict(os.environ, {}, clear=False):
        os.environ["ANTHROPIC_API_KEY"] = "exported-primary-key"
        os.environ["CANDATA_ENV_FILE"] = str(env_file)

        at = AppTest.from_file(str(APP_PATH), default_timeout=60).run()
        assert not at.exception
        assert os.environ.get("ANTHROPIC_API_KEY") == "exported-primary-key"


def test_live_planner_without_keys_returns_false() -> None:
    """Without session key or environment key, live_planner_available returns False."""
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("ANTHROPIC_API_KEY", None)
        assert live_planner_available() is False
        assert live_planner_available(None) is False
        assert live_planner_available("") is False


def test_live_planner_with_session_key() -> None:
    """Session-provided key enables live planner regardless of os.environ."""
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("ANTHROPIC_API_KEY", None)
        assert live_planner_available("session-secret-key") is True


def test_ui_sidebar_demo_mode_when_no_key(tmp_path: Path) -> None:
    """When no key is configured, UI displays demo mode info banner."""
    empty_env = tmp_path / ".empty.env"
    empty_env.write_text("", encoding="utf-8")

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("ANTHROPIC_API_KEY", None)
        os.environ["CANDATA_ENV_FILE"] = str(empty_env)

        at = AppTest.from_file(str(APP_PATH), default_timeout=60).run()

    assert not at.exception
    info_texts = [info.value for info in at.info]
    assert any(
        "Demo mode" in t and "No `ANTHROPIC_API_KEY` detected in `.env` or session" in t
        for t in info_texts
    )


def test_ui_sidebar_live_mode_from_session(tmp_path: Path) -> None:
    """When user inputs session key, sidebar displays 'session' as the active source."""
    empty_env = tmp_path / ".empty.env"
    empty_env.write_text("", encoding="utf-8")

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("ANTHROPIC_API_KEY", None)
        os.environ["CANDATA_ENV_FILE"] = str(empty_env)

        at = AppTest.from_file(str(APP_PATH), default_timeout=60)
        at.session_state["custom_api_key"] = "session-custom-key"
        at.run()

    assert not at.exception
    success_texts = [s.value for s in at.success]
    assert any("Live mode" in t and "Active (session)" in t for t in success_texts)
    all_text = " ".join(m.value for m in at.markdown) + " " + " ".join(s.value for s in at.success)
    assert "session-custom-key" not in all_text


def test_load_env_graceful_when_dotenv_is_none(tmp_path: Path) -> None:
    """_load_env executes without error if python-dotenv is not installed (load_dotenv is None)."""
    app_mod = _load_app_module()
    app_mod.load_dotenv = None
    # Should execute safely without throwing
    app_mod._load_env(tmp_path / ".nonexistent.env")
