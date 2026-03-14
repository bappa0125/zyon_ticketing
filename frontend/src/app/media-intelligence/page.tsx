"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { MediaMentionCard, type MediaMentionItem } from "@/components/MediaIntelligence/MediaMentionCard";
import { ShareOfVoiceChart } from "@/components/MediaIntelligence/ShareOfVoiceChart";
import { MentionsTrendChart } from "@/components/MediaIntelligence/MentionsTrendChart";
import { TopPublicationsList } from "@/components/MediaIntelligence/TopPublicationsList";
import { TopicsList } from "@/components/MediaIntelligence/TopicsList";
import { CoverageByDomain, type DomainRow } from "@/components/MediaIntelligence/CoverageByDomain";
import { PRSummaryCard } from "@/components/MediaIntelligence/PRSummaryCard";
import { getApiBase } from "@/lib/api";

interface DashboardData {
  client: string;
  competitors: string[];
  range: string;
  coverage: { entity: string; mentions: number }[];
  feed: MediaMentionItem[];
  timeline: { date: string; [k: string]: string | number }[];
  top_publications: { source: string; mentions: number }[];
  topics: { topic: string; mentions: number }[];
  by_domain?: DomainRow[];
  pr_summary?: string;
}

const RANGE_OPTIONS = [
  { value: "24h", label: "24 hours" },
  { value: "7d", label: "7 days" },
  { value: "30d", label: "30 days" },
] as const;

