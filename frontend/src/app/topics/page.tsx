"use client";

import { useState, useEffect } from "react";
import { TopicTable, TopicRow } from "@/components/TopicTable";
import Link from "next/link";

function getApiUrl(): string {
  if (typeof window === "undefined")
    return process.env.NEXT_PUBLIC_API_URL || "http://localhost/api";
  return "/api";
}

export default function TopicsPage() {
  const [topics, setTopics] = useState<TopicRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [clientFilter, setClientFilter] = useState<string>("");

  useEffect(() => {
    async function fetchTopics() {
      try {
        const url = clientFilter
          ? `${getApiUrl()}/topics?client=${encodeURIComponent(clientFilter)}`
          : `${getApiUrl()}/topics`;
        const res = await fetch(url);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        setTopics(data.topics ?? []);
      } catch (err) {
        console.error("fetchTopics failed:", err);
        setTopics([]);
      } finally {
        setLoading(false);
      }
    }
    fetchTopics();
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
        </div>
        <h1 className="text-xl font-semibold mb-4 text-zinc-100">
          Topic Detection
        </h1>
        <p className="text-sm text-zinc-500 mb-4">
          Key topics in media coverage for monitored entities. Filter by client:
        </p>
        <input
          type="text"
          placeholder="Client (e.g. Sahi)"
          value={clientFilter}
          onChange={(e) => setClientFilter(e.target.value)}
          className="mb-4 px-3 py-2 rounded-lg bg-zinc-800 border border-zinc-700 text-zinc-200 placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-zinc-600 w-48"
        />
        <TopicTable topics={topics} loading={loading} />
      </div>
    </div>
  );
}
