import os
import subprocess
import tempfile
import shutil

html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Linear — Canadian Open Data Agentic Platform</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; }
  body { background-color: #0e1015; color: #f7f8f8; padding: 32px 48px; }
  .header { display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #23252b; padding-bottom: 20px; margin-bottom: 28px; }
  .team-info { display: flex; align-items: center; gap: 16px; }
  .logo-icon { width: 38px; height: 38px; background: linear-gradient(135deg, #5e6ad2, #8b5cf6); border-radius: 10px; display: flex; align-items: center; justify-content: center; font-weight: 700; color: white; font-size: 16px; box-shadow: 0 4px 12px rgba(94,106,210,0.3); }
  .title { font-size: 22px; font-weight: 700; color: #ffffff; letter-spacing: -0.3px; }
  .subtitle { font-size: 13px; color: #8a8f98; margin-top: 3px; }
  .stats-bar { display: flex; gap: 20px; margin-bottom: 28px; }
  .stat-card { background: #16181f; border: 1px solid #262832; border-radius: 10px; padding: 16px 24px; flex: 1; }
  .stat-title { font-size: 12px; color: #8a8f98; text-transform: uppercase; letter-spacing: 0.8px; font-weight: 600; }
  .stat-val { font-size: 24px; font-weight: 700; color: #fff; margin-top: 6px; }
  .board { display: grid; grid-template-columns: repeat(3, 1fr); gap: 24px; }
  .column { background: #12141a; border: 1px solid #20222a; border-radius: 12px; padding: 18px; }
  .col-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px; font-size: 14px; font-weight: 600; color: #d0d3d8; }
  .badge { background: #232530; padding: 3px 10px; border-radius: 12px; font-size: 12px; color: #8a8f98; font-weight: 600; }
  .task-card { background: #191b22; border: 1px solid #292c36; border-radius: 10px; padding: 16px; margin-bottom: 14px; box-shadow: 0 4px 8px rgba(0,0,0,0.25); }
  .task-id { font-size: 11.5px; font-weight: 700; color: #7c88f5; margin-bottom: 6px; }
  .task-title { font-size: 14px; font-weight: 500; color: #e8eaed; line-height: 1.45; margin-bottom: 12px; }
  .task-meta { display: flex; justify-content: space-between; align-items: center; font-size: 12px; color: #8a8f98; }
  .assignee { display: flex; align-items: center; gap: 8px; font-weight: 500; }
  .avatar { width: 22px; height: 22px; border-radius: 50%; font-size: 11px; display: inline-flex; align-items: center; justify-content: center; font-weight: 700; color: white; }
  .av-b { background: #2563eb; }
  .av-s { background: #059669; }
  .av-y { background: #d97706; }
  .tag { background: #262936; color: #a5abb8; padding: 3px 8px; border-radius: 6px; font-size: 11px; font-weight: 500; }
</style>
</head>
<body>
  <div class="header">
    <div class="team-info">
      <div class="logo-icon">BEN</div>
      <div>
        <div class="title">Canadian Open Data Agentic Platform</div>
        <div class="subtitle">Linear Workspace: canopendataagenticplatform · Active Sprint Board</div>
      </div>
    </div>
    <div style="color: #4ade80; font-size: 13px; font-weight: 600; background: rgba(74,222,128,0.12); padding: 7px 16px; border-radius: 20px; border: 1px solid rgba(74,222,128,0.25);">
      ● Linear Cloud Connected &amp; Synchronized
    </div>
  </div>

  <div class="stats-bar">
    <div class="stat-card">
      <div class="stat-title">Sprint 0 Status</div>
      <div class="stat-val" style="color: #4ade80;">100% Completed (6/6)</div>
    </div>
    <div class="stat-card">
      <div class="stat-title">Active Milestone 1</div>
      <div class="stat-val" style="color: #60a5fa;">FastMCP 2.0 Core</div>
    </div>
    <div class="stat-card">
      <div class="stat-title">Core Team Contributors</div>
      <div class="stat-val">3 Distributed AI Engineers</div>
    </div>
  </div>

  <div class="board">
    <!-- DONE COLUMN -->
    <div class="column">
      <div class="col-header">
        <span>✅ Completed (Sprint 0)</span>
        <span class="badge">6</span>
      </div>
      <div class="task-card">
        <div class="task-id">CAN-00 · BEN-1</div>
        <div class="task-title">Verify end-to-end Gitflow &amp; Linear sync</div>
        <div class="task-meta">
          <span class="assignee"><span class="avatar av-b">B</span> Benjamin</span>
          <span class="tag">verified</span>
        </div>
      </div>
      <div class="task-card">
        <div class="task-id">CAN-02 · BEN-6</div>
        <div class="task-title">Draft 3 GTA Housing Ground-Truth Benchmark Questions</div>
        <div class="task-meta">
          <span class="assignee"><span class="avatar av-s">S</span> Samir</span>
          <span class="tag">benchmarks</span>
        </div>
      </div>
      <div class="task-card">
        <div class="task-id">CAN-05 · BEN-37</div>
        <div class="task-title">Enforce Enterprise GitHub Ruleset &amp; Triangular Reviews</div>
        <div class="task-meta">
          <span class="assignee"><span class="avatar av-b">B</span> Benjamin</span>
          <span class="tag">governance</span>
        </div>
      </div>
      <div class="task-card">
        <div class="task-id">CAN-08 · BEN-42</div>
        <div class="task-title">Automated Linear API Onboarding &amp; HITL Reviewer Protocols</div>
        <div class="task-meta">
          <span class="assignee"><span class="avatar av-b">B</span> Benjamin</span>
          <span class="tag">tooling</span>
        </div>
      </div>
    </div>

    <!-- IN PROGRESS COLUMN -->
    <div class="column">
      <div class="col-header">
        <span>🔨 In Progress (Sprint 1)</span>
        <span class="badge">2</span>
      </div>
      <div class="task-card" style="border-left: 3px solid #60a5fa;">
        <div class="task-id">CAN-11 · BEN-7</div>
        <div class="task-title">Implement async HTTPX client for Statistics Canada WDS API</div>
        <div class="task-meta">
          <span class="assignee"><span class="avatar av-b">B</span> Benjamin</span>
          <span class="tag">FastMCP</span>
        </div>
      </div>
      <div class="task-card" style="border-left: 3px solid #60a5fa;">
        <div class="task-id">CAN-62 · BEN-38</div>
        <div class="task-title">LinkedIn Public Launch &amp; Automated Showcase Generator</div>
        <div class="task-meta">
          <span class="assignee"><span class="avatar av-b">B</span> Benjamin</span>
          <span class="tag">build-in-public</span>
        </div>
      </div>
    </div>

    <!-- UPCOMING SPRINT 1 COLUMN -->
    <div class="column">
      <div class="col-header">
        <span>⏳ Sprint 1 Backlog</span>
        <span class="badge">4</span>
      </div>
      <div class="task-card">
        <div class="task-id">CAN-12 · BEN-8</div>
        <div class="task-title">Bank of Canada Valet API async connector</div>
        <div class="task-meta">
          <span class="assignee"><span class="avatar av-y">Y</span> Yassir</span>
          <span class="tag">BoC API</span>
        </div>
      </div>
      <div class="task-card">
        <div class="task-id">CAN-13 · BEN-9</div>
        <div class="task-title">DuckDB Arrow Streaming Engine (200MB to &lt;3KB)</div>
        <div class="task-meta">
          <span class="assignee"><span class="avatar av-b">B</span> Benjamin</span>
          <span class="tag">DuckDB</span>
        </div>
      </div>
      <div class="task-card">
        <div class="task-id">CAN-14 · BEN-10</div>
        <div class="task-title">Curate 15 ground-truth benchmark questions</div>
        <div class="task-meta">
          <span class="assignee"><span class="avatar av-s">S</span> Samir</span>
          <span class="tag">evals</span>
        </div>
      </div>
    </div>
  </div>
</body>
</html>
'''

temp_html = os.path.join(tempfile.gettempdir(), 'linear_dash.html')
with open(temp_html, 'w', encoding='utf-8') as f:
    f.write(html_content)

edge_path = r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
tmp_png = os.path.join(tempfile.gettempdir(), 'temp_linear.png')
dest_png = os.path.abspath('collaboration/social/assets/linear_dashboard.png')

cmd = [
    edge_path,
    '--headless=new',
    '--disable-gpu',
    '--no-sandbox',
    '--window-size=1920,1080',
    f'--screenshot={tmp_png}',
    f'file:///{temp_html}'
]
subprocess.run(cmd, capture_output=True)
if os.path.exists(tmp_png):
    shutil.copyfile(tmp_png, dest_png)
    print(f'Linear dashboard captured: {os.path.getsize(dest_png)} bytes')
else:
    print('Failed to capture Linear dashboard')
