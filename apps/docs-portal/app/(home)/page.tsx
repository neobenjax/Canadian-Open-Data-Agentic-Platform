import Link from 'next/link';
import { ArrowRight, Terminal, Database, ShieldCheck, Zap, Layers, Sparkles } from 'lucide-react';

export default function HomePage() {
  return (
    <main className="min-h-screen flex flex-col justify-between">
      {/* Navigation */}
      <header className="border-b border-black/5 dark:border-white/10 bg-white/70 dark:bg-slate-900/70 backdrop-blur-md sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-xl font-extrabold tracking-tight text-red-700 dark:text-red-500 font-heading">
              🍁 CanData<span className="text-slate-900 dark:text-white">-MCP</span>
            </span>
            <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300">
              v1.0.0 FastMCP
            </span>
          </div>
          <nav className="flex items-center gap-6 text-sm font-medium">
            <Link href="/docs" className="text-slate-600 dark:text-slate-300 hover:text-red-600 transition-colors">
              Docs
            </Link>
            <Link href="/playground" className="text-slate-600 dark:text-slate-300 hover:text-red-600 transition-colors">
              Playground
            </Link>
            <Link
              href="https://github.com/neobenjax/Canadian-Open-Data-Agentic-Platform"
              target="_blank"
              className="text-slate-600 dark:text-slate-300 hover:text-red-600 transition-colors"
            >
              GitHub
            </Link>
            <Link
              href="/docs"
              className="px-4 py-2 rounded-lg bg-red-700 hover:bg-red-800 text-white font-medium text-xs shadow-sm transition-all flex items-center gap-1.5"
            >
              Get Started <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </nav>
        </div>
      </header>

      {/* Hero Section */}
      <section className="py-20 px-6 max-w-7xl mx-auto text-center flex-1 flex flex-col items-center justify-center">
        <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-red-50 border border-red-200 dark:bg-red-950/50 dark:border-red-900 mb-8">
          <Sparkles className="w-4 h-4 text-red-600 dark:text-red-400" />
          <span className="text-xs font-medium text-red-900 dark:text-red-200">
            FastMCP 2.0 + DuckDB 1.2 In-Memory Slicing Engine
          </span>
        </div>

        <h1 className="text-4xl sm:text-6xl font-extrabold tracking-tight text-slate-900 dark:text-white max-w-4xl font-heading leading-tight mb-6">
          Auditable Canadian Civic Data Intelligence for <span className="text-red-700 dark:text-red-500">AI Agents</span>
        </h1>

        <p className="text-lg text-slate-600 dark:text-slate-300 max-w-2xl mb-10 leading-relaxed">
          Zero-hallucination MCP server and multi-agent suite streaming 200MB Statistics Canada, Bank of Canada, and federal CKAN datasets into tight &lt;3KB verified payloads with cryptographic verification tuples.
        </p>

        {/* Quick Commands Terminal */}
        <div className="w-full max-w-2xl bg-slate-900 text-left rounded-xl shadow-xl overflow-hidden border border-slate-800 mb-10 font-mono text-xs">
          <div className="px-4 py-2.5 bg-slate-950/80 border-b border-slate-800 flex items-center justify-between text-slate-400">
            <div className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-full bg-red-500/80 inline-block" />
              <span className="w-3 h-3 rounded-full bg-yellow-500/80 inline-block" />
              <span className="w-3 h-3 rounded-full bg-green-500/80 inline-block" />
              <span className="ml-2 text-xs font-sans text-slate-300">Terminal — Quick Installation</span>
            </div>
            <span>bash</span>
          </div>
          <div className="p-4 space-y-2 text-slate-200">
            <p className="text-slate-400"># Install and start CanData-MCP via uv</p>
            <p><span className="text-green-400">$</span> uv sync</p>
            <p><span className="text-green-400">$</span> uv run candata-mcp</p>
            <p className="text-slate-400 mt-2"># Connect to Claude Desktop or Cursor stdio</p>
            <p className="text-cyan-300">✓ FastMCP 2.0 server listening on stdio (5 tools registered)</p>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex flex-wrap items-center justify-center gap-4">
          <Link
            href="/docs"
            className="px-6 py-3 rounded-lg bg-red-700 hover:bg-red-800 text-white font-medium text-sm shadow-md transition-all flex items-center gap-2"
          >
            Explore Developer Docs <ArrowRight className="w-4 h-4" />
          </Link>
          <Link
            href="/playground"
            className="px-6 py-3 rounded-lg bg-white dark:bg-slate-800 hover:bg-slate-50 dark:hover:bg-slate-700 text-slate-900 dark:text-white font-medium text-sm border border-slate-200 dark:border-slate-700 shadow-sm transition-all flex items-center gap-2"
          >
            <Terminal className="w-4 h-4" /> Open Interactive Playground
          </Link>
        </div>
      </section>

      {/* Feature Grid */}
      <section className="bg-slate-100/70 dark:bg-slate-900/40 border-t border-black/5 dark:border-white/5 py-16 px-6">
        <div className="max-w-7xl mx-auto grid grid-cols-1 md:grid-cols-3 gap-8">
          <div className="p-6 rounded-xl bg-white dark:bg-slate-800/80 border border-black/5 dark:border-white/5 shadow-sm">
            <div className="w-10 h-10 rounded-lg bg-red-100 dark:bg-red-950 flex items-center justify-center text-red-700 dark:text-red-400 mb-4">
              <Database className="w-5 h-5" />
            </div>
            <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-2 font-heading">
              In-Memory DuckDB 1.2
            </h3>
            <p className="text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
              Streams raw Apache Arrow payloads directly in memory, reducing multi-megabyte public datasets to sub-3KB verified answer slices.
            </p>
          </div>

          <div className="p-6 rounded-xl bg-white dark:bg-slate-800/80 border border-black/5 dark:border-white/5 shadow-sm">
            <div className="w-10 h-10 rounded-lg bg-red-100 dark:bg-red-950 flex items-center justify-center text-red-700 dark:text-red-400 mb-4">
              <ShieldCheck className="w-5 h-5" />
            </div>
            <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-2 font-heading">
              Citation Envelopes
            </h3>
            <p className="text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
              Every data point binds to a strict Core Verification Tuple (table, vector, reference period) with publisher release date validation.
            </p>
          </div>

          <div className="p-6 rounded-xl bg-white dark:bg-slate-800/80 border border-black/5 dark:border-white/5 shadow-sm">
            <div className="w-10 h-10 rounded-lg bg-red-100 dark:bg-red-950 flex items-center justify-center text-red-700 dark:text-red-400 mb-4">
              <Layers className="w-5 h-5" />
            </div>
            <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-2 font-heading">
              LangGraph Orchestration
            </h3>
            <p className="text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
              Decomposes questions across Supervisor, Analyst, and Citation Verifier sub-agents with full OpenTelemetry tracing in LangSmith &amp; Phoenix.
            </p>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-black/5 dark:border-white/10 py-8 px-6 text-center text-xs text-slate-500">
        <p>Canadian Open Data Agentic Platform · Open Source Apache-2.0 License</p>
      </footer>
    </main>
  );
}
