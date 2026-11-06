import Link from 'next/link';
import { ArrowLeft, BookOpen, Terminal, Sparkles } from 'lucide-react';

const DOCS_NAV = [
  { href: '/docs', label: 'Overview' },
  { href: '/docs/quickstart', label: 'Quickstart & Installation' },
  { href: '/docs/claude-desktop', label: 'Claude Desktop & Cursor' },
  { href: '/docs/connectors', label: 'Official Canadian Connectors' },
  { href: '/docs/architecture', label: 'System Architecture' },
  { href: '/docs/api-reference', label: 'MCP Tools Reference' },
];

export default function DocsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen flex flex-col bg-slate-50 dark:bg-slate-950">
      {/* Top Header */}
      <header className="border-b border-black/5 dark:border-white/10 bg-white/80 dark:bg-slate-900/80 backdrop-blur sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link
              href="/"
              className="text-xs font-semibold text-slate-500 hover:text-red-700 flex items-center gap-1.5 transition-colors"
            >
              <ArrowLeft className="w-3.5 h-3.5" /> Overview
            </Link>
            <div className="h-4 w-px bg-slate-200 dark:bg-slate-800" />
            <Link href="/docs" className="flex items-center gap-2 font-bold text-slate-900 dark:text-white text-sm">
              <BookOpen className="w-4 h-4 text-red-600" />
              <span>CanData Developer Docs</span>
            </Link>
          </div>
          <div className="flex items-center gap-4">
            <Link
              href="/playground"
              className="text-xs font-medium px-3 py-1.5 rounded-lg bg-red-50 text-red-700 dark:bg-red-950/60 dark:text-red-300 border border-red-200 dark:border-red-900 flex items-center gap-1.5 transition-all hover:bg-red-100"
            >
              <Terminal className="w-3.5 h-3.5" /> Open API Sandbox
            </Link>
          </div>
        </div>
      </header>

      {/* Docs Body with Sidebar */}
      <div className="max-w-7xl mx-auto px-6 py-8 flex-1 w-full grid grid-cols-1 md:grid-cols-12 gap-8">
        {/* Sidebar */}
        <aside className="md:col-span-3 space-y-6">
          <div>
            <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">
              Guides &amp; Architecture
            </h3>
            <ul className="space-y-1">
              {DOCS_NAV.map((item) => (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    className="block px-3 py-2 rounded-lg text-sm font-medium text-slate-600 dark:text-slate-300 hover:bg-red-50 dark:hover:bg-red-950/30 hover:text-red-700 dark:hover:text-red-400 transition-colors"
                  >
                    {item.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          <div className="p-4 rounded-xl bg-gradient-to-br from-red-50 to-orange-50 dark:from-red-950/20 dark:to-slate-900 border border-red-100 dark:border-red-900/50">
            <div className="flex items-center gap-2 text-xs font-bold text-red-800 dark:text-red-300 mb-1">
              <Sparkles className="w-3.5 h-3.5 text-red-600" /> FastMCP Standard
            </div>
            <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
              Tested against Anthropic Claude 3.5 Sonnet, Claude Desktop, and LangGraph 0.2+.
            </p>
          </div>
        </aside>

        {/* Main Content Area */}
        <article className="md:col-span-9 bg-white dark:bg-slate-900 rounded-xl p-8 border border-black/5 dark:border-white/10 shadow-sm prose dark:prose-invert max-w-none">
          {children}
        </article>
      </div>
    </div>
  );
}
