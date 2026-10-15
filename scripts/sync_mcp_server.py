#!/usr/bin/env python3
"""
Canadian Open Data Agentic Platform - Standalone MCP Server Distribution Sync Utility
=====================================================================================
Synchronizes files from 'distribution/', plus 'packages/', 'tests/', and shared root
configs from this engineering monorepo to the standalone distribution repository:
  https://github.com/neobenjax/Canadian-Open-Data-Agentic-Platform-MCP-Server.git

Preserves contributor attribution (Benjamin Sanchez, Samir Ibrahim, Yassir Khougali).

Usage:
    python scripts/sync_mcp_server.py --dry-run
    python scripts/sync_mcp_server.py
    python scripts/sync_mcp_server.py --token <github_pat>
"""

import argparse
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

# Ensure UTF-8 output encoding on Windows consoles
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Paths
ROOT_DIR = Path(__file__).resolve().parent.parent
DIST_DIR = ROOT_DIR / "distribution"
SCRATCH_DIR = ROOT_DIR / ".mcp_dist_scratch"
ENV_FILE = ROOT_DIR / ".env"
TARGET_REPO_URL = (
    "https://github.com/neobenjax/Canadian-Open-Data-Agentic-Platform-MCP-Server.git"
)

# Shared root files to copy to distribution root
SHARED_FILES = [
    "ABOUT_THE_TEAM.md",
    ".cursorrules",
    ".env.example",
    ".gitignore",
    "LICENSE",
]

# Shared root directories to copy
SHARED_DIRS = [
    "packages",
    "tests",
]

# Bloat items to remove from the distribution repo
BLOAT_ITEMS = [
    "apps",
    "presentation",
    "collaboration",
    "assets",
    "docs",
    "CANADIAN_AGENTIC_DATA_PLATFORM_PLAN.md",
    "General Plan - idea.md",
    "TASKS.md",
    "linear_tasks_import.csv",
    "WIKI_README.md",
    "MCP_README.md",
]


def on_rm_error(func, path, exc_info):
    """Handles read-only file deletion on Windows."""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass


def clean_scratch_dir() -> None:
    """Safely cleans the scratch directory on Windows and Unix."""
    if SCRATCH_DIR.exists():
        shutil.rmtree(SCRATCH_DIR, onerror=on_rm_error)
    if SCRATCH_DIR.exists():
        subprocess.run(["cmd", "/c", "rmdir", "/s", "/q", str(SCRATCH_DIR)], capture_output=True)


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


