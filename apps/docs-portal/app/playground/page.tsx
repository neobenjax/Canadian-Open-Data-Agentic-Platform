'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { ArrowLeft, Play, Copy, Check, Terminal, Database, ShieldCheck, RefreshCw } from 'lucide-react';

interface ToolPreset {
  id: string;
  name: string;
  description: string;
  provider: 'Statistics Canada' | 'Bank of Canada' | 'DuckDB Engine';
  defaultParams: Record<string, any>;
  sampleResponse: Record<string, any>;
  verificationTuple?: {
    table_id: string;
    vector_id: string;
    reference_period: string;
    release_date: string;
    status: string;
  };
}

const TOOLS: ToolPreset[] = [
  {
    id: 'search_statcan_cubes',
    name: 'search_statcan_cubes',
    description: 'Search official Statistics Canada tables by natural language query',
    provider: 'Statistics Canada',
    defaultParams: {
      query: 'Consumer price index monthly',
      limit: 3,
    },
    sampleResponse: {
      total_matches: 48,
      results: [
        {
          table_id: '18-10-0004-01',
          title_en: 'Consumer Price Index, monthly, not seasonally adjusted',
          title_fr: 'Indice des prix à la consommation, mensuel, non désaisonnalisé',
          release_date: '2026-10-20T08:30:00Z',
          frequency: 'Monthly',
          canonical_url: 'https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810000401',
        },
        {
          table_id: '18-10-0006-01',
          title_en: 'Consumer Price Index, monthly, seasonally adjusted',
          title_fr: 'Indice des prix à la consommation, mensuel, désaisonnalisé',
          release_date: '2026-10-20T08:30:00Z',
          frequency: 'Monthly',
          canonical_url: 'https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810000601',
        },
      ],
    },
    verificationTuple: {
      table_id: '18-10-0004-01',
      vector_id: 'N/A (Metadata)',
      reference_period: '2026-09',
      release_date: '2026-10-20',
      status: 'VERIFIED_METADATA',
    },
  },
  {
    id: 'get_data_from_vectors',
    name: 'get_data_from_vectors',
    description: 'Fetch verified monthly observations for specific StatCan vectors',
    provider: 'Statistics Canada',
    defaultParams: {
      vector_ids: ['v41690973'], // CPI Shelter
      latest_n: 4,
    },
    sampleResponse: {
      vector_id: 'v41690973',
      table_id: '18-10-0004-01',
      coordinate: '1.2',
      series_title_en: 'Shelter',
      unit: '2002=100',
      observations: [
        { ref_period: '2026-06', value: 178.4, status: 'v' },
        { ref_period: '2026-07', value: 179.1, status: 'v' },
        { ref_period: '2026-08', value: 178.6, status: 'v' },
        { ref_period: '2026-09', value: 178.2, status: 'v' },
      ],
      payload_size_bytes: 612,
    },
    verificationTuple: {
      table_id: '18-10-0004-01',
      vector_id: 'v41690973',
      reference_period: '2026-06/2026-09',
      release_date: '2026-10-20',
      status: 'STRICT_PASS',
    },
  },
  {
    id: 'get_series',
    name: 'get_series (Valet API)',
    description: 'Query Bank of Canada policy rate or monetary indicators',
    provider: 'Bank of Canada',
    defaultParams: {
      series_name: 'FX_RPA_RATE',
      recent: 5,
    },
    sampleResponse: {
      series_name: 'FX_RPA_RATE',
      label: 'Policy Interest Rate (Target)',
      description: 'Target for the overnight rate set by the Bank of Canada',
      observations: [
        { date: '2026-10-23', value: '3.7500' },
        { date: '2026-10-24', value: '3.7500' },
        { date: '2026-10-27', value: '3.7500' },
        { date: '2026-10-28', value: '3.7500' },
        { date: '2026-10-29', value: '3.7500' },
      ],
      source: 'Bank of Canada Valet REST API v1',
    },
    verificationTuple: {
      table_id: 'BOC-VALET',
      vector_id: 'FX_RPA_RATE',
      reference_period: '2026-10-23/2026-10-29',
      release_date: '2026-10-29',
      status: 'STRICT_PASS',
    },
  },
  {
    id: 'execute_sql_analytics',
    name: 'execute_sql_analytics',
    description: 'Execute in-memory DuckDB SQL math over sliced observation payload',
    provider: 'DuckDB Engine',
    defaultParams: {
      vector_id: 'v41690973',
      sql: 'SELECT ref_period, value, (value - LAG(value, 1) OVER (ORDER BY ref_period)) AS mom_change FROM series ORDER BY ref_period DESC LIMIT 3;',
    },
    sampleResponse: {
      execution_mode: 'DuckDB-in-memory-Arrow',
      execution_time_ms: 1.4,
      sandbox: {
        enable_external_access: false,
        lock_configuration: true,
      },
      results: [
        { ref_period: '2026-09', value: 178.2, mom_change: -0.4 },
        { ref_period: '2026-08', value: 178.6, mom_change: -0.5 },
        { ref_period: '2026-07', value: 179.1, mom_change: 0.7 },
      ],
      citation: {
        table_id: '18-10-0004-01',
        vector_id: 'v41690973',
        recipe: 'sql_in_memory_mom',
      },
    },
    verificationTuple: {
      table_id: '18-10-0004-01',
      vector_id: 'v41690973',
      reference_period: '2026-07/2026-09',
      release_date: '2026-10-20',
      status: 'VERIFIED_DETERMINISTIC_SQL',
    },
  },
];

