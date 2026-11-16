'use client';

import React from 'react';
import { ArrowRight, AlertTriangle, CheckCircle2, Database, Cpu, Sparkles, FileText } from 'lucide-react';

export function ArchitectureFlowDiagram() {
  return (
    <div className="my-8 p-6 rounded-2xl border border-black/10 dark:border-white/10 bg-slate-50/70 dark:bg-slate-900/60 shadow-sm backdrop-blur-sm not-prose">
      <div className="flex items-center justify-between mb-6 pb-3 border-b border-black/5 dark:border-white/5">
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-[#D80621] animate-pulse" />
          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300">
            CanData Civic Architecture: Traditional API Trap vs. High-Assurance Engine
          </h4>
        </div>
        <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-red-100 dark:bg-red-950/80 text-[#D80621] dark:text-red-300 font-semibold">
          FastMCP 2.0 + DuckDB 1.2
        </span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-center">
        {/* Step 1: LLM Agent */}
        <div className="lg:col-span-3 p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950/80 shadow-xs flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-mono font-medium text-slate-500 dark:text-slate-400">Step 1</span>
            <Cpu className="w-4 h-4 text-slate-600 dark:text-slate-400" />
          </div>
          <div className="text-sm font-bold text-slate-900 dark:text-slate-100">
            LLM Agent / User Query
          </div>
          <p className="text-xs text-slate-600 dark:text-slate-400">
            Claude Desktop, Cursor, or LangGraph asks for official Canadian statistics.
          </p>
          <div className="mt-1 text-[11px] font-mono p-1.5 rounded bg-slate-100 dark:bg-slate-900 text-slate-700 dark:text-slate-300">
            &ldquo;CPI shelter index YoY?&rdquo;
          </div>
        </div>

        {/* Transition Arrow 1 */}
        <div className="hidden lg:flex lg:col-span-1 justify-center text-slate-400 dark:text-slate-600">
          <ArrowRight className="w-5 h-5" />
        </div>

        {/* Step 2: The Core Decision Fork */}
        <div className="lg:col-span-8 flex flex-col gap-4">
          {/* Path A: Traditional API Pitfall (Red / Warning) */}
          <div className="p-3.5 rounded-xl border border-amber-300/60 dark:border-amber-800/60 bg-amber-50/60 dark:bg-amber-950/20 flex items-start gap-3">
            <div className="p-1.5 rounded-lg bg-amber-100 dark:bg-amber-900/50 text-amber-700 dark:text-amber-400 shrink-0 mt-0.5">
              <AlertTriangle className="w-4 h-4" />
            </div>
            <div className="flex-1">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-bold text-amber-900 dark:text-amber-200">
                  Legacy REST Approach: Monolithic SDMX / CSV Dump
                </span>
                <span className="text-[10px] font-mono text-amber-700 dark:text-amber-400 font-semibold">
                  ~200MB Uncompressed
                </span>
              </div>
              <p className="text-xs text-amber-800/80 dark:text-amber-300/70 mt-0.5">
                Full 40-year table payload sent to LLM &rarr; Exhausts 128k context window, creates silent temporal drift and hallucinated citations.
              </p>
            </div>
          </div>

          {/* Path B: CanData-MCP High-Assurance Engine (Green / Maple Red) */}
          <div className="p-3.5 rounded-xl border-2 border-red-500/30 dark:border-red-500/40 bg-white dark:bg-slate-950 shadow-sm flex items-start gap-3">
            <div className="p-1.5 rounded-lg bg-red-100 dark:bg-red-950 text-[#D80621] dark:text-red-400 shrink-0 mt-0.5">
              <Database className="w-4 h-4" />
            </div>
            <div className="flex-1">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-bold text-slate-900 dark:text-slate-100 flex items-center gap-1.5">
                  <span>CanData In-Memory DuckDB Slicing Engine</span>
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
                </span>
                <span className="text-[10px] font-mono text-emerald-700 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/60 px-2 py-0.5 rounded font-semibold">
                  &lt;3KB Typed Envelope
                </span>
              </div>
              <p className="text-xs text-slate-600 dark:text-slate-400 mt-1">
                Zero mental math. Executes deterministic C++ aggregations in-memory and binds every fact to a verifiable <strong>Core Verification Tuple</strong>:
              </p>
              <div className="mt-2 p-2 rounded-lg bg-slate-100/90 dark:bg-slate-900/90 font-mono text-[11px] text-slate-800 dark:text-slate-200 flex flex-wrap gap-x-4 gap-y-1">
                <span><strong className="text-red-700 dark:text-red-400">table_id:</strong> &quot;18-10-0004-01&quot;</span>
                <span><strong className="text-red-700 dark:text-red-400">vector_id:</strong> &quot;v41690973&quot;</span>
                <span><strong className="text-red-700 dark:text-red-400">ref_period:</strong> &quot;2026-09&quot;</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
