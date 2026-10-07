# Developer Account Setup & Agent Automation Guide

This guide provides step-by-step instructions for team members (**Benjamin, Samir, Yassir**) to configure their accounts for secure, verified collaboration and demonstrates how our AI assistants (**Cursor, Claude Code, Antigravity, Copilot**) automate task tracking, commit signing, and Linear issue synchronization.

---

## 🔐 Part 1: GitHub SSH Key & Verified Commit Signing

To comply with enterprise security standards and branch protection, all commits should be cryptographically signed using SSH keys, yielding the green **Verified** badge on GitHub.

```mermaid
flowchart LR
    A[1. Generate Ed25519 Key] --> B[2. Configure Git to use SSH Signing]
    B --> C[3. Add Public Key to GitHub as Signing Key]
    C --> D[4. Commit & Get Green 'Verified' Badge]
```

### Step 1.1: Generate Your SSH Key (If Not Already Created)
Open your terminal (PowerShell or Bash) and run:
```bash
ssh-keygen -t ed25519 -C "your_email@example.com"
```
*(Press Enter to save to default location `~/.ssh/id_ed25519`)*.

### Step 1.2: Configure Git for Automatic SSH Signing
Tell Git to use SSH format for signing all commits:
```bash
# 1. Set SSH as the signing format
git config --global gpg.format ssh

# 2. Point to your public SSH key
# On Windows PowerShell:
git config --global user.signingkey "$HOME/.ssh/id_ed25519.pub"

# On macOS / Linux:
git config --global user.signingkey ~/.ssh/id_ed25519.pub

# 3. Enable automatic commit signing globally
git config --global commit.gpgsign true

# 4. Verify your git user identity matches your GitHub account
git config --global user.name "Your Name"
git config --global user.email "your_email@example.com"
```

### Step 1.3: Add Your Signing Key to GitHub
1. Copy your public key:
   - **Windows:** `Get-Content ~/.ssh/id_ed25519.pub | Set-Clipboard`
   - **macOS:** `pbcopy < ~/.ssh/id_ed25519.pub`
   - **Linux:** `cat ~/.ssh/id_ed25519.pub`