export default function MediaIntelligencePage() {
  const [clients, setClients] = useState<{ name: string }[]>([]);
  const [client, setClient] = useState<string>("");
  const [range, setRange] = useState<string>("7d");
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingClients, setLoadingClients] = useState(true);
  const [selectedDomain, setSelectedDomain] = useState<string | null>(null);
  const [contentQuality, setContentQuality] = useState<string>("");

  useEffect(() => {
    async function fetchClients() {
      try {
        const res = await fetch(`${getApiBase()}/clients`);
        if (!res.ok) throw new Error("Failed to load clients");
        const json = await res.json();
        const list = json.clients ?? [];
        setClients(list);
        if (list.length > 0 && !client) setClient(list[0].name);
      } catch (e) {
        console.error(e);
        setClients([]);
      } finally {
        setLoadingClients(false);
      }
    }
    fetchClients();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fetch clients once on mount; default client set from first load
  }, []);

  useEffect(() => {
    if (!client.trim()) {
      setData(null);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    const params = new URLSearchParams({
      client,
      range,
    });
    if (selectedDomain) params.set("domain", selectedDomain);
    if (contentQuality) params.set("content_quality", contentQuality);
    (async () => {
      try {
        const res = await fetch(
          `${getApiBase()}/media-intelligence/dashboard?${params.toString()}`
        );
        if (!res.ok) throw new Error("Dashboard failed");
        const json = await res.json();
        if (!cancelled) setData(json);
      } catch (e) {
        console.error(e);
        if (!cancelled) setData(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [client, range, selectedDomain, contentQuality]);

  const entities = data ? [data.client, ...(data.competitors || [])] : [];
  const totalMentions = data?.coverage?.reduce((s, c) => s + c.mentions, 0) ?? 0;
  const feedItems = data?.feed ?? [];

  return (
    <div className="app-page">
      <nav className="border-b border-zinc-800 bg-zinc-950 px-4 py-2 flex flex-wrap gap-2">
        <Link href="/" className="text-sm text-zinc-400 hover:text-zinc-200">
          ← Chat
        </Link>
        <Link href="/clients" className="text-sm text-zinc-400 hover:text-zinc-200">
          Clients
        </Link>
        <Link href="/media" className="text-sm text-zinc-400 hover:text-zinc-200">
          Media
        </Link>
      </nav>

      <div className="max-w-7xl mx-auto p-4 md:p-6">
        <header className="mb-6">
          <h1 className="text-2xl font-semibold text-zinc-100">Media Intelligence</h1>
          <p className="text-sm text-zinc-500 mt-1">
            Monitor media mentions for your client and competitors. See share of voice, trends, and top sources.
          </p>
        </header>

        {/* Entity selector + date filter */}
        <section className="flex flex-wrap items-center gap-4 mb-6 p-4 rounded-lg border border-zinc-800 bg-zinc-900/30">
          <div className="flex items-center gap-2">
            <label className="text-sm text-zinc-400">Client</label>
            <select
              value={client}
              onChange={(e) => setClient(e.target.value)}
              disabled={loadingClients}
              className="px-3 py-2 rounded-lg bg-zinc-800 border border-zinc-700 text-zinc-200 focus:outline-none focus:ring-2 focus:ring-zinc-600 min-w-[160px]"
            >
              {loadingClients && (
                <option value="">Loading…</option>
              )}
              {!loadingClients && (
                <>
                  <option value="">Select client</option>
                  {clients.map((c) => (
                    <option key={c.name} value={c.name}>
                      {c.name}
                    </option>
                  ))}
                </>
              )}
            </select>
          </div>
          <div className="flex items-center gap-2">
            <label className="text-sm text-zinc-400">Period</label>
            <div className="flex rounded-lg overflow-hidden border border-zinc-700">
              {RANGE_OPTIONS.map((r) => (
                <button
                  key={r.value}
                  onClick={() => setRange(r.value)}
                  className={`px-3 py-2 text-sm transition-colors ${
                    range === r.value
                      ? "bg-zinc-600 text-zinc-100"
                      : "bg-zinc-800 text-zinc-400 hover:bg-zinc-700"
                  }`}
                >
                  {r.label}
                </button>
              ))}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <label className="text-sm text-zinc-400">Source</label>
            <select
              value={selectedDomain ?? ""}
              onChange={(e) => setSelectedDomain(e.target.value || null)}
              className="px-3 py-2 rounded-lg bg-zinc-800 border border-zinc-700 text-zinc-200 focus:outline-none focus:ring-2 focus:ring-zinc-600 min-w-[180px]"
            >
              <option value="">All sources</option>
              {(data?.by_domain ?? []).map((row) => (
                <option key={row.domain} value={row.domain}>
                  {row.name || row.domain} ({row.total})
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <label className="text-sm text-zinc-400">Content</label>
            <select
              value={contentQuality}
              onChange={(e) => setContentQuality(e.target.value)}
              className="px-3 py-2 rounded-lg bg-zinc-800 border border-zinc-700 text-zinc-200 focus:outline-none focus:ring-2 focus:ring-zinc-600 min-w-[140px]"
            >
              <option value="">All</option>
              <option value="full_text">Full article only</option>
              <option value="snippet">Snippet only</option>
            </select>
          </div>
          {data && (
            <p className="text-sm text-zinc-500">
              {data.competitors?.length ? `Client + ${data.competitors.length} competitors` : "Client only"}
            </p>
          )}
        </section>

        {!client.trim() && (
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-8 text-center text-zinc-500">
            Select a client to view the dashboard.
          </div>
        )}

        {client.trim() && (
          <>
            {/* Coverage overview + summary */}
            <section className="mb-6">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-4">
                  <p className="text-xs text-zinc-500 uppercase tracking-wider">Total mentions</p>
                  <p className="text-2xl font-semibold text-zinc-100 mt-1">
                    {loading ? "—" : totalMentions}
                  </p>
                  <p className="text-xs text-zinc-500 mt-1">in selected period</p>
                </div>
                <div className="md:col-span-2">
                  <ShareOfVoiceChart
                    coverage={data?.coverage ?? []}
                    loading={loading}
                    clientName={data?.client}
                  />
                </div>
              </div>
              {client.toLowerCase() === "sahi" && (
                <div className="mt-4 mb-4">
                  <PRSummaryCard
                    client={client}
                    range={range}
                    prSummary={data?.pr_summary ?? ""}
                    loading={loading}
                  />
                </div>
              )}
              <div className="mt-4">
                <CoverageByDomain
                  byDomain={data?.by_domain ?? []}
                  entities={entities}
                  clientName={data?.client ?? ""}
                  competitors={data?.competitors ?? []}
                  loading={loading}
                  onSelectDomain={(d) => setSelectedDomain(d)}
                  selectedDomain={selectedDomain}
                />
              </div>
            </section>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Main: Feed (2/3) */}
              <div className="lg:col-span-2">
                <section>
                  <h2 className="text-lg font-medium text-zinc-200 mb-3">Media mentions feed</h2>
                  {loading && (
                    <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-8 text-center text-zinc-500">
                      Loading mentions…
                    </div>
                  )}
                  {!loading && feedItems.length === 0 && (
                    <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-8 text-center text-zinc-500">
                      No mentions in this period. Try another date range or run media monitoring.
                    </div>
                  )}
                  {!loading && feedItems.length > 0 && (
                    <div className="space-y-3 max-h-[600px] overflow-y-auto pr-1">
                      {feedItems.map((item, i) => (
                        <MediaMentionCard key={item.id || i} item={item} />
                      ))}
                    </div>
                  )}
                </section>
              </div>

              {/* Sidebar: Trend, Top pubs, Topics (1/3) */}
              <div className="space-y-4">
                <MentionsTrendChart
                  timeline={data?.timeline ?? []}
                  entities={entities}
                  clientName={data?.client}
                  loading={loading}
                />
                <TopPublicationsList items={data?.top_publications ?? []} loading={loading} />
                <TopicsList topics={data?.topics ?? []} loading={loading} />
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
