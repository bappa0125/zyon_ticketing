"use client";

import { ClientProvider } from "@/context/ClientContext";
import { AppNav } from "./AppNav";
import { HelpPanel } from "./HelpPanel";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <ClientProvider>
      <div className="min-h-screen ai-bg-mesh">
        <AppNav />
        <main className="mx-auto w-full max-w-[var(--ai-max-content)] px-4 py-6 md:px-6 md:py-8 animate-ai-fade-in motion-reduce:animate-none">
          {children}
        </main>
        <HelpPanel />
      </div>
    </ClientProvider>
  );
}
