'use client';

import React, { useState } from 'react';
import {
  Terminal,
  Code,
  Cpu,
  ShieldCheck,
  Check,
  Copy,
  ExternalLink,
  Zap,
  Database,
  ArrowRight,
  Globe,
  Sparkles,
} from 'lucide-react';
import Link from 'next/link';

export function QuickstartPill() {
  const [copied, setCopied] = useState(false);
  const command = 'uv run candata-mcp';

  const copyCommand = () => {
    navigator.clipboard.writeText(command);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="inline-flex flex-wrap items-center gap-3 p-1.5 rounded-2xl bg-white/90 dark:bg-slate-900/90 border border-black/10 dark:border-white/10 shadow-sm backdrop-blur-md">
      <Link
        href="/docs"
        className="px-5 py-2.5 rounded-xl bg-[#D80621] hover:bg-[#A82424] text-white font-semibold text-xs transition-all shadow-md flex items-center gap-1.5"
      >
        Get Started <ArrowRight className="w-3.5 h-3.5" />
      </Link>

      <button
        onClick={copyCommand}
        className="flex items-center gap-2 px-3.5 py-2 rounded-xl bg-slate-100 dark:bg-slate-800/80 hover:bg-slate-200 dark:hover:bg-slate-800 text-xs font-mono text-slate-800 dark:text-slate-200 transition-colors border border-black/5 dark:border-white/5"
        title="Copy install command"
      >
        <span className="text-[#D80621] font-bold">$</span>
        <span>{command}</span>
        {copied ? (
          <Check className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400 ml-1" />
        ) : (
          <Copy className="w-3.5 h-3.5 text-slate-400 ml-1" />
        )}
      </button>

      <Link
        href="/playground"
        className="px-3.5 py-2 text-xs font-medium text-slate-600 dark:text-slate-300 hover:text-[#D80621] dark:hover:text-red-400 transition-colors flex items-center gap-1"
      >
        Interactive Sandbox <ExternalLink className="w-3 h-3 text-slate-400" />
      </Link>
    </div>
  );
}

export function AnimatedCivicIllustration() {
  return (
    <div className="relative w-full max-w-md mx-auto my-6 p-6 rounded-3xl bg-gradient-to-b from-red-50/60 to-transparent dark:from-red-950/20 dark:to-transparent border border-black/5 dark:border-white/5 flex items-center justify-center">
      {/* Background Orbital Rings */}
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
        <div className="w-64 h-64 rounded-full border border-dashed border-red-300/40 dark:border-red-500/20 animate-spin" style={{ animationDuration: '40s' }} />
        <div className="absolute w-44 h-44 rounded-full border border-red-200/50 dark:border-red-500/10" />
      </div>

      {/* Central Engine Node */}
      <div className="relative z-10 text-center flex flex-col items-center">
        <div className="w-20 h-20 rounded-2xl bg-white dark:bg-slate-800 shadow-xl border border-red-200 dark:border-red-900/50 flex flex-col items-center justify-center animate-float">
          <span className="text-3xl">🍁</span>
          <span className="text-[10px] font-mono font-bold text-[#D80621] dark:text-red-400 mt-1">
            DuckDB 1.2
          </span>
        </div>

        {/* Floating Badges */}
        <div className="absolute -top-4 -left-12 px-2.5 py-1 rounded-lg bg-white dark:bg-slate-800 border border-black/10 dark:border-white/10 shadow text-[10px] font-mono text-emerald-700 dark:text-emerald-400 flex items-center gap-1">
          <Check className="w-3 h-3" /> StatCan WDS
        </div>

        <div className="absolute -top-4 -right-12 px-2.5 py-1 rounded-lg bg-white dark:bg-slate-800 border border-black/10 dark:border-white/10 shadow text-[10px] font-mono text-cyan-700 dark:text-cyan-400 flex items-center gap-1">
          <Zap className="w-3 h-3" /> BoC Valet
        </div>

        <div className="absolute -bottom-4 px-3 py-1 rounded-lg bg-white dark:bg-slate-800 border border-black/10 dark:border-white/10 shadow text-[10px] font-mono text-slate-800 dark:text-slate-200">
          242 MB → <span className="text-emerald-600 dark:text-emerald-400 font-bold">&lt; 3 KB</span>
        </div>
      </div>
    </div>
  );
}

