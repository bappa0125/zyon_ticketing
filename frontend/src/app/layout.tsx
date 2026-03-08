import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Zyon AI Chat",
  description: "AI-powered chat assistant",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen antialiased">
        <nav className="border-b border-zinc-800 bg-zinc-950 px-4 py-2 flex gap-4">
          <Link href="/" className="text-sm text-zinc-400 hover:text-zinc-200">
            Chat
          </Link>
          <Link
            href="/clients"
            className="text-sm text-zinc-400 hover:text-zinc-200"
          >
            Clients
          </Link>
          <Link
            href="/media"
            className="text-sm text-zinc-400 hover:text-zinc-200"
          >
            Media
          </Link>
          <Link
            href="/sentiment"
            className="text-sm text-zinc-400 hover:text-zinc-200"
          >
            Sentiment
          </Link>
          <Link
            href="/topics"
            className="text-sm text-zinc-400 hover:text-zinc-200"
          >
            Topics
          </Link>
          <Link
            href="/coverage"
            className="text-sm text-zinc-400 hover:text-zinc-200"
          >
            Coverage
          </Link>
          <Link
            href="/opportunities"
            className="text-sm text-zinc-400 hover:text-zinc-200"
          >
            Opportunities
          </Link>
        </nav>
        {children}
      </body>
    </html>
  );
}
