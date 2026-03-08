"use client";

import { useState, useEffect } from "react";
import { MediaTable } from "@/components/MediaTable";
import Link from "next/link";

function getApiUrl(): string {
  if (typeof window === "undefined")
    return process.env.NEXT_PUBLIC_API_URL || "http://localhost/api";
  return "/api";
}

export default function MediaPage() {
  const [articles, setArticles] = useState<
    { title: string; source: string; url: string; entity: string; date?: string; snippet?: string }[]
  >([]);
  const [loading, setLoading] = useState(true);
  const [clientFilter, setClientFilter] = useState<string>("");

  useEffect(() => {
    async function fetchArticles() {
      try {
        const url = clientFilter
          ? `${getApiUrl()}/media/latest?client=${encodeURIComponent(clientFilter)}`
          : `${getApiUrl()}/media/latest`;
        const res = await fetch(url);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        setArticles(data.articles ?? []);
      } catch (err) {
        console.error("fetchArticles failed:", err);
        setArticles([]);
      } finally {
        setLoading(false);
      }
    }
    fetchArticles();
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
        </div>
        <h1 className="text-xl font-semibold mb-4 text-zinc-100">
          Media Monitoring
        </h1>
        <p className="text-sm text-zinc-500 mb-4">
          Latest news mentions of monitored clients and competitors. Filter by client:
        </p>
        <input
          type="text"
          placeholder="Client (e.g. Sahi)"
          value={clientFilter}
          onChange={(e) => setClientFilter(e.target.value)}
          className="mb-4 px-3 py-2 rounded-lg bg-zinc-800 border border-zinc-700 text-zinc-200 placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-zinc-600 w-48"
        />
        <MediaTable articles={articles} loading={loading} />
      </div>
    </div>
  );
}
