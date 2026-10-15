#!/usr/bin/env python3
"""
Canadian Open Data Agentic Platform - Documentation WIKI Sync Utility
=====================================================================
Synchronizes documentation, presentations, portfolio sites, and collaboration
assets from the primary MCP codebase to the dedicated WIKI repository:
  https://github.com/neobenjax/Canadian-Open-Data-Agentic-Platform-WIKI.git

Usage:
    python scripts/sync_wiki_repo.py --dry-run
    python scripts/sync_wiki_repo.py
    python scripts/sync_wiki_repo.py --token <github_pat>
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Ensure UTF-8 output encoding on Windows consoles
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Paths
ROOT_DIR = Path(__file__).resolve().parent.parent
SCRATCH_DIR = ROOT_DIR / ".wiki_sync_scratch"
ENV_FILE = ROOT_DIR / ".env"
WIKI_REPO_URL = "https://github.com/neobenjax/Canadian-Open-Data-Agentic-Platform-WIKI.git"

# Sync definitions: source relative to ROOT_DIR -> dest relative to WIKI root
SYNC_FILES = {
    "WIKI_README.md": "README.md",
    "ABOUT_THE_TEAM.md": "ABOUT_THE_TEAM.md",
    "CANADIAN_AGENTIC_DATA_PLATFORM_PLAN.md": "CANADIAN_AGENTIC_DATA_PLATFORM_PLAN.md",
    "General Plan - idea.md": "General Plan - idea.md",
}

SYNC_DIRS = [
    "collaboration",
    "docs",
    "presentation",
    "apps",
    "assets",
]


def load_env_token() -> str | None:
    """Reads WIKI_SYNC_TOKEN or GITHUB_TOKEN from .env or os.environ."""
    token = os.environ.get("WIKI_SYNC_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token and not token.startswith("ghp_YOUR") and not token.startswith("lin_api"):
        return token.strip()

    if ENV_FILE.exists():
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip("\"'")
                    if k in ("WIKI_SYNC_TOKEN", "GITHUB_TOKEN"):
                        if v and not v.startswith("ghp_YOUR"):
                            return v
    return None


def run_git(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Runs a git command safely and returns the completed process."""
    return subprocess.run(
        cmd,
        cwd=cwd or ROOT_DIR,
        capture_output=True,
        text=True,
        check=False,
    )


def sync_wiki(dry_run: bool = False, token: str | None = None) -> int:
    """Executes the synchronization to the WIKI repository."""
    print("=" * 70)
    print(" Canadian Open Data Agentic Platform - WIKI Sync Utility")
    print("=" * 70)

    auth_token = token or load_env_token()
    if not auth_token:
        print("\n[!] Error: No GitHub authentication token found.")
        print("Please configure 'WIKI_SYNC_TOKEN' or 'GITHUB_TOKEN' in your .env file,")
        print("or pass --token <github_pat>.")
        return 1

    # Form authenticated clone URL
    auth_url = WIKI_REPO_URL.replace("https://", f"https://x-access-token:{auth_token}@")

    print(f"\nSource repository : {ROOT_DIR}")
    print(f"Target WIKI repo   : {WIKI_REPO_URL}")
    print(f"Execution mode    : {'DRY RUN (No push)' if dry_run else 'LIVE SYNC & PUSH'}")

    # Prepare scratch clone dir
    if SCRATCH_DIR.exists():
        shutil.rmtree(SCRATCH_DIR, ignore_errors=True)
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)

    print("\n[1/4] Cloning remote WIKI repository into temporary staging...")
    clone_res = run_git(["git", "clone", "--depth", "1", auth_url, str(SCRATCH_DIR)])
    if clone_res.returncode != 0:
        # If repo is empty or clone failed, try git init
        print("[-] Direct clone note: Repository may be empty. Initializing branch 'main'...")
        run_git(["git", "init"], cwd=SCRATCH_DIR)
        run_git(["git", "remote", "add", "origin", auth_url], cwd=SCRATCH_DIR)
        run_git(["git", "checkout", "-b", "main"], cwd=SCRATCH_DIR)
    else:
        print("[+] Remote repository cloned successfully.")

    print("\n[2/4] Copying documentation files and directories...")
    # Copy individual files
    for src_rel, dest_rel in SYNC_FILES.items():
        src_path = ROOT_DIR / src_rel
        dest_path = SCRATCH_DIR / dest_rel
        if src_path.exists():
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, dest_path)
            print(f"  [FILE] Copied: {src_rel} -> {dest_rel}")
        else:
            print(f"  [-] Skipped (not found): {src_rel}")

    # Copy directories
    for d in SYNC_DIRS:
        src_dir = ROOT_DIR / d
        dest_dir = SCRATCH_DIR / d
        if src_dir.exists():
            if dest_dir.exists():
                shutil.rmtree(dest_dir, ignore_errors=True)
            shutil.copytree(src_dir, dest_dir)
            file_count = sum(1 for _ in dest_dir.rglob("*") if _.is_file())
            print(f"  [DIR]  Copied folder: {d}/ ({file_count} files)")
        else:
            print(f"  [-]  Folder not found: {d}/")

    print("\n[3/4] Checking git status on staging...")
    run_git(["git", "config", "user.name", "CanData Sync Bot"], cwd=SCRATCH_DIR)
    run_git(["git", "config", "user.email", "candata-bot@noreply.github.com"], cwd=SCRATCH_DIR)
    run_git(["git", "add", "-A"], cwd=SCRATCH_DIR)

    status_res = run_git(["git", "status", "--porcelain"], cwd=SCRATCH_DIR)
    changes = status_res.stdout.strip().splitlines()

    if not changes:
        print("[*] No changes detected. The WIKI repository is already 100% up to date!")
        shutil.rmtree(SCRATCH_DIR, ignore_errors=True)
        return 0

    print(f"[*] Detected {len(changes)} modified/new files in WIKI repository.")
    for line in changes[:10]:
        print(f"    {line}")
    if len(changes) > 10:
        print(f"    ... and {len(changes) - 10} more files.")

    if dry_run:
        print("\n[i] DRY RUN COMPLETE: Verification successful. No changes were committed or pushed.")
        shutil.rmtree(SCRATCH_DIR, ignore_errors=True)
        return 0

    print("\n[4/4] Committing and pushing changes to WIKI repository...")
    head_sha = run_git(["git", "rev-parse", "--short", "HEAD"]).stdout.strip() or "local"
    commit_msg = f"docs: automated sync from main [ref:{head_sha}]"
    run_git(["git", "commit", "-m", commit_msg], cwd=SCRATCH_DIR)

    push_res = run_git(["git", "push", "-u", "origin", "main"], cwd=SCRATCH_DIR)
    if push_res.returncode == 0:
        print("\n[SUCCESS] WIKI repository has been updated and published to GitHub!")
        print(f"URL: {WIKI_REPO_URL}")
        shutil.rmtree(SCRATCH_DIR, ignore_errors=True)
        return 0
    else:
        print(f"\n[ERROR] Error pushing to WIKI repository:\n{push_res.stderr}")
        shutil.rmtree(SCRATCH_DIR, ignore_errors=True)
        return 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Synchronize documentation and collaboration assets to the WIKI repository."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the sync and show changes without committing or pushing.",
    )
    parser.add_argument(
        "--token",
        type=str,
        default=None,
        help="GitHub Personal Access Token (defaults to WIKI_SYNC_TOKEN or GITHUB_TOKEN in .env).",
    )
    args = parser.parse_args()

    sys.exit(sync_wiki(dry_run=args.dry_run, token=args.token))


if __name__ == "__main__":
    main()
