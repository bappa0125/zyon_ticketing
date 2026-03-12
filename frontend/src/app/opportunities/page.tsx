"use client";

import { useState, useEffect } from "react";
import { OpportunityTable, OpportunityRow } from "@/components/OpportunityTable";
import Link from "next/link";

import { getApiBase } from "@/lib/api";

export default function OpportunitiesPage() {
  const [opportunities, setOpportunities] = useState<OpportunityRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [clientFilter, setClientFilter] = useState<string>("Sahi");

  useEffect(() => {
    async function fetchOpportunities() {
      if (!clientFilter.trim()) {
        setOpportunities([]);
        setLoading(false);
        return;
      }
      try {
        const url = `${getApiBase()}/opportunities?client=${encodeURIComponent(clientFilter)}`;
        const res = await fetch(url);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        setOpportunities(data.opportunities ?? []);
      } catch (err) {
        console.error("fetchOpportunities failed:", err);
        setOpportunities([]);
      } finally {
        setLoading(false);
      }
    }
    fetchOpportunities();
  }, [clientFilter]);

  return (
    <div className="app-page p-6">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center gap-4 mb-6">
          <Link
            href="/"
            className="text-sm text-zinc-400 hover:text-zinc-200"
          >
            ← Chat
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
        </div>
        <h1 className="text-xl font-semibold mb-4 text-zinc-100">
          PR Opportunities
        </h1>
        <p className="text-sm text-zinc-500 mb-4">
          Topics where competitors have coverage but the client does not. Filter by client:
        </p>
        <input
          type="text"
          placeholder="Client (e.g. Sahi)"
          value={clientFilter}
          onChange={(e) => setClientFilter(e.target.value)}
          className="mb-4 px-3 py-2 rounded-lg bg-zinc-800 border border-zinc-700 text-zinc-200 placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-zinc-600 w-48"
        />
        <OpportunityTable opportunities={opportunities} loading={loading} />
      </div>
    </div>
  );
}
