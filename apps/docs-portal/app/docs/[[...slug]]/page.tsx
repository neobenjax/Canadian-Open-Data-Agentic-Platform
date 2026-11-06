import { source } from '@/lib/source';
import { notFound } from 'next/navigation';
import defaultMdxComponents from 'fumadocs-ui/mdx';

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
    <div className="space-y-6">
      <header className="border-b border-black/5 dark:border-white/10 pb-6 mb-6">
        <h1 className="text-3xl font-extrabold text-slate-900 dark:text-white tracking-tight">
          {pageData.title}
        </h1>
        {pageData.description && (
          <p className="text-base text-slate-600 dark:text-slate-300 mt-2">
            {pageData.description}
          </p>
        )}
      </header>
      <div className="prose dark:prose-invert max-w-none">
        <MDX components={{ ...defaultMdxComponents }} />
      </div>
    </div>
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
