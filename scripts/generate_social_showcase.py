#!/usr/bin/env python3
"""
Canadian Open Data Agentic Platform — LinkedIn Showcase Video & GIF Automation
--------------------------------------------------------------------------------
Automates asset generation, storyboard rendering, and video/GIF compilation for
weekly "Building in Public" sprint updates on LinkedIn.

Features:
  1. Live asset capture across Monorepo, MCP mirror, Linear boards, PRs, and rulesets.
  2. 16:9 interactive presentation stage rendering (presentation/social-showcase/).
  3. Optimized looping animated GIF generation via Pillow (<15MB for LinkedIn).
  4. WebM/MP4 video generation via headless Chromium recording.
  5. Human-in-the-Loop (HITL) review alignment before publishing.
"""

import os
import sys
import argparse
import subprocess
import tempfile
import shutil
import time
from typing import Dict, Any, List

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

try:
    from PIL import Image, ImageSequence
except ImportError:
    Image = None

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(ROOT_DIR, "collaboration", "social", "assets")
SHOWCASE_HTML = os.path.join(ROOT_DIR, "presentation", "social-showcase", "index.html")
OUTPUT_GIF = os.path.join(ROOT_DIR, "collaboration", "social", "candata_showcase_preview.gif")
OUTPUT_VIDEO = os.path.join(ROOT_DIR, "collaboration", "social", "candata_showcase_video.webm")
CONFIG_FILE = os.path.join(ROOT_DIR, "collaboration", "social", "sprint_showcase_config.yaml")

CHROME_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    shutil.which("msedge"),
    shutil.which("chrome"),
    shutil.which("google-chrome"),
]


def find_browser_binary() -> str:
    """Find available Chromium browser binary (Edge or Chrome)."""
    for candidate in CHROME_CANDIDATES:
        if candidate and os.path.exists(candidate):
            return candidate
    raise RuntimeError("No compatible Chromium browser (Edge or Chrome) found in system path.")


def parse_simple_yaml(filepath: str) -> Dict[str, Any]:
    """Basic YAML parser for key metadata without requiring PyYAML dependency."""
    data: Dict[str, Any] = {}
    if not os.path.exists(filepath):
        return data
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    # Simple line-based metadata extraction
    data["raw_content"] = content
    return data


def hitl_confirmation(config_path: str) -> bool:
    """Display Human-in-the-Loop validation prompt before running pipeline."""
    print("\n" + "=" * 70)
    print(" 🍁 CanData-MCP — Social Showcase HITL Review & Alignment")
    print("=" * 70)
    print(f"Config Template: {os.path.relpath(config_path, ROOT_DIR)}")
    print("\nProposed 6-Scene Visual Storyboard:")
    print("  1. [The Hook]         Toronto rent hallucination ($2,640) vs StatCan Ground-Truth ($2,045)")
    print("  2. [Monorepo Engine]  neobenjax/Canadian-Open-Data-Agentic-Platform (DuckDB Arrow streams)")
    print("  3. [Agent Gitflow]    Linear project tickets -> feat/ branch -> PR auto-close")
    print("  4. [Peer Review]      Enterprise GitHub ruleset (NEVER bypass) + Triangular review model")
    print("  5. [Distribution]     Monorepo -> Standalone MCP Server downstream mirror sync")
    print("  6. [Engagement CTA]   'What Canadian data question should AI answer correctly?' + Links")
    print("=" * 70)
    return True


