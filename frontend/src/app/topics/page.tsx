"use client";

import { useState, useEffect } from "react";
import { TopicTable, TopicRow } from "@/components/TopicTable";
import { TopicsBriefingCards } from "@/components/TopicsBriefingCards";
import Link from "next/link";

import { getApiBase } from "@/lib/api";

const RANGE_OPTIONS = [
  { value: "24h", label: "24h" },
  { value: "7d", label: "7d" },
  { value: "30d", label: "30d" },
] as const;

interface TopicsResponse {
  topics: TopicRow[];
  client: string | null;
  competitors: string[];
  range: string;
}

export default function TopicsPage() {
  const [topics, setTopics] = useState<TopicRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [clientFilter, setClientFilter] = useState<string>("");
  const [range, setRange] = useState<string>("7d");
  const [clients, setClients] = useState<{ name: string }[]>([]);
  const [responseMeta, setResponseMeta] = useState<{ client: string | null; range: string }>({ client: null, range: "7d" });

  useEffect(() => {
    async function fetchClients() {
      try {
        const res = await fetch(`${getApiBase()}/clients`);
        if (!res.ok) return;
        const json = await res.json();
        const list = json.clients ?? [];
        setClients(list);
        if (list.length > 0 && !clientFilter) setClientFilter(list[0].name);
      } catch {
        setClients([]);
      }
    }
    fetchClients();
  }, []);

  useEffect(() => {
    async function fetchTopics() {
      try {
        const params = new URLSearchParams();
        params.set("range_param", range);
        if (clientFilter.trim()) params.set("client", clientFilter.trim());
        const url = `${getApiBase()}/topics?${params.toString()}`;
        const res = await fetch(url);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data: TopicsResponse = await res.json();
        setTopics(data.topics ?? []);
        setResponseMeta({ client: data.client ?? null, range: data.range ?? "7d" });
      } catch (err) {
        console.error("fetchTopics failed:", err);
        setTopics([]);
      } finally {
        setLoading(false);
      }
    }
    fetchTopics();
  }, [clientFilter, range]);

  function handleExportBrief() {
    const rows = [
      ["Topic", "Vol", "Trend %", "Sentiment", "Client", "Competitors", "Action"].join("\t"),
      ...topics.map((t) =>
        [
          t.topic,
          t.mentions,
          t.trend_pct ?? "—",
          t.sentiment_summary ?? "—",
          t.client_mentions ?? "—",
          t.competitor_mentions ?? "—",
          t.action ?? "—",
        ].join("\t")
      ),
    ];
    const blob = new Blob([rows.join("\n")], { type: "text/tab-separated-values;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `topics-brief-${responseMeta.client ?? "all"}-${responseMeta.range}.tsv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const displayClient = responseMeta.client ?? "All";

  return (
    <div className="app-page">
      <div className="max-w-6xl mx-auto p-6">
        <div className="flex items-center gap-4 mb-4">
          <Link href="/" className="text-sm text-zinc-400 hover:text-zinc-200">
            ← Chat
          </Link>
          <Link href="/media-intelligence" className="text-sm text-zinc-400 hover:text-zinc-200">
            Media Intelligence
          </Link>
          <Link href="/clients" className="text-sm text-zinc-400 hover:text-zinc-200">
            Clients
          </Link>
        </div>

        {/* Header: TOPICS & TRENDING – Sahi  [Client ▼] [7d ▼] */}
        <header className="flex flex-wrap items-center justify-between gap-4 py-4 border-b border-zinc-800">
          <h1 className="text-xl font-semibold text-zinc-100">
            TOPICS & TRENDING – {displayClient}
          </h1>
          <div className="flex items-center gap-3">
            <select
              value={clientFilter}
              onChange={(e) => setClientFilter(e.target.value)}
              className="px-3 py-2 rounded-lg bg-zinc-800 border border-zinc-700 text-zinc-200 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-600"
            >
              <option value="">All</option>
              {clients.map((c) => (
                <option key={c.name} value={c.name}>
                  {c.name}
                </option>
              ))}
            </select>
            <select
              value={range}
              onChange={(e) => setRange(e.target.value)}
              className="px-3 py-2 rounded-lg bg-zinc-800 border border-zinc-700 text-zinc-200 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-600"
            >
              {RANGE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
        </header>

        {/* Three briefing cards */}
        <section className="py-6">
          <TopicsBriefingCards topics={topics} />
        </section>

        {/* Trending topics table */}
        <section className="py-6 border-t border-zinc-800">
          <div className="flex items-center justify-between gap-4 mb-4">
            <h2 className="text-base font-medium text-zinc-200">TRENDING TOPICS</h2>
            <button
              type="button"
              onClick={handleExportBrief}
              disabled={topics.length === 0}
              className="px-4 py-2 rounded-lg bg-zinc-800 border border-zinc-700 text-zinc-300 text-sm hover:bg-zinc-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Export Brief
            </button>
          </div>
          <TopicTable topics={topics} loading={loading} clientName={responseMeta.client} />
          {topics.length > 0 && (
            <p className="text-xs text-zinc-500 mt-3">Click row to expand briefing</p>
          )}
        </section>

        {/* Publication themes (placeholder) */}
        <section className="py-6 border-t border-zinc-800">
          <h2 className="text-base font-medium text-zinc-200 mb-3">PUBLICATION THEMES (for future content)</h2>
          <ul className="space-y-2 text-sm text-zinc-500">
            <li>• Retail options adoption – &quot;From F&amp;O fear to first trade&quot;</li>
            <li>• Cost of investing – &quot;Beyond brokerage: true cost&quot;</li>
            <li>• Financial literacy – &quot;Educate before you trade&quot;</li>
          </ul>
          <p className="text-xs text-zinc-600 mt-2 italic">Themes derived from topic clusters — coming soon</p>
        </section>
      </div>
    </div>
  );
}
