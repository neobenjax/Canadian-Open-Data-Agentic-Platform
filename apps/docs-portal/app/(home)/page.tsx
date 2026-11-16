import Link from 'next/link';
import {
  ArrowRight,
  Terminal,
  Database,
  ShieldCheck,
  Zap,
  Layers,
  Sparkles,
  ExternalLink,
  Cpu,
  Activity,
  Globe,
  CheckCircle2,
  Server,
  Lock,
} from 'lucide-react';
import { QuickstartPill, AnimatedCivicIllustration, HeroPreview } from './hero-preview';

export default function HomePage() {
  return (
    <main className="min-h-screen flex flex-col justify-between bg-[#FDFCFB] dark:bg-[#0B0F19] text-slate-900 dark:text-slate-100 selection:bg-red-100 dark:selection:bg-red-900/50 selection:text-red-900 relative">
      {/* Background Subtle Grid / Celestial Glow (contained overflow) */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none -z-10">
        <div className="absolute inset-0 bg-[radial-gradient(#e5e7eb_1px,transparent_1px)] dark:bg-[radial-gradient(#1f2937_1px,transparent_1px)] [background-size:24px_24px] opacity-60" />
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[700px] h-[350px] bg-red-500/10 dark:bg-red-600/10 blur-[120px]" />
      </div>

      {/* Navigation Header (Sticky on top while scrolling) */}
      <header className="border-b border-black/5 dark:border-white/10 bg-[#FDFCFB]/90 dark:bg-[#0B0F19]/90 backdrop-blur-md sticky top-0 z-50 m-0 p-0 shadow-xs">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link href="/" className="text-xl font-extrabold tracking-tight font-heading flex items-center gap-2 hover:opacity-90 transition-opacity">
              <span className="text-2xl">🍁</span>
              <span>
                CanData<span className="text-[#D80621]"> -MCP</span>
              </span>
            </Link>
            <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-red-100 text-[#D80621] dark:bg-red-950/80 dark:border dark:border-red-800/70 dark:text-red-300">
              Beta v0.5.0
            </span>
          </div>

          <nav className="flex items-center gap-5 text-xs sm:text-sm font-medium">
            <Link
              href="/docs"
              className="text-slate-600 dark:text-slate-300 hover:text-[#D80621] dark:hover:text-white transition-colors"
            >
              Documentation
            </Link>
            <Link
              href="/playground"
              className="text-slate-600 dark:text-slate-300 hover:text-[#D80621] dark:hover:text-white transition-colors hidden sm:inline-block"
            >
              Playground
            </Link>
            <Link
              href="https://candata-agent.streamlit.app"
              target="_blank"
              className="text-emerald-700 dark:text-emerald-400 hover:text-emerald-800 transition-colors hidden md:flex items-center gap-1 font-mono text-xs"
            >
              <Activity className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
              Streamlit Demo
            </Link>
            <Link
              href="https://github.com/neobenjax/Canadian-Open-Data-Agentic-Platform-MCP-Server"
              target="_blank"
              className="text-slate-600 dark:text-slate-300 hover:text-[#D80621] dark:hover:text-white transition-colors flex items-center gap-1"
              title="Official Standalone MCP Server Repository"
            >
              MCP Server <ExternalLink className="w-3 h-3 text-slate-400" />
            </Link>
            <Link
              href="https://github.com/neobenjax/Canadian-Open-Data-Agentic-Platform"
              target="_blank"
              className="text-slate-600 dark:text-slate-300 hover:text-[#D80621] dark:hover:text-white transition-colors hidden lg:flex items-center gap-1"
              title="Full Platform Monorepo"
            >
              Monorepo <ExternalLink className="w-3 h-3 text-slate-400" />
            </Link>
            <Link
              href="/docs"
              className="px-4 py-2 rounded-xl bg-[#D80621] hover:bg-[#A82424] text-white font-medium text-xs shadow-md transition-all flex items-center gap-1.5"
            >
              Get Started <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </nav>
        </div>
      </header>

      {/* Hero Section (Fumadocs.dev Style) */}
      <section className="pt-16 pb-12 px-6 max-w-5xl mx-auto text-center flex flex-col items-center justify-center relative">
        {/* Animated Headline */}
        <h1 className="text-4xl sm:text-6xl lg:text-7xl font-extrabold tracking-tight text-slate-900 dark:text-white font-heading leading-[1.08] mb-6">
          Auditable Canadian civic data,{' '}
          <span className="text-[#D80621]">in seconds.</span>
        </h1>

        {/* Subtitle */}
        <p className="text-base sm:text-lg text-slate-600 dark:text-slate-300 max-w-2xl mb-8 leading-relaxed font-sans">
          Zero-hallucination FastMCP 2.0 server & LangGraph multi-agent suite streaming 200MB
          Statistics Canada, Bank of Canada, and federal CKAN datasets into tight sub-3KB verified
          payloads with cryptographic two-tier citation envelopes.
        </p>

        {/* Quickstart Install Pill & Action CTA (Matching Fumadocs.dev) */}
        <QuickstartPill />

        <div className="mt-4 text-xs text-slate-500 dark:text-slate-400 font-sans">
          Runs on <span className="font-semibold text-slate-700 dark:text-slate-300">FastMCP 2.0</span> ·{' '}
          <span className="font-semibold text-slate-700 dark:text-slate-300">Claude Desktop</span> ·{' '}
          <span className="font-semibold text-slate-700 dark:text-slate-300">Cursor</span> ·{' '}
          <span className="font-semibold text-slate-700 dark:text-slate-300">LangGraph Multi-Agent</span>
        </div>

        {/* Celestial / Planetary Data Engine Illustration (Fumadocs Style) */}
        <AnimatedCivicIllustration />

        {/* Interactive Code Showcase */}
        <HeroPreview />
      </section>

      {/* Live Metrics Counter Bar */}
      <section className="border-y border-black/5 dark:border-white/10 bg-slate-100/60 dark:bg-slate-900/60 py-8 px-6 my-6">
        <div className="max-w-6xl mx-auto grid grid-cols-2 md:grid-cols-4 gap-6 text-center">
          <div className="p-3">
            <div className="text-3xl sm:text-4xl font-extrabold text-[#D80621] font-mono mb-1">
              &lt; 3 KB
            </div>
            <div className="text-xs text-slate-500 dark:text-slate-400 uppercase tracking-wider font-sans">
              Payload Size (from 200MB)
            </div>
          </div>
          <div className="p-3 border-l border-black/5 dark:border-white/10">
            <div className="text-3xl sm:text-4xl font-extrabold text-emerald-600 dark:text-emerald-400 font-mono mb-1">
              0
            </div>
            <div className="text-xs text-slate-500 dark:text-slate-400 uppercase tracking-wider font-sans">
              Hallucinated Series
            </div>
          </div>
          <div className="p-3 border-l border-black/5 dark:border-white/10">
            <div className="text-3xl sm:text-4xl font-extrabold text-cyan-600 dark:text-cyan-400 font-mono mb-1">
              100%
            </div>
            <div className="text-xs text-slate-500 dark:text-slate-400 uppercase tracking-wider font-sans">
              Citation Provenance
            </div>
          </div>
          <div className="p-3 border-l border-black/5 dark:border-white/10">
            <div className="text-3xl sm:text-4xl font-extrabold text-amber-600 dark:text-amber-400 font-mono mb-1">
              3
            </div>
            <div className="text-xs text-slate-500 dark:text-slate-400 uppercase tracking-wider font-sans">
              Official Federal APIs
            </div>
          </div>
        </div>
      </section>

      {/* Bento Grid Feature Section */}
      <section className="py-16 px-6 max-w-6xl mx-auto w-full">
        <div className="text-center mb-12">
          <h2 className="text-xs font-bold uppercase tracking-widest text-[#D80621] mb-2 font-mono">
            Platform Capabilities
          </h2>
          <h3 className="text-3xl sm:text-4xl font-extrabold text-slate-900 dark:text-white font-heading">
            Engineered for Ground-Truth Truthfulness
          </h3>
          <p className="text-slate-600 dark:text-slate-300 text-sm max-w-2xl mx-auto mt-3">
            Every architectural decision eliminates silent drift, catches data revisions, and provides
            verifiable lineage back to official Canadian publications.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Card 1: Wide Card */}
          <div className="md:col-span-2 p-8 rounded-3xl bg-white dark:bg-slate-900 border border-black/5 dark:border-white/10 hover:border-[#D80621]/30 transition-all flex flex-col justify-between shadow-sm hover:shadow-md">
            <div>
              <div className="w-11 h-11 rounded-2xl bg-red-50 dark:bg-red-950/60 border border-red-200 dark:border-red-900/40 flex items-center justify-center text-[#D80621] dark:text-red-400 mb-5">
                <Database className="w-5 h-5" />
              </div>
              <h4 className="text-xl font-bold text-slate-900 dark:text-white mb-2 font-heading">
                In-Memory DuckDB 1.2+ Arrow Streaming Engine
              </h4>
              <p className="text-sm text-slate-600 dark:text-slate-300 leading-relaxed max-w-2xl mb-6">
                Reduces massive Statistics Canada SDMX data cubes and Bank of Canada time-series
                directly in RAM. Eliminates LLM mental math by executing exact aggregate SQL in
                strictly sandboxed, read-only memory spaces.
              </p>
            </div>
            <div className="grid grid-cols-3 gap-4 pt-4 border-t border-black/5 dark:border-white/5 text-xs font-mono">
              <div>
                <span className="text-slate-400 block">Reduction</span>
                <span className="text-emerald-600 dark:text-emerald-400 font-semibold">99.9% Payload Savings</span>
              </div>
              <div>
                <span className="text-slate-400 block">Sandbox</span>
                <span className="text-cyan-600 dark:text-cyan-400 font-semibold">Zero-Trust Memory</span>
              </div>
              <div>
                <span className="text-slate-400 block">Interface</span>
                <span className="text-slate-600 dark:text-slate-300 font-semibold">Apache Arrow IPC</span>
              </div>
            </div>
          </div>

          {/* Card 2: Citation Envelopes */}
          <div className="p-8 rounded-3xl bg-white dark:bg-slate-900 border border-black/5 dark:border-white/10 hover:border-emerald-500/30 transition-all flex flex-col justify-between shadow-sm hover:shadow-md">
            <div>
              <div className="w-11 h-11 rounded-2xl bg-emerald-50 dark:bg-emerald-950/60 border border-emerald-200 dark:border-emerald-900/40 flex items-center justify-center text-emerald-600 dark:text-emerald-400 mb-5">
                <ShieldCheck className="w-5 h-5" />
              </div>
              <h4 className="text-xl font-bold text-slate-900 dark:text-white mb-2 font-heading">
                Two-Tier Citation Envelopes
              </h4>
              <p className="text-sm text-slate-600 dark:text-slate-300 leading-relaxed mb-6">
                Tier 1 enforces mandatory verification tuples{' '}
                <code className="text-[#D80621] bg-slate-100 dark:bg-slate-800 px-1 py-0.5 rounded text-xs font-mono">
                  (table_id, vector_id, reference_period)
                </code>
                . Tier 2 carries data quality grades (A-F), confidentiality flags, and revision timestamps.
              </p>
            </div>
            <div className="flex items-center gap-2 text-xs text-emerald-700 dark:text-emerald-400 font-medium">
              <CheckCircle2 className="w-4 h-4" /> Passed NIST &amp; DeepEval CI Suites
            </div>
          </div>

          {/* Card 3: 3 Federal Connectors */}
          <div className="p-8 rounded-3xl bg-white dark:bg-slate-900 border border-black/5 dark:border-white/10 hover:border-cyan-500/30 transition-all flex flex-col justify-between shadow-sm hover:shadow-md">
            <div>
              <div className="w-11 h-11 rounded-2xl bg-cyan-50 dark:bg-cyan-950/60 border border-cyan-200 dark:border-cyan-900/40 flex items-center justify-center text-cyan-600 dark:text-cyan-400 mb-5">
                <Globe className="w-5 h-5" />
              </div>
              <h4 className="text-xl font-bold text-slate-900 dark:text-white mb-2 font-heading">
                3 Federal REST Connectors
              </h4>
              <p className="text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
                Async HTTPX clients for Statistics Canada WDS, Bank of Canada Valet, and Open
                Government Canada CKAN DataStore with automatic 409 maintenance window defense.
              </p>
            </div>
            <div className="mt-6 flex flex-wrap gap-2 text-[11px] font-mono">
              <span className="px-2 py-1 rounded bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300">
                StatCan WDS
              </span>
              <span className="px-2 py-1 rounded bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300">
                BoC Valet
              </span>
              <span className="px-2 py-1 rounded bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300">
                CKAN Federal
              </span>
            </div>
          </div>

          {/* Card 4: LangGraph Multi-Agent */}
          <div className="p-8 rounded-3xl bg-white dark:bg-slate-900 border border-black/5 dark:border-white/10 hover:border-amber-500/30 transition-all flex flex-col justify-between shadow-sm hover:shadow-md">
            <div>
              <div className="w-11 h-11 rounded-2xl bg-amber-50 dark:bg-amber-950/60 border border-amber-200 dark:border-amber-900/40 flex items-center justify-center text-amber-600 dark:text-amber-400 mb-5">
                <Cpu className="w-5 h-5" />
              </div>
              <h4 className="text-xl font-bold text-slate-900 dark:text-white mb-2 font-heading">
                LangGraph Multi-Agent Team
              </h4>
              <p className="text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
                Autonomous coordination between Supervisor, Query Planner, Data Analyst, and Citation
                Verifier nodes with Human-in-the-Loop (HITL) breakpoints for geographic boundary ambiguity.
              </p>
            </div>
            <div className="mt-6 text-xs text-amber-700 dark:text-amber-400 font-mono flex items-center gap-1.5">
              <Zap className="w-4 h-4" /> Time-Travel SQLite Checkpointer
            </div>
          </div>

          {/* Card 5: Security & Guardrails */}
          <div className="p-8 rounded-3xl bg-white dark:bg-slate-900 border border-black/5 dark:border-white/10 hover:border-purple-500/30 transition-all flex flex-col justify-between shadow-sm hover:shadow-md">
            <div>
              <div className="w-11 h-11 rounded-2xl bg-purple-50 dark:bg-purple-950/60 border border-purple-200 dark:border-purple-900/40 flex items-center justify-center text-purple-600 dark:text-purple-400 mb-5">
                <Lock className="w-5 h-5" />
              </div>
              <h4 className="text-xl font-bold text-slate-900 dark:text-white mb-2 font-heading">
                Zero-Trust Guardrails
              </h4>
              <p className="text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
                Pydantic v2 schemas defeat prompt injection, driver-level DuckDB flags block
                arbitrary file reads, and container root filesystems are locked read-only.
              </p>
            </div>
            <div className="mt-6 text-xs text-purple-700 dark:text-purple-400 font-mono">
              UID 10001 Hardened Containers
            </div>
          </div>
        </div>
      </section>

      {/* Cloud Deployment Banner */}
      <section className="py-12 px-6 max-w-6xl mx-auto w-full">
        <div className="p-8 sm:p-12 rounded-3xl bg-gradient-to-r from-red-50 via-white to-slate-50 dark:from-red-950/30 dark:via-slate-900 dark:to-slate-950 border border-black/5 dark:border-white/10 shadow-sm relative overflow-hidden">
          <div className="max-w-2xl">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-red-100 dark:bg-red-950/80 text-[#D80621] dark:text-red-300 text-xs font-mono mb-4">
              <Server className="w-3.5 h-3.5" /> Production Cloud Hosting
            </div>
            <h3 className="text-2xl sm:text-3xl font-extrabold text-slate-900 dark:text-white font-heading mb-3">
              Deployable in Seconds via Vercel &amp; Streamlit Cloud
            </h3>
            <p className="text-slate-600 dark:text-slate-300 text-sm leading-relaxed mb-6">
              Explore the documentation on Vercel at{' '}
              <code className="text-[#D80621] dark:text-red-400 bg-white dark:bg-slate-800 px-2 py-0.5 rounded border border-black/5 dark:border-white/5 font-mono">
                candata.vercel.app
              </code>{' '}
              or test live queries on the interactive Streamlit analytics app at{' '}
              <code className="text-emerald-700 dark:text-emerald-400 bg-white dark:bg-slate-800 px-2 py-0.5 rounded border border-black/5 dark:border-white/5 font-mono">
                candata-agent.streamlit.app
              </code>
              .
            </p>
            <div className="flex flex-wrap items-center gap-3">
              <Link
                href="/docs"
                className="px-5 py-2.5 rounded-xl bg-[#D80621] hover:bg-[#A82424] text-white font-semibold text-xs shadow-md transition-all flex items-center gap-2"
              >
                Read Deployment Guide <ArrowRight className="w-3.5 h-3.5" />
              </Link>
              <Link
                href="https://github.com/neobenjax/Canadian-Open-Data-Agentic-Platform-MCP-Server"
                target="_blank"
                className="px-5 py-2.5 rounded-xl bg-white dark:bg-slate-800 hover:bg-slate-50 dark:hover:bg-slate-700 text-slate-800 dark:text-slate-200 font-semibold text-xs border border-black/10 dark:border-white/10 transition-all flex items-center gap-2"
              >
                MCP Server Repo <ExternalLink className="w-3.5 h-3.5 text-slate-400" />
              </Link>
              <Link
                href="https://github.com/neobenjax/Canadian-Open-Data-Agentic-Platform"
                target="_blank"
                className="px-5 py-2.5 rounded-xl bg-white dark:bg-slate-800 hover:bg-slate-50 dark:hover:bg-slate-700 text-slate-800 dark:text-slate-200 font-semibold text-xs border border-black/10 dark:border-white/10 transition-all flex items-center gap-2"
              >
                Full Monorepo <ExternalLink className="w-3.5 h-3.5 text-slate-400" />
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-black/5 dark:border-white/10 py-8 px-6 text-center text-xs text-slate-500 bg-white/50 dark:bg-slate-950/50">
        <div className="max-w-6xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <span className="text-lg">🍁</span>
            <span className="text-slate-700 dark:text-slate-300 font-semibold font-heading">
              Canadian Open Data Agentic Platform
            </span>
            <span className="text-slate-400">·</span>
            <span>Apache-2.0 License</span>
          </div>
          <div className="flex items-center gap-6">
            <Link href="/docs" className="hover:text-slate-800 dark:hover:text-slate-200 transition-colors">
              Docs
            </Link>
            <Link href="/playground" className="hover:text-slate-800 dark:hover:text-slate-200 transition-colors">
              Playground
            </Link>
            <Link
              href="https://candata-agent.streamlit.app"
              target="_blank"
              className="hover:text-emerald-600 transition-colors"
            >
              Streamlit Demo
            </Link>
            <Link
              href="https://github.com/neobenjax/Canadian-Open-Data-Agentic-Platform-MCP-Server"
              target="_blank"
              className="hover:text-slate-800 dark:hover:text-slate-200 transition-colors"
            >
              MCP Server
            </Link>
            <Link
              href="https://github.com/neobenjax/Canadian-Open-Data-Agentic-Platform"
              target="_blank"
              className="hover:text-slate-800 dark:hover:text-slate-200 transition-colors"
            >
              Monorepo
            </Link>
          </div>
        </div>
      </footer>
    </main>
  );
}
