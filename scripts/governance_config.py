#!/usr/bin/env python3
"""
Canadian Open Data Agentic Platform — Centralized Governance Configuration
---------------------------------------------------------------------------
Loads and exposes project governance invariants from `governance.json`.
Allows exporting the governance and triage engine to other repositories
without modifying any underlying Python script.
"""

import json
import os
import re
from typing import Any

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOVERNANCE_CONFIG_FILE = os.path.join(ROOT_DIR, "governance.json")

_CONFIG_CACHE: dict[str, Any] | None = None


def load_governance_config(filepath: str | None = None, reload: bool = False) -> dict[str, Any]:
    """Load governance configuration from JSON file.

    Fails loud with FileNotFoundError if the configuration file is missing.
    """
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None and not reload and filepath is None:
        return _CONFIG_CACHE

    target_path = filepath or GOVERNANCE_CONFIG_FILE
    if not os.path.exists(target_path):
        raise FileNotFoundError(
            f"Governance configuration file not found at: {target_path}. "
            "Ensure 'governance.json' exists in repository root."
        )

    with open(target_path, encoding="utf-8") as f:
        data = json.load(f)

    if filepath is None:
        _CONFIG_CACHE = data
    return data


def get_repo_name(config: dict[str, Any] | None = None) -> str:
    """Return configured GitHub repository name (owner/repo)."""
    cfg = config or load_governance_config()
    return cfg.get("project", {}).get("repo", "")


def get_task_prefix(config: dict[str, Any] | None = None) -> str:
    """Return configured task issue prefix (e.g. CAN, PROJ)."""
    cfg = config or load_governance_config()
    return cfg.get("project", {}).get("task_prefix", "CAN")


def get_linear_team_prefix(config: dict[str, Any] | None = None) -> str:
    """Return configured Linear native team prefix (e.g. BEN, TEAM)."""
    cfg = config or load_governance_config()
    return cfg.get("project", {}).get("linear_team_prefix", "BEN")


def get_tasks_file(config: dict[str, Any] | None = None) -> str:
    """Return path to TASKS.md file."""
    cfg = config or load_governance_config()
    rel_path = cfg.get("project", {}).get("tasks_file", "TASKS.md")
    return os.path.join(ROOT_DIR, rel_path)


def get_triangular_matrix(config: dict[str, Any] | None = None) -> dict[str, str]:
    """Return author -> reviewer mapping dictionary."""
    cfg = config or load_governance_config()
    return cfg.get("reviewers", {}).get("triangular_matrix", {})


def get_triangular_reviewer(author: str, config: dict[str, Any] | None = None) -> str | None:
    """Resolve triangular peer reviewer for given author."""
    clean_author = author.lower().lstrip("@")
    matrix = get_triangular_matrix(config)
    return matrix.get(clean_author)


def get_milestone_number(task_key: str | None, config: dict[str, Any] | None = None) -> int | None:
    """Resolve GitHub Milestone number (1-7) from task key e.g. CAN-17 -> 3."""
    if not task_key:
        return None
    try:
        task_id = int(task_key.split("-")[1])
    except Exception:
        return None

    cfg = config or load_governance_config()
    ranges = cfg.get("milestones", {}).get("ranges", [])
    for r in ranges:
        if task_id in r.get("task_ids", []):
            # GitHub Milestones: Milestone 0 is #1, Milestone 1 is #2, etc.
            return r.get("index", 0) + 1
    return None


def get_milestone_index(task_key: str | None, config: dict[str, Any] | None = None) -> int | None:
    """Resolve 0-indexed milestone number e.g. CAN-17 -> 2 (Milestone 2)."""
    num = get_milestone_number(task_key, config)
    return (num - 1) if num is not None else None


def get_area_label(search_text: str, config: dict[str, Any] | None = None) -> str:
    """Resolve domain area label from search text based on keyword dictionary."""
    cfg = config or load_governance_config()
    keywords_map = cfg.get("labels", {}).get("area_keywords", {})
    text_lower = search_text.lower()

    for label, keywords in keywords_map.items():
        if any(k.lower() in text_lower for k in keywords):
            return label
    return cfg.get("labels", {}).get("default_area", "area:governance")


def get_commit_pattern(config: dict[str, Any] | None = None) -> re.Pattern[str]:
    """Compile conventional commit regex using configured prefixes and types."""
    cfg = config or load_governance_config()
    types = cfg.get("commit_linter", {}).get(
        "allowed_types",
        ["feat", "fix", "docs", "chore", "test", "refactor", "ci", "style", "perf"],
    )
    prefixes = cfg.get("commit_linter", {}).get(
        "allowed_prefixes",
        ["CAN", "TECH-DEBT"],
    )

    types_part = "|".join(types)
    prefix_patterns: list[str] = []
    for p in prefixes:
        if p == "TECH-DEBT":
            prefix_patterns.append(r"\[TECH-DEBT\]")
        else:
            prefix_patterns.append(rf"\[{p}-\d+\]")
    prefixes_part = "|".join(prefix_patterns)

    # Format: `([PREFIX] )?type(scope)?: description`
    pattern_str = rf"^((?:{prefixes_part})\s+)?(?:{types_part})(?:\([a-zA-Z0-9_\-.]+\))?:\s+.+$"
    return re.compile(pattern_str)


def get_procedural_blocklist(config: dict[str, Any] | None = None) -> list[str]:
    """Return list of banned procedural phrases in commit messages."""
    cfg = config or load_governance_config()
    return cfg.get("commit_linter", {}).get("procedural_keywords_blocklist", [])
