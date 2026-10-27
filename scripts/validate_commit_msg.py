#!/usr/bin/env python3
"""
Canadian Open Data Agentic Platform — Commit Message Conventional Linter
-------------------------------------------------------------------------
Validates git commit messages deterministically against conventional standards:
- Task Commits:       `[<PREFIX>-XX] feat: <summary>` or `[TECH-DEBT] fix: <summary>`
- Operational Commits: `chore: <summary>`, `docs: <summary>`, `ci: <summary>`
- Rejects conversational/procedural messages ("address review comments", "fix PR").
Configured via `governance.json` for portability across different repositories.
"""

import io
import os
import sys

# Ensure repository root is on sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from scripts.governance_config import get_commit_pattern, get_procedural_blocklist  # noqa: E402

if isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout.reconfigure(encoding="utf-8")
if isinstance(sys.stderr, io.TextIOWrapper):
    sys.stderr.reconfigure(encoding="utf-8")

ALLOWED_STARTS = (
    "Merge branch",
    "Merge pull request",
    "Merge remote-tracking",
    "Revert",
)


def validate_commit_message(message: str) -> tuple[bool, str]:
    """Validate commit message string and return (is_valid, reason)."""
    lines = [
        line.strip()
        for line in message.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    if not lines:
        return False, "Commit message is empty."

    first_line = lines[0]

    # Allow automatic git merge/revert messages
    if first_line.startswith(ALLOWED_STARTS):
        return True, "Merge or revert commit allowed."

    # Validate against configured conventional pattern
    pattern = get_commit_pattern()
    if not pattern.match(first_line):
        return (
            False,
            f"Commit message does not match conventional format: '{first_line}'\n\n"
            "Allowed formats:\n"
            "  - Task feature:      [<PREFIX>-XX] feat: add new feature\n"
            "  - Task bugfix:       [<PREFIX>-XX] fix: resolve issue\n"
            "  - Operational chore: chore: update CI or dependencies\n"
            "  - Documentation:     docs: update developer guide\n"
            "  - Tech debt:         [TECH-DEBT] refactor: optimize memory engine\n\n"
            "Rule: Commit messages must describe the technical outcome, not procedural actions.\n"
            "Avoid: 'address review comments', 'updates', 'fix PR'.",
        )

    # Reject procedural anti-patterns (Guardrail 17)
    blocklist = get_procedural_blocklist()
    if any(k.lower() in first_line.lower() for k in blocklist):
        return (
            False,
            f"Commit message contains procedural commentary: '{first_line}'\n"
            "Guardrail 17: Commit messages must describe outcome, never procedural phrases.",
        )

    return True, "Valid conventional commit."


def main():
    if len(sys.argv) < 2:
        print(
            "Usage: python scripts/validate_commit_msg.py <commit_msg_file_or_string>",
            file=sys.stderr,
        )
        sys.exit(1)

    target = sys.argv[1]
    msg = ""

    # Check if target is a file path (standard git hook pass)
    try:
        with open(target, encoding="utf-8") as f:
            msg = f.read()
    except Exception:
        # Otherwise treat target as literal message string
        msg = target

    is_valid, reason = validate_commit_message(msg)
    if not is_valid:
        print("\n" + "=" * 74, file=sys.stderr)
        print(" ❌ CONVENTIONAL COMMIT LINTER: REJECTED", file=sys.stderr)
        print("=" * 74, file=sys.stderr)
        print(reason, file=sys.stderr)
        print("=" * 74 + "\n", file=sys.stderr)
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
