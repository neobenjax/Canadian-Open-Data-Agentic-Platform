import { source } from '@/lib/source';
import { notFound } from 'next/navigation';
import defaultMdxComponents from 'fumadocs-ui/mdx';
import {
  DocsPage,
  DocsBody,
  DocsTitle,
  DocsDescription,
} from 'fumadocs-ui/page';
import { ArchitectureFlowDiagram } from '@/components/architecture-flow';

interface PageProps {
  params: Promise<{ slug?: string[] }>;
}

export default async function DocsCatchAllPage({ params }: PageProps) {
  const resolvedParams = await params;
  const page = source.getPage(resolvedParams.slug);

  if (!page) {
    notFound();
  }

  const pageData = page.data as any;
  const MDX = pageData.body;

  return (
    <DocsPage
      toc={pageData.toc}
      full={pageData.full}
      tableOfContent={{
        style: 'clerk',
        single: false,
      }}
    >
      <DocsTitle>{pageData.title}</DocsTitle>
      {pageData.description && (
        <DocsDescription>{pageData.description}</DocsDescription>
      )}
      <DocsBody>
        <MDX
          components={{
            ...defaultMdxComponents,
            ArchitectureFlowDiagram,
          }}
        />
      </DocsBody>
    </DocsPage>
  );
}

export async function generateStaticParams() {
  return source.generateParams();
}

export async function generateMetadata({ params }: PageProps) {
  const resolvedParams = await params;
  const page = source.getPage(resolvedParams.slug);

  if (!page) {
    return {
      title: 'Documentation | CanData-MCP',
    };
  }

  const pageData = page.data as any;
  return {
    title: `${pageData.title} | CanData Developer Docs`,
    description: pageData.description,
  };
}
