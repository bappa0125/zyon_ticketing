"use client";

import { useActiveClient } from "@/context/ClientContext";

export function ClientSwitcher() {
  const { clients, clientName, setClientName, ready } = useActiveClient();

  if (!ready || clients.length === 0) {
    return (
      <div
        className="shrink-0 h-9 w-[7.5rem] sm:w-[9.5rem] animate-pulse rounded-lg bg-[var(--ai-surface)]"
        aria-hidden
      />
    );
  }

  return (
    <label className="shrink-0 flex flex-col gap-0.5">
      <span className="hidden text-[10px] font-medium uppercase tracking-wider text-[var(--ai-muted)] px-0.5 sm:block">
        Client
      </span>
      <select
        value={clientName ?? ""}
        onChange={(e) => setClientName(e.target.value)}
        className="h-9 w-[7.5rem] min-w-0 max-w-[11rem] cursor-pointer truncate rounded-lg border border-[var(--ai-border)] bg-[var(--ai-surface)] px-2 text-sm font-medium text-[var(--ai-text)] shadow-sm transition-colors hover:border-[var(--ai-accent)]/40 focus:border-[var(--ai-accent)] focus:outline-none focus:ring-2 focus:ring-[var(--ai-accent)]/25 sm:w-auto sm:min-w-[9.5rem] sm:px-2.5"
        aria-label="Active client"
      >
        {clients.map((c) => (
          <option key={c.name} value={c.name}>
            {c.name}
          </option>
        ))}
      </select>
    </label>
  );
}
