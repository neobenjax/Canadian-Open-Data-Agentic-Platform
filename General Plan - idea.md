# Game Plan — Canadian Open Data MCP Server

**Kickoff:** Friday Oct 2, 2026 · 11:00 · place TBD
**Team:** Samir · Ben · 3rd member (maybe Yaser)
**Stack:** Python + FastMCP + DuckDB
**Cadence:** weekly meeting (Fridays, same slot as kickoff?) + short daily check-in
**Posting:** everyone posts; lead author rotates each stage; the others tag, reshare and comment

Ben is bringing the full task list and posting strategy on Oct 2.
This plan covers two things:

1. **Part A:** what I do before Friday, so I show up having done real work.
2. **Part B:** my own draft of the full project, so I can check Ben's plan against it.

---

## My role: Agent & Evaluation

Why this role fits me:

- I already did the GTA Housing project on **CMHC rent + StatCan income** for 25 municipalities. Those numbers are already checked, so they work as **ground truth**. I can ask the MCP tools questions where I already know the right answer.
- My posts are all about honest data: rejection logs, "blank, not zero", "42 of 45 usable". Evaluation is that same habit applied to an AI agent: *did it cite the right table, and did it make anything up?*
- It's also the role that teaches the most about agents (tool use, prompts, workflows). That's the skill I'm trying to show on LinkedIn.

Suggested split (to confirm Friday):

| Person | Role | Owns |
|---|---|---|
| **Ben** | Backend & MCP | StatCan WDS/SDMX, CMHC, CKAN adapters, DuckDB aggregation, MCP tools |
| **Samir** | Agent & Evaluation | Benchmark questions + ground truth, comparing against existing tools, agent flows, prompts, evals |
| **3rd member** | Demo & Docs | README, demo recordings (60-sec Claude Desktop video), landing/GitHub page, architecture diagram |

---

## Part A — Prep week (Thu Sep 24 → Fri Oct 2)

| Day | Task | Time | Academy |
|---|---|---|---|
| **Thu 24** | Reply to Ben: confirm Oct 2 at 11:00, suggest a location. Ask the 3rd member if they're in. | 15 min | — |
| **Fri 25** | Install Claude Desktop + `uv`/Python 3.12. Set up a scratch repo. | 1 hr | — |
| **Sat 26** | **Course: Introduction to Model Context Protocol** (Python SDK: tools, resources, prompts) | 1 hr | ✅ |
| **Sun 27** | Build a toy MCP server with 1 tool (e.g. fetch one StatCan vector) and connect it to Claude Desktop. Proves I understand it end-to-end. | 1–2 hrs | applies the MCP course |
| **Mon 28** | Write **10 benchmark questions** from the GTA Housing project with known answers (rent-to-income, vacancy, rent growth vs income, Toronto vs Brampton…). Add 3 cross-source ones (CMHC + StatCan). | 1.5 hrs | — |
| **Tue 29** | Install **mcp-statcan** and **ckan-mcp-server** in Claude Desktop. Run all 10 questions through each. | 2 hrs | — |
| **Wed 30** | Fill in the **comparison scorecard** (below). Note the gaps: this becomes the "why ours" pitch Ben mentioned. | 1.5 hrs | **Course: Claude Code 101** (1.5 hr) |
| **Thu Oct 1** | Read my Part B against the kickoff agenda. Write down my questions for Ben's plan. Confirm the place. | 1 hr | — |
| **Fri Oct 2** | **Kickoff 11:00.** Bring the scorecard + benchmark questions. | — | — |

### Comparison scorecard (fill in Tue/Wed)

| Question | Known answer | mcp-statcan | ckan-mcp-server | Plain Claude (no tools) |
|---|---|---|---|---|
| Q1 … | | ✅ / ⚠️ / ❌ + cited table? | | |

Score each answer on: **correct value · cited official table · handled missing data honestly · tokens/time · could it combine sources?**
The last column (no tools) is the control. It shows what the tools actually add.

---

## Part B — Draft of the full project (compare with Ben's)

About 9 weeks. Each stage ends at a Friday meeting and produces one LinkedIn post.

### Stage 1 — Explore & Benchmark · Oct 2 → Oct 16