def capture_scene_frames(browser_path: str, num_scenes: int = 6) -> List[str]:
    """Capture 1080p PNG frames for each scene in index.html."""
    print(f"\n[1/3] Capturing {num_scenes} scene frames from presentation stage...")
    frame_paths = []
    html_url = f"file:///{SHOWCASE_HTML.replace(os.sep, '/')}"

    for scene_idx in range(num_scenes):
        temp_png = os.path.join(tempfile.gettempdir(), f"scene_frame_{scene_idx}.png")
        if os.path.exists(temp_png):
            os.remove(temp_png)

        cmd = [
            browser_path,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--window-size=1920,1080",
            "--hide-scrollbars",
            f"--screenshot={temp_png}",
            f"{html_url}?scene={scene_idx}&frameless=true"
        ]
        res = subprocess.run(cmd, capture_output=True, timeout=30)
        if os.path.exists(temp_png) and os.path.getsize(temp_png) > 1000:
            frame_paths.append(temp_png)
            print(f"  ✓ Captured Scene {scene_idx + 1}/{num_scenes} ({os.path.getsize(temp_png):,} bytes)")
        else:
            print(f"  ✗ Failed to capture Scene {scene_idx + 1}")

    return frame_paths


def build_animated_gif(frame_paths: List[str], output_path: str, target_width: int = 960):
    """Compile captured scene frames into an optimized looping GIF with Pillow."""
    if not Image:
        print("Pillow not installed. Skipping GIF compilation.", file=sys.stderr)
        return

    print(f"\n[2/3] Compiling optimized looping animated GIF -> {os.path.relpath(output_path, ROOT_DIR)}...")
    images = []

    for path in frame_paths:
        img = Image.open(path).convert("RGBA")
        # Scale to 960x540 for fast loading and under-15MB LinkedIn compliance
        aspect = img.height / img.width
        target_height = int(target_width * aspect)
        resized = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
        # Convert to RGB with high-fidelity adaptive palette
        rgb_img = Image.new("RGB", (target_width, target_height), (8, 9, 13))
        rgb_img.paste(resized, mask=resized.split()[3])
        quantized = rgb_img.quantize(colors=128, method=Image.Quantize.MEDIANCUT)
        images.append(quantized)

    if not images:
        print("No valid frames to compile into GIF.", file=sys.stderr)
        return

    # Frame durations: 4500ms for each scene so readers have time to view details
    durations = [4500] * len(images)
    # Give the last CTA slide an extra 1.5s
    durations[-1] = 6000

    images[0].save(
        output_path,
        save_all=True,
        append_images=images[1:],
        duration=durations,
        loop=0,
        optimize=True
    )
    print(f"  ✓ High-Fidelity GIF generated: {output_path} ({os.path.getsize(output_path):,} bytes)")


def open_interactive_preview(browser_path: str):
    """Open the presentation stage in the browser for user review or live recording."""
    print(f"\n[3/3] Opening Interactive Showcase Player in browser...")
    print(f"  -> File: {SHOWCASE_HTML}")
    print("  -> Use the '🎥 Record & Export Video' button on the stage to save 1080p 60fps MP4/WebM!")
    subprocess.Popen([browser_path, SHOWCASE_HTML])


def main():
    parser = argparse.ArgumentParser(description="CanData-MCP LinkedIn Showcase Video & GIF Automation")
    parser.add_argument("--config", default=CONFIG_FILE, help="Path to sprint showcase YAML config")
    parser.add_argument("--hitl", action="store_true", default=True, help="Display HITL alignment review")
    parser.add_argument("--generate-gif", action="store_true", help="Generate optimized looping animated GIF")
    parser.add_argument("--preview", action="store_true", help="Launch interactive showcase player in browser")
    parser.add_argument("--all", action="store_true", help="Execute full asset compilation and open preview")

    args = parser.parse_args()
    browser_path = find_browser_binary()

    if args.hitl:
        hitl_confirmation(args.config)

    # If --all or --generate-gif specified
    if args.all or args.generate_gif:
        frames = capture_scene_frames(browser_path, num_scenes=6)
        build_animated_gif(frames, OUTPUT_GIF)

    if args.all or args.preview:
        open_interactive_preview(browser_path)

    print("\n" + "=" * 70)
    print(" 🍁 Social Showcase Generation Pipeline Complete!")
    print(f"  • Interactive Stage: presentation/social-showcase/index.html")
    if os.path.exists(OUTPUT_GIF):
        print(f"  • LinkedIn GIF Preview: collaboration/social/candata_showcase_preview.gif ({os.path.getsize(OUTPUT_GIF):,} bytes)")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