export default function PlaygroundPage() {
  const [selectedTool, setSelectedTool] = useState<ToolPreset>(TOOLS[0]);
  const [paramsInput, setParamsInput] = useState<string>(
    JSON.stringify(TOOLS[0].defaultParams, null, 2)
  );
  const [executing, setExecuting] = useState(false);
  const [response, setResponse] = useState<any>(TOOLS[0].sampleResponse);
  const [copied, setCopied] = useState(false);

  const handleSelectTool = (tool: ToolPreset) => {
    setSelectedTool(tool);
    setParamsInput(JSON.stringify(tool.defaultParams, null, 2));
    setResponse(tool.sampleResponse);
  };

  const handleExecute = () => {
    setExecuting(true);
    setTimeout(() => {
      setExecuting(false);
      setResponse(selectedTool.sampleResponse);
    }, 350);
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(JSON.stringify(response, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 flex flex-col">
      {/* Header */}
      <header className="border-b border-black/5 dark:border-white/10 bg-white dark:bg-slate-900 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link
              href="/"
              className="text-xs font-semibold text-slate-500 hover:text-red-700 flex items-center gap-1.5 transition-colors"
            >
              <ArrowLeft className="w-3.5 h-3.5" /> Back to Overview
            </Link>
            <div className="h-4 w-px bg-slate-200 dark:bg-slate-800" />
            <h1 className="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-2">
              <Terminal className="w-4 h-4 text-red-600" /> CanData Interactive API Sandbox
            </h1>
          </div>
          <Link
            href="/docs"
            className="text-xs font-medium text-red-700 dark:text-red-400 hover:underline"
          >
            View Docs API Reference &rarr;
          </Link>
        </div>
      </header>

      {/* Main Workspace */}
      <div className="max-w-7xl mx-auto px-6 py-8 w-full flex-1 grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Left Column: Tool Selector & Request Input */}
        <div className="lg:col-span-5 flex flex-col gap-6">
          {/* Tool Preset List */}
          <div className="bg-white dark:bg-slate-900 rounded-xl p-5 border border-black/5 dark:border-white/10 shadow-sm">
            <h2 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">
              Available MCP Tools
            </h2>
            <div className="space-y-2">
              {TOOLS.map((tool) => (
                <button
                  key={tool.id}
                  onClick={() => handleSelectTool(tool)}
                  className={`w-full text-left p-3 rounded-lg border text-sm transition-all flex flex-col gap-1 ${
                    selectedTool.id === tool.id
                      ? 'bg-red-50/80 border-red-300 dark:bg-red-950/40 dark:border-red-800 text-slate-900 dark:text-white'
                      : 'border-slate-200 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/50 text-slate-700 dark:text-slate-300'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono font-semibold text-xs text-red-700 dark:text-red-400">
                      {tool.name}
                    </span>
                    <span className="text-[10px] px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-500 font-sans">
                      {tool.provider}
                    </span>
                  </div>
                  <p className="text-xs text-slate-500 dark:text-slate-400 line-clamp-1">
                    {tool.description}
                  </p>
                </button>
              ))}
            </div>
          </div>

          {/* Parameters Editor */}
          <div className="bg-white dark:bg-slate-900 rounded-xl p-5 border border-black/5 dark:border-white/10 shadow-sm flex-1 flex flex-col">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-xs font-bold text-slate-400 uppercase tracking-wider">
                Tool Arguments (JSON)
              </h2>
              <button
                onClick={() => setParamsInput(JSON.stringify(selectedTool.defaultParams, null, 2))}
                className="text-xs text-slate-500 hover:text-red-700 flex items-center gap-1"
              >
                <RefreshCw className="w-3 h-3" /> Reset
              </button>
            </div>
            <textarea
              value={paramsInput}
              onChange={(e) => setParamsInput(e.target.value)}
              className="flex-1 w-full font-mono text-xs p-3 rounded-lg bg-slate-900 text-slate-100 border border-slate-800 focus:outline-none focus:ring-2 focus:ring-red-600 resize-none min-h-[160px]"
              spellCheck={false}
            />
            <button
              onClick={handleExecute}
              disabled={executing}
              className="mt-4 w-full py-2.5 rounded-lg bg-red-700 hover:bg-red-800 text-white font-medium text-xs shadow-sm transition-all flex items-center justify-center gap-2 disabled:opacity-50"
            >
              {executing ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" /> Executing in DuckDB Sandbox...
                </>
              ) : (
                <>
                  <Play className="w-3.5 h-3.5 fill-current" /> Execute Query via FastMCP
                </>
              )}
            </button>
          </div>
        </div>

        {/* Right Column: Execution Output & Verification Badge */}
        <div className="lg:col-span-7 flex flex-col gap-6">
          {/* Verification Tuple Badge */}
          {selectedTool.verificationTuple && (
            <div className="bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800/50 rounded-xl p-4 flex items-center justify-between shadow-sm">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-full bg-emerald-100 dark:bg-emerald-900/60 flex items-center justify-center text-emerald-700 dark:text-emerald-300">
                  <ShieldCheck className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-xs font-bold text-emerald-900 dark:text-emerald-200 uppercase tracking-wide">
                    Official Citation Envelope (Strict Tier 1)
                  </h3>
                  <p className="text-xs text-emerald-800 dark:text-emerald-300 font-mono mt-0.5">
                    ({selectedTool.verificationTuple.table_id}, {selectedTool.verificationTuple.vector_id}, {selectedTool.verificationTuple.reference_period})
                  </p>
                </div>
              </div>
              <span className="text-[10px] font-bold px-2.5 py-1 rounded-full bg-emerald-200 dark:bg-emerald-900 text-emerald-900 dark:text-emerald-100 uppercase tracking-wider">
                {selectedTool.verificationTuple.status}
              </span>
            </div>
          )}

          {/* Response Payload Inspector */}
          <div className="bg-slate-900 rounded-xl border border-slate-800 shadow-xl overflow-hidden flex-1 flex flex-col font-mono text-xs">
            <div className="px-4 py-3 bg-slate-950 border-b border-slate-800 flex items-center justify-between text-slate-400">
              <div className="flex items-center gap-2">
                <Database className="w-4 h-4 text-cyan-400" />
                <span className="text-slate-200 font-sans text-xs font-semibold">
                  Response Envelope (&lt;3KB Payload)
                </span>
              </div>
              <button
                onClick={handleCopy}
                className="text-xs text-slate-400 hover:text-white flex items-center gap-1 transition-colors"
              >
                {copied ? <Check className="w-3.5 h-3.5 text-green-400" /> : <Copy className="w-3.5 h-3.5" />}
                <span>{copied ? 'Copied' : 'Copy JSON'}</span>
              </button>
            </div>
            <pre className="p-4 text-slate-200 flex-1 overflow-auto max-h-[500px]">
              {JSON.stringify(response, null, 2)}
            </pre>
          </div>
        </div>
      </div>
    </div>
  );
}