2. Go to GitHub: [https://github.com/settings/keys](https://github.com/settings/keys).
3. Click **New SSH Key**.
4. In the **Key type** dropdown, select **Signing Key** (IMPORTANT: Select *Signing Key*, not Authentication Key).
5. Paste your key and click **Add SSH Key**.

### Step 1.4: Verify Your Commit Signing
Run a test commit on your feature branch:
```bash
git commit -m "[CAN-00] test: verify commit signing"
git log --show-signature -1
```
When pushed to GitHub, your commit will show a green **Verified** badge.

---

## 📋 Part 2: Linear.app Workspace & Personal API Key

Our team tracks cycles and epics in Linear:
- **Workspace:** [https://linear.app/canopendataagenticplatform/team/CAN/active](https://linear.app/canopendataagenticplatform/team/CAN/active)
- **Team Key:** `CAN` (Issues format: `CAN-01`, `CAN-02`, etc.)
- **Free Tier Confirmation:** Linear Personal API Keys (`lin_api_...`) are **100% free** and provide full read/write access to list, create, and transition tasks.

### Step 2.1: Generate Your Personal API Key
1. Go to Linear: [linear.app/canopendataagenticplatform](https://linear.app/canopendataagenticplatform).
2. Click your avatar (bottom left) $\rightarrow$ **Settings** $\rightarrow$ **Account** $\rightarrow$ **Security & Access**.
3. Under **Personal API keys**, click **Create Key**.
4. Name it `Agent-Key` and copy the secret token (`lin_api_...`).
5. Add it to your local environment (e.g. in your `.env` or shell profile):
   ```bash
   # Windows PowerShell
   [System.Environment]::SetEnvironmentVariable('LINEAR_API_KEY', 'lin_api_YOUR_TOKEN', 'User')

   # macOS / Linux (bash/zsh)
   export LINEAR_API_KEY="lin_api_YOUR_TOKEN"
   ```

---

## 🤖 Part 3: Connecting Your AI Agent to Linear (MCP Integration)

By configuring the official **Linear Model Context Protocol (MCP)** server, your AI assistant (**Cursor, Claude Desktop, Antigravity**) can query, create, and modify tasks directly.

### Configuration for Cursor:
1. Open Cursor $\rightarrow$ **Cursor Settings** $\rightarrow$ **Features** $\rightarrow$ **MCP**.
2. Click **+ Add New MCP Server**.
3. Fill in:
   - **Name:** `linear`
   - **Type:** `command`
   - **Command:** `npx -y @modelcontextprotocol/server-linear`
4. Set Environment Variable:
   ```json
   {
     "LINEAR_API_KEY": "lin_api_YOUR_TOKEN_HERE"
   }
   ```

### Configuration for Claude Desktop:
In `~/Library/Application Support/Claude/claude_desktop_config.json` (Mac) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):
```json
{
  "mcpServers": {
    "linear": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-linear"],
      "env": {
        "LINEAR_API_KEY": "lin_api_YOUR_TOKEN_HERE"
      }
    }
  }
}
```

---

## 🔄 Part 4: Task Status Synchronization Automation (`sync_tasks.py`)

To ensure that [`TASKS.md`](../TASKS.md) and Linear.app never fall out of sync, we provide an automated CLI tool located at `scripts/sync_tasks.py`.

### 1. Check Live Dashboard:
```bash
python scripts/sync_tasks.py --status
```
*Outputs completion percentage, grouped milestone progress, and task states across Benjamin, Samir, and Yassir.*

### 2. See Tasks Assigned to You:
```bash
python scripts/sync_tasks.py --owner Samir
python scripts/sync_tasks.py --owner Yassir
python scripts/sync_tasks.py --owner Benjamin
```

### 3. Transition Task to "In Progress":
```bash
python scripts/sync_tasks.py --mark-in-progress CAN-02
```

### 4. Mark Task as Done (Updates TASKS.md checkbox & Linear status):
```bash
python scripts/sync_tasks.py --mark-done CAN-02
```
*This command automatically flips `- [ ] CAN-02` to `- [x] CAN-02` in `TASKS.md` and transitions the ticket on Linear to "Done"!*

---

## 💬 Part 5: How Team Members Manage Status Changes

You have two easy ways to tackle status updates:

### Method A: Asking Your AI Agent (Zero-Friction)
You can simply instruct your agent:
> *"I have finished CAN-02. Please mark it as completed in TASKS.md and update Linear."*

The Agent will:
1. Run `python scripts/sync_tasks.py --mark-done CAN-02` (or use Linear MCP).
2. Stage and commit the `TASKS.md` checkbox update alongside your Pull Request.

### Method B: Manual Linear UI Changes (Visual Board)
1. Open the board: [https://linear.app/canopendataagenticplatform/team/CAN/active](https://linear.app/canopendataagenticplatform/team/CAN/active).
2. Drag your task card between columns:
   - **Todo** $\rightarrow$ Initial backlog state.
   - **In Progress** $\rightarrow$ When you create your branch (`feat/CAN-XXX-...`).
   - **In Review** $\rightarrow$ When you open your GitHub PR and assign your triangular reviewer.
   - **Done** $\rightarrow$ When your PR merges into `main` (Linear also does this automatically if your PR body says `Closes CAN-XXX`!).

---

## 🚀 Part 6: Agent Self-Setup Commands

Team members can ask their agent to assist with any of the steps above:
- *"Check my git SSH signing configuration"* $\rightarrow$ Agent runs `git config --get commit.gpgsign`.
- *"Show me my pending tasks from TASKS.md"* $\rightarrow$ Agent runs `python scripts/sync_tasks.py --owner <Name>`.
- *"Verify if our tasks match Linear"* $\rightarrow$ Agent runs `python scripts/sync_tasks.py --status --sync-linear`.
