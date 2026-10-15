# Walkthrough Guide: CAN-62 LinkedIn Showcase & Reusable Social Pipeline

## 🎯 Purpose
This guide walks through the automated LinkedIn showcase video & animated GIF generator built for **CanData-MCP** (`CAN-62`). It allows the team to present the 7-week "Building in Public" sprint series on LinkedIn with real, high-resolution visual proof of our Monorepo, MCP mirror, Linear sprint board, GitHub PR flows, and enterprise rulesets.

---

## 📦 What Was Built

1. **Live Asset Capture (`collaboration/social/assets/` & `presentation/social-showcase/assets/`):**
   - `benchmark_questions.png` — Real capture of Samir's Housing Ground-Truth Benchmark on GitHub (`collaboration/benchmarks/benchmark_questions_draft.md`).
   - `monorepo_main.png` — Real capture of the monorepo root [`neobenjax/Canadian-Open-Data-Agentic-Platform`](https://github.com/neobenjax/Canadian-Open-Data-Agentic-Platform).
   - `linear_dashboard.png` — Linear sprint board showing completed Sprint 0 tasks (`CAN-00`..`08`) and active Sprint 1 (`CAN-11`, `CAN-62`).
   - `pr_merged_sample.png` — Real capture of merged PRs linked to Linear tickets.
   - `github_ruleset.png` — Real capture of active enterprise branch protection (`Bypass: NEVER`, 1 required review, signed commits).
   - `distribution_mcp.png` — Real capture of downstream standalone distribution repo [`neobenjax/Canadian-Open-Data-Agentic-Platform-MCP-Server`](https://github.com/neobenjax/Canadian-Open-Data-Agentic-Platform-MCP-Server).

2. **Interactive 16:9 Motion Stage (`presentation/social-showcase/index.html`):**
   - Zero-dependency, responsive 16:9 canvas stage (`1920x1080`), dark tech theme with Canadian maple & cyan accents.
   - **Clean Text Formatting:** Fixed all LaTeX arrow artifacts (`$\rightarrow$`) to clean Unicode arrows (`→`) across titles and headers.
   - **6 Storyboard Scenes:**
     1. **The Hook:** $2,640 hallucination vs. $2,045 StatCan verified CMHC table.
     2. **The Monorepo Engine:** DuckDB Arrow streaming callouts (<3KB payloads).
     3. **Agent-in-the-Loop Gitflow:** Linear tickets → feature branches → PR auto-close.
     4. **Peer Review Guardrail:** Ruleset screenshot + SVG Triangular Review diagram (`Benjamin -> Samir -> Yassir -> Benjamin`).
     5. **Distribution Mirror:** Monorepo → Standalone MCP mirror sync diagram with individual git attribution.
     6. **Community CTA:** Catchy finale with engagement question and team badges.
   - **Fullscreen Presentation Mode:** Added `⛶ Fullscreen Presentation` button (and `F` key shortcut) for seamless 100vw/100vh display.
   - **Clean Studio Recording Mode:** When clicking **"🎥 Record & Export Video"**, the stage automatically strips all external toolbars, black margins, and bottom controls, producing an edge-to-edge, pre-cut 1080p 60fps video with no post-production cropping required!

3. **Optimized Looping Animated GIF (`collaboration/social/candata_showcase_preview.gif`):**
   - High-fidelity looping GIF (655 KB, 960x540, 128-color adaptive palette, 4.5s per scene, well under LinkedIn's 15MB limit).
   - Generated in frameless studio mode: contains **only** the pristine presentation content, with zero control buttons or outer black borders!

4. **Reusable Automation CLI (`scripts/generate_social_showcase.py`):**
   - Single command to regenerate assets, capture frames, and recompile GIFs for future sprint updates.
   - Config-driven via `collaboration/social/sprint_showcase_config.yaml`.
   - Incorporates Human-in-the-Loop (HITL) review alignment before compilation.

5. **Role-Aware Developer Resolution (`AGENTS.md`):**
   - Updated universal agent guidelines so all AI agents (Claude, Cursor, Antigravity, Copilot) read `.env` first for `CANDATA_TEAM_MEMBER`, greet the developer by name, and remember their identity across sessions.

---

## 🧪 How to Test Manually

### Test 1: View the Interactive 16:9 Showcase in Browser
1. Open the interactive presentation in Microsoft Edge or Google Chrome:
   ```powershell
   Start-Process "presentation\social-showcase\index.html"
   ```
2. What to verify:
   - Notice the clean headers: `Linear Tickets → Feature Branches → Pull Requests` and `Monorepo → Standalone MCP Server Mirror` (no LaTeX markers).
   - Click `⛶ Fullscreen Presentation` or press `F` to enter edge-to-edge fullscreen mode.
   - Use the `⏸ Pause / ▶ Play` button to freeze any scene, or use arrow keys (`←` / `→`) to navigate.

### Test 2: Record a Clean, Pre-Cut 1080p Video for LinkedIn
1. In the open showcase window, click the red **"🎥 Record & Export Video (Clean 1080p)"** button.
2. The page automatically strips all buttons and black outer borders into studio mode.
3. Select the browser tab when prompted by the browser dialog.
4. The showcase will automatically replay all 6 scenes in 60fps.
5. Once completed, your browser will automatically download `CanData_MCP_LinkedIn_Showcase_Sprint_0.webm` — already framed and cut to the exact 16:9 canvas with zero black bars or buttons!

### Test 3: Inspect the Looping Animated GIF
1. Open the generated GIF:
   ```powershell
   Invoke-Item "collaboration\social\candata_showcase_preview.gif"
   ```
2. Notice that the GIF is now captured in frameless studio mode: no outer background, no controls bar, just the clean slideshow content.

### Test 4: Reusable CLI Automation for Future Sprints
1. To regenerate the GIF anytime:
   ```powershell
   python scripts/generate_social_showcase.py --generate-gif
   ```
2. To launch the interactive browser studio from CLI:
   ```powershell
   python scripts/generate_social_showcase.py --preview
   ```
