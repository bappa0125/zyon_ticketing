"use client";

import { Suspense, useMemo } from "react";
import { ClientTable } from "@/components/ClientTable";
import Link from "next/link";
import { useActiveClient } from "@/context/ClientContext";
import { ClientsUrlSync } from "./ClientsUrlSync";
import {
  clientsInVerticalUi,
  firstClientForVertical,
  verticalFromClient,
  type ClientsVerticalUi,
} from "@/lib/clientVerticals";

export default function ClientsPage() {
  const { clients, ready, activeClient, setClientName } = useActiveClient();

  const hasPolitical = clients.some((c) => c.vertical === "political");
  const hasTrading =
    clients.some((c) => c.vertical === "trading") ||
    clients.some((c) => c.vertical === "corporate_pr");

  const uiVertical: ClientsVerticalUi | null =
    ready && activeClient ? verticalFromClient(activeClient) : null;

  const tableRows = useMemo(() => {
    if (!uiVertical) return [];
    return clientsInVerticalUi(clients, uiVertical).map((c) => ({
      name: c.name,
      domain: c.domain,
      competitors: c.competitors,
    }));
  }, [clients, uiVertical]);

  const onVerticalChange = (v: ClientsVerticalUi) => {
    const pick = firstClientForVertical(clients, v);
    if (pick) setClientName(pick.name);
  };

  return (
    <div className="app-page p-6">
      <Suspense fallback={null}>
        <ClientsUrlSync />
      </Suspense>
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center gap-4 mb-6">
          <Link
            href="/"
            className="text-sm text-zinc-400 hover:text-zinc-200"
          >
            ← Chat
          </Link>
        </div>

        <header className="flex flex-wrap items-end justify-between gap-4 mb-6">
          <div>
            <h1 className="text-xl font-semibold text-zinc-100">Monitored Clients</h1>
            <p className="text-sm text-zinc-500 mt-1">
              Trading vs Political switches the active account for the entire app (same as the header
              switcher). This page lists only clients in the selected portfolio. The URL uses{" "}
              <code className="text-zinc-400">?vertical=…</code> and{" "}
              <code className="text-zinc-400">?client=…</code>.
            </p>
          </div>
          <label className="flex flex-col gap-1 min-w-[14rem]">
            <span className="text-xs font-medium uppercase tracking-wider text-zinc-500">
              Portfolio
            </span>
            <select
              value={uiVertical ?? ""}
              onChange={(e) => onVerticalChange(e.target.value as ClientsVerticalUi)}
              disabled={!ready || (!hasPolitical && !hasTrading)}
              className="px-3 py-2 rounded-lg bg-zinc-800 border border-zinc-700 text-zinc-200 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-600 disabled:opacity-50"
              aria-label="Switch between trading and political monitoring"
            >
              {!ready ? (
                <option value="">Loading…</option>
              ) : (
                <>
                  {hasTrading ? (
                    <option value="trading">Trading</option>
                  ) : null}
                  {hasPolitical ? (
                    <option value="political">Political</option>
                  ) : null}
                </>
              )}
            </select>
          </label>
        </header>

        {ready && activeClient ? (
          <p className="text-sm text-zinc-500 mb-4">
            Active account:{" "}
            <span className="text-zinc-300">{activeClient.name}</span>
            {tableRows.length > 1 ? (
              <span className="text-zinc-600"> · {tableRows.length} clients in this portfolio</span>
            ) : null}
          </p>
        ) : null}

        <ClientTable clients={tableRows} loading={!ready} />
      </div>
    </div>
  );
}