def sync_mcp_distro(dry_run: bool = False, token: str | None = None) -> int:
    """Synchronizes the MCP Server package to the distribution repository."""
    print("=" * 75)
    print(" CanData Platform - Standalone MCP Server Distribution Publisher")
    print("=" * 75)

    auth_token = token or load_env_token()
    if not auth_token:
        print("\n[!] Error: No GitHub authentication token found.")
        print("Please configure 'GITHUB_TOKEN' or 'WIKI_SYNC_TOKEN' in .env.")
        return 1

    auth_url = TARGET_REPO_URL.replace("https://", f"https://x-access-token:{auth_token}@")

    print(f"\nMonorepo source : {ROOT_DIR}")
    print(f"Distribution src: {DIST_DIR}")
    print(f"Target repo     : {TARGET_REPO_URL}")
    print(f"Mode            : {'DRY RUN (Simulate only)' if dry_run else 'LIVE WASH & PUBLISH'}")

    clean_scratch_dir()

    print("\n[1/5] Cloning target MCP Server repository...")
    clone_res = run_git(["git", "clone", auth_url, str(SCRATCH_DIR)])
    if clone_res.returncode != 0:
        print(f"[!] Git clone failed: {clone_res.stderr}")
        return 1
    print("[+] Cloned successfully.")

    print("\n[2/5] Washing out non-MCP bloat from distribution repository...")
    washed_count = 0
    for item in BLOAT_ITEMS:
        item_path = SCRATCH_DIR / item
        if item_path.is_dir():
            shutil.rmtree(item_path, onerror=on_rm_error)
            print(f"  [-] Removed folder: {item}/")
            washed_count += 1
        elif item_path.is_file():
            item_path.unlink()
            print(f"  [-] Removed file:   {item}")
            washed_count += 1
    if washed_count == 0:
        print("  [*] Target repository is already free of legacy bloat.")

    print("\n[3/5] Overlaying distribution folder & shared monorepo packages...")
    # Copy all files from distribution/ into target root
    if DIST_DIR.exists():
        for dist_item in DIST_DIR.iterdir():
            dest = SCRATCH_DIR / dist_item.name
            if dist_item.is_file():
                shutil.copy2(dist_item, dest)
                print(f"  [+] Copied from distribution/: {dist_item.name} -> {dest.name}")
            elif dist_item.is_dir():
                if dest.exists():
                    shutil.rmtree(dest, onerror=on_rm_error)
                shutil.copytree(dist_item, dest)
                print(f"  [+] Copied folder from distribution/: {dist_item.name}/")

    # Copy shared files
    for f in SHARED_FILES:
        src_path = ROOT_DIR / f
        dest_path = SCRATCH_DIR / f
        if src_path.exists():
            shutil.copy2(src_path, dest_path)
            print(f"  [+] Copied shared file: {f}")

    # Copy shared directories
    for d in SHARED_DIRS:
        src_dir = ROOT_DIR / d
        dest_dir = SCRATCH_DIR / d
        if src_dir.exists():
            if dest_dir.exists():
                shutil.rmtree(dest_dir, onerror=on_rm_error)
            shutil.copytree(src_dir, dest_dir)
            file_count = sum(1 for _ in dest_dir.rglob("*") if _.is_file())
            print(f"  [+] Copied shared directory: {d}/ ({file_count} files)")

    print("\n[4/5] Inspecting distribution git status...")
    run_git(["git", "add", "-A"], cwd=SCRATCH_DIR)
    status_res = run_git(["git", "status", "--porcelain"], cwd=SCRATCH_DIR)
    changes = status_res.stdout.strip().splitlines()

    if not changes:
        print("[*] No changes detected. MCP Server distribution is already up to date!")
        clean_scratch_dir()
        return 0

    print(f"[*] Detected {len(changes)} changes in distribution repo:")
    for line in changes[:12]:
        print(f"    {line}")
    if len(changes) > 12:
        print(f"    ... and {len(changes) - 12} more changes.")

    if dry_run:
        print("\n[i] DRY RUN COMPLETE: Verification successful. Nothing was pushed.")
        clean_scratch_dir()
        return 0

    print("\n[5/5] Committing with multi-contributor attribution & pushing...")
    run_git(["git", "config", "user.name", "Neobenjax"], cwd=SCRATCH_DIR)
    run_git(["git", "config", "user.email", "besaze@hotmail.com"], cwd=SCRATCH_DIR)

    commit_body = (
        "docs: add CONTRIBUTING redirect and update distribution metadata\n\n"
        "Configures contribution guidelines redirecting developers to the primary\n"
        "engineering monorepo for issue tracking and PR submissions.\n\n"
        "Co-authored-by: Samir Ibrahim <samiroibrahim@users.noreply.github.com>\n"
        "Co-authored-by: Yassir Tagelsir Khougali <yassirtmk@users.noreply.github.com>"
    )

    run_git(["git", "commit", "-m", commit_body], cwd=SCRATCH_DIR)

    push_res = run_git(["git", "push", "origin", "main"], cwd=SCRATCH_DIR)
    clean_scratch_dir()

    if push_res.returncode == 0:
        print("\n[SUCCESS] Standalone MCP Server updated successfully on GitHub!")
        print(f"👉 URL: {TARGET_REPO_URL}")
        return 0
    else:
        print(f"\n[ERROR] Push failed:\n{push_res.stderr}")
        return 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Publish the standalone MCP server package to its distribution repository."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the washout and sync without pushing to GitHub.",
    )
    parser.add_argument(
        "--token",
        type=str,
        default=None,
        help="GitHub Personal Access Token.",
    )
    args = parser.parse_args()

    sys.exit(sync_mcp_distro(dry_run=args.dry_run, token=args.token))


if __name__ == "__main__":
    main()