export function HeroPreview() {
  const [activeTab, setActiveTab] = useState<'quickstart' | 'mcp' | 'orchestrator' | 'citation'>('quickstart');
  const [copied, setCopied] = useState(false);

  const snippets = {
    quickstart: {
      title: 'Quickstart CLI',
      filename: 'terminal.sh',
      code: `# 1. Zero-install run directly from the official MCP distribution repository
uvx --from "git+https://github.com/neobenjax/Canadian-Open-Data-Agentic-Platform-MCP-Server.git#subdirectory=packages/candata-mcp" candata-mcp

# 2. Or clone the standalone MCP distribution repo for local testing
git clone https://github.com/neobenjax/Canadian-Open-Data-Agentic-Platform-MCP-Server.git
cd Canadian-Open-Data-Agentic-Platform-MCP-Server
uv sync && uv run candata-mcp

# Note: For full multi-agent orchestration, see the monorepo:
# https://github.com/neobenjax/Canadian-Open-Data-Agentic-Platform`,
    },
    mcp: {
      title: 'MCP Manual Registry',
      filename: 'mcp_config.json (Claude / Cursor / Any MCP Client)',
      code: `{
  "mcpServers": {
    "candata-mcp": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/neobenjax/Canadian-Open-Data-Agentic-Platform-MCP-Server.git#subdirectory=packages/candata-mcp",
        "candata-mcp"
      ],
      "env": {
        "PYTHONUNBUFFERED": "1"
      }
    }
  }
}`,
    },
    orchestrator: {
      title: 'LangGraph Multi-Agent',
      filename: 'supervisor_agent.py',
      code: `# Multi-agent graph with DuckDB SQL Analyst & Citation Verifier
from candata_agent.supervisor import build_agent_graph

app = build_agent_graph(planner=planner, statcan=statcan, valet=valet, checkpointer=saver)

# Stream question through astream_events v2
async for event in app.astream_events(
    {"messages": [HumanMessage(content="Toronto shelter CPI year-over-year Aug 2026")]},
    version="v2",
):
    print(f"[{event['name']}] -> {event['data']}")`,
    },
    citation: {
      title: 'Citation Envelope',
      filename: 'citation_envelope.json',
      code: `{
  "claim": "Toronto Shelter CPI rose 4.8% YoY in August 2026",
  "citation": {
    "core": {
      "table_id": "18-10-0004-01",
      "vector_id": "v41692889",
      "reference_period": "2026-08"
    },
    "enrichment": {
      "release_time": "2026-09-15T08:30:00-04:00",
      "coordinate": "16.79.0.0.0.0.0.0.0.0",
      "status_code": "NORMAL",
      "quality_symbol": "A"
    },
    "verification_verdict": "PASS"
  }
}`,
    },
  };

  const current = snippets[activeTab];

  const handleCopy = () => {
    navigator.clipboard.writeText(current.code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="w-full max-w-4xl mx-auto mt-8 rounded-2xl border border-black/10 dark:border-white/10 bg-white/90 dark:bg-slate-900/90 shadow-xl backdrop-blur-xl overflow-hidden text-left font-mono text-xs">
      {/* Top Tab Bar */}
      <div className="px-4 py-3 bg-slate-100/70 dark:bg-slate-950/70 border-b border-black/5 dark:border-white/5 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-red-500/80 inline-block" />
          <span className="w-2.5 h-2.5 rounded-full bg-amber-500/80 inline-block" />
          <span className="w-2.5 h-2.5 rounded-full bg-emerald-500/80 inline-block" />
          <span className="text-slate-500 dark:text-slate-400 font-sans text-xs ml-2 font-medium">
            {current.filename}
          </span>
        </div>

        <div className="flex items-center bg-slate-200/80 dark:bg-slate-800/80 rounded-lg p-0.5">
          {(['quickstart', 'mcp', 'orchestrator', 'citation'] as const).map((key) => (
            <button
              key={key}
              onClick={() => setActiveTab(key)}
              className={`px-2.5 py-1 rounded-md text-[11px] font-sans transition-all ${
                activeTab === key
                  ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-white font-semibold shadow-sm'
                  : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
              }`}
            >
              {snippets[key].title}
            </button>
          ))}
        </div>

        <button
          onClick={handleCopy}
          className="px-2 py-1 rounded bg-slate-200/70 dark:bg-slate-800 text-slate-700 dark:text-slate-300 text-[11px] font-sans flex items-center gap-1 hover:bg-slate-300 dark:hover:bg-slate-700 transition-colors"
        >
          {copied ? <Check className="w-3 h-3 text-emerald-600" /> : <Copy className="w-3 h-3" />}
          <span>{copied ? 'Copied' : 'Copy'}</span>
        </button>
      </div>

      {/* Code Block */}
      <div className="p-4 overflow-x-auto text-slate-800 dark:text-slate-200 leading-relaxed font-mono">
        <pre className="text-xs">
          <code>{current.code}</code>
        </pre>
      </div>
    </div>
  );
}
