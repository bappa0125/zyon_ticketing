"use client";

import { useState, useEffect } from "react";
import { CoverageChart, CoverageRow } from "@/components/CoverageChart";
import Link from "next/link";

function getApiUrl(): string {
  if (typeof window === "undefined")
    return process.env.NEXT_PUBLIC_API_URL || "http://localhost/api";
  return "/api";
}

export default function CoveragePage() {
  const [coverage, setCoverage] = useState<CoverageRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [clientFilter, setClientFilter] = useState<string>("Sahi");

  useEffect(() => {
    async function fetchCoverage() {
      if (!clientFilter.trim()) {
        setCoverage([]);
        setLoading(false);
        return;
      }
      try {
        const url = `${getApiUrl()}/coverage/competitors?client=${encodeURIComponent(clientFilter)}`;
        const res = await fetch(url);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        setCoverage(data.coverage ?? []);
      } catch (err) {
        console.error("fetchCoverage failed:", err);
        setCoverage([]);
      } finally {
        setLoading(false);
      }
    }
    fetchCoverage();
  }, [clientFilter]);

  return (
    <div className="min-h-screen bg-[var(--background)] p-6">
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
        </div>
        <h1 className="text-xl font-semibold mb-4 text-zinc-100">
          Competitor Coverage
        </h1>
        <p className="text-sm text-zinc-500 mb-4">
          Compare media mentions for client and competitors. Filter by client:
        </p>
        <input
          type="text"
          placeholder="Client (e.g. Sahi)"
          value={clientFilter}
          onChange={(e) => setClientFilter(e.target.value)}
          className="mb-4 px-3 py-2 rounded-lg bg-zinc-800 border border-zinc-700 text-zinc-200 placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-zinc-600 w-48"
        />
        <CoverageChart coverage={coverage} loading={loading} />
      </div>
    </div>
  );
}