| Task | Owner |
|---|---|
| Pick 3–4 datasets: CMHC rent/vacancy, StatCan income, population/immigration, housing starts | All |
| Check **CMHC access**: HMIP has no clean public API, so it may mean scraping or bulk exports. **Biggest technical risk; confirm early.** | Ben |
| Test StatCan WDS + SDMX endpoints, measure table sizes | Ben |
| Extend the benchmark to ~25 questions; finish the scorecard for existing tools | Samir |
| Architecture sketch (sources → DuckDB → MCP tools → client) | 3rd |
| **Post 1** (lead: Samir): *"We tested the existing Canadian data MCP tools against answers we already knew. Here's where they break."* | Samir |

🎓 Samir: *AI capabilities and limitations* (context limits explain why a 200 MB table can't go straight into the model)

### Stage 2 — Build the MCP Server · Oct 16 → Oct 30

| Task | Owner |
|---|---|
| FastMCP server with 3–5 tools: `search_tables`, `get_series`, `compare_regions`, `describe_table`, `cite_source` | Ben |
| DuckDB server-side filtering/aggregation, so the model only gets small payloads | Ben |
| Every tool response includes source table ID + URL + reference period | Ben + Samir |
| Run the benchmark against our server each week; track the score over time | Samir |
| Demo GIF of the first working query | 3rd |
| **Post 2** (lead: Ben): *How we got a 200 MB StatCan table down to a 2 KB answer* (DuckDB + SDMX filtering) | Ben |

🎓 Samir: *Claude Code in action* · Ben: *Introduction to MCP* (if not done)

### Stage 3 — Add the Agent · Oct 30 → Nov 13

| Task | Owner |
|---|---|
| Agent flow that answers a multi-source question end-to-end, e.g. *"Where in the GTA is rent rising fastest vs income?"* | Samir |
| Prompts/instructions: always cite, say "data can't answer this" when it can't, flag mismatched years (2020 census vs 2025 rent) | Samir |
| Chart output for the answer | 3rd |
| **Post 3** (lead: 3rd member): 60-sec video, one question answered in Claude Desktop with citations | 3rd |

🎓 Samir: *Building with the Claude API* (the tool use + agents sections; no need to do all 67 lessons) · *Introduction to subagents*

### Stage 4 — Improve & Test · Nov 13 → Nov 27

| Task | Owner |
|---|---|
| Bilingual EN/FR (StatCan and CKAN metadata are already bilingual) | Ben |
| Automated eval suite: benchmark questions run in CI, score reported | Samir |
| Unit tests for the adapters | Ben |
| Invite 3–5 testers (analysts, journalists, policy people); collect what broke | Samir + 3rd |
| **Post 4** (lead: Samir): *what broke and how we fixed it*, in the honest style of the El Niño posts | Samir |

🎓 Ben: *Model Context Protocol: Advanced topics* (notifications/sampling help with streaming large tables)

### Stage 5 — Publish & Share · Nov 27 → Dec 4

| Task | Owner |
|---|---|
| Publish to GitHub + PyPI + MCP directories | Ben |
| Case-study README: benchmark results vs existing tools | Samir + 3rd |
| One-page pitch for the target buyers: federal/crown entities, public-sector IT, boutique data/policy firms, municipal tech | Samir |
| **Post 5** (lead: rotate): case study + link + thanks to testers | All |

🎓 Everyone: *Adapt content across platforms* (use case) to turn the case study into posts, a README and the pitch

---

## Daily check-in (async, 2 min)

Post in the group chat before a set time each day:

```
✅ Done:
➡️ Next:
🚧 Blocked:
```

## Kickoff agenda (Oct 2, 11:00)

1. Ben walks through his tasks + posting strategy (20 min)
2. Samir: benchmark + scorecard of existing tools (10 min)
3. Agree on roles, stage dates, post rotation (15 min)
4. Open decisions (below) (10 min)
5. Set the weekly meeting slot + the daily check-in time (5 min)

## Open decisions to settle Friday

- [ ] Is the 3rd member confirmed (Yaser)?
- [ ] Final 3–4 datasets
- [ ] CMHC access approach (API / export / scrape) and its legal/ToS status
- [ ] Repo: whose GitHub account or an org, name, license (MIT?)
- [ ] Where we talk (WhatsApp/Slack/Discord) + daily check-in time
- [ ] Weekly meeting: Fridays 11:00 every week?
- [ ] Post rotation and how we tag each other; approval before posting?
- [ ] Project length: is ~9 weeks (to Dec 4) realistic?

## Questions to check Ben's plan against

- Does it include **testing existing tools first** (his own suggestion)? Is the benchmark in it?
- Is the CMHC access risk addressed early, not in Stage 3?
- Does every stage end with something demo-able for the post?
- Is evaluation a real task with an owner, or just "write tests" at the end?
