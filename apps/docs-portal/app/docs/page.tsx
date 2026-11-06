import React from 'react';
import Link from 'next/link';
import { ArrowRight, Terminal, Database, CheckCircle2 } from 'lucide-react';

export default function DocsIndexPage() {
  return (
    <div className="space-y-8">
      <div>
        <span className="text-xs font-bold text-red-700 dark:text-red-400 uppercase tracking-wider">
          CanData-MCP Documentation
        </span>
        <h1 className="text-3xl font-extrabold text-slate-900 dark:text-white mt-1 mb-4 font-heading">
          Canadian Open Data Agentic Platform
        </h1>
        <p className="text-base text-slate-600 dark:text-slate-300 leading-relaxed">
          Welcome to the developer documentation for the <strong>Canadian Open Data Agentic Platform (`CanData-MCP`)</strong>. This platform provides an auditable, sub-second civic data intelligence layer bridging frontier AI reasoning with official Canadian public data sources.
        </p>
      </div>

      {/* Feature callout */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 not-prose">
        <Link
          href="/docs/quickstart"
          className="p-5 rounded-xl border border-slate-200 dark:border-slate-800 hover:border-red-500/50 hover:bg-red-50/20 dark:hover:bg-red-950/20 transition-all block group"
        >
          <div className="flex items-center justify-between mb-2">
            <span className="font-bold text-slate-900 dark:text-white text-sm flex items-center gap-2">
              <Terminal className="w-4 h-4 text-red-600" /> Quickstart Guide
            </span>
            <ArrowRight className="w-4 h-4 text-slate-400 group-hover:text-red-600 transition-colors" />
          </div>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Install and run the FastMCP server in under 60 seconds with Astral uv.
          </p>
        </Link>

        <Link
          href="/docs/claude-desktop"
          className="p-5 rounded-xl border border-slate-200 dark:border-slate-800 hover:border-red-500/50 hover:bg-red-50/20 dark:hover:bg-red-950/20 transition-all block group"
        >
          <div className="flex items-center justify-between mb-2">
            <span className="font-bold text-slate-900 dark:text-white text-sm flex items-center gap-2">
              <Database className="w-4 h-4 text-red-600" /> Client Integrations
            </span>
            <ArrowRight className="w-4 h-4 text-slate-400 group-hover:text-red-600 transition-colors" />
          </div>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Configure Claude Desktop, Cursor Composer, and custom LangGraph agents.
          </p>
        </Link>
      </div>

      <div className="border-t border-slate-100 dark:border-slate-800 pt-6">
        <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-4">
          Guaranteed Guardrails
        </h2>
        <ul className="space-y-3 not-prose text-sm text-slate-700 dark:text-slate-300">
          <li className="flex items-start gap-2.5">
            <CheckCircle2 className="w-4 h-4 text-green-600 shrink-0 mt-0.5" />
            <span><strong>No Hallucinated Identifiers:</strong> Vectors and table IDs verified against live WDS and Valet APIs.</span>
          </li>
          <li className="flex items-start gap-2.5">
            <CheckCircle2 className="w-4 h-4 text-green-600 shrink-0 mt-0.5" />
            <span><strong>Strict Core Verification Tuples:</strong> <code>(table_id, vector_id, reference_period)</code> verified before answering.</span>
          </li>
          <li className="flex items-start gap-2.5">
            <CheckCircle2 className="w-4 h-4 text-green-600 shrink-0 mt-0.5" />
            <span><strong>Zero Mental Math:</strong> All arithmetic performed via deterministic DuckDB SQL recipes in C++.</span>
          </li>
          <li className="flex items-start gap-2.5">
            <CheckCircle2 className="w-4 h-4 text-green-600 shrink-0 mt-0.5" />
            <span><strong>Context Clamping:</strong> Multi-megabyte payloads clamped to &lt;3KB observation envelopes.</span>
          </li>
        </ul>
      </div>
    </div>
  );
}
