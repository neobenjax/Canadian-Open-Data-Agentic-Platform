import { DocsLayout } from 'fumadocs-ui/layouts/docs';
import { source } from '@/lib/source';
import React from 'react';

export default function RootDocsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <DocsLayout
      tree={source.pageTree}
      nav={{
        enabled: false,
        title: (
          <span className="flex items-center gap-2 font-bold text-sm tracking-tight">
            <span className="text-[#D80621] text-base">🍁</span>
            <span>
              CanData<span className="text-[#D80621]">-MCP</span>
            </span>
          </span>
        ),
      }}
      links={[
        {
          text: 'Playground',
          url: '/playground',
        },
        {
          text: 'MCP Server',
          url: 'https://github.com/neobenjax/Canadian-Open-Data-Agentic-Platform-MCP-Server',
          external: true,
        },
        {
          text: 'Monorepo',
          url: 'https://github.com/neobenjax/Canadian-Open-Data-Agentic-Platform',
          external: true,
        },
      ]}
      sidebar={{
        collapsible: true,
      }}
    >
      {children}
    </DocsLayout>
  );
}
