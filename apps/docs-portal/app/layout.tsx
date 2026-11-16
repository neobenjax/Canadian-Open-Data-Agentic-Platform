import 'fumadocs-ui/style.css';
import './globals.css';
import type { Metadata } from 'next';
import { RootProvider } from 'fumadocs-ui/provider';

export const metadata: Metadata = {
  title: {
    template: '%s | CanData Docs Portal',
    default: 'CanData Documentation & Interactive API Playground',
  },
  description: 'FastMCP 2.0 In-Memory DuckDB Slicing Engine & Multi-Agent Platform for Canadian Civic Data',
  icons: {
    icon: [
      { url: '/icon.svg', type: 'image/svg+xml' },
      { url: '/favicon.ico', sizes: 'any' },
    ],
    shortcut: '/favicon.ico',
    apple: '/icon.svg',
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning className="m-0 p-0 border-0">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@600;700;800&family=JetBrains+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="m-0 p-0 border-0 antialiased min-h-screen">
        <RootProvider>{children}</RootProvider>
      </body>
    </html>
  );
}
