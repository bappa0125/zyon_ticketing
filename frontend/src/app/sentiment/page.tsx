"use client";

import { useState, useEffect } from "react";
import { SentimentChart, type SentimentSummary } from "@/components/SentimentChart";
import { SentimentMentionCard } from "@/components/Sentiment/SentimentMentionCard";
import type { MediaMentionItem } from "@/components/MediaIntelligence/MediaMentionCard";
import Link from "next/link";

function getApiUrl(): string {
  if (typeof window === "undefined")
    return process.env.NEXT_PUBLIC_API_URL || "http://localhost/api";
  return "/api";
}

const RANGE_OPTIONS = [
  { value: "24h", label: "24h" },
  { value: "7d", label: "7 days" },
  { value: "30d", label: "30 days" },
] as const;

const SENTIMENT_FILTERS = [
  { value: "", label: "All sentiment" },
  { value: "positive", label: "Positive" },
  { value: "neutral", label: "Neutral" },
  { value: "negative", label: "Negative" },
] as const;

interface ClientWithCompetitors {
  name: string;
  domain?: string;
  competitors?: string[];
}

export default function SentimentPage() {
  const [clients, setClients] = useState<ClientWithCompetitors[]>([]);
  const [client, setClient] = useState<string>("");
  const [competitor, setCompetitor] = useState<string>("");
  const [competitorFilter, setCompetitorFilter] = useState<string>("");
  const [range, setRange] = useState<string>("7d");
  const [sentimentFilter, setSentimentFilter] = useState<string>("");
  const [summaries, setSummaries] = useState<SentimentSummary[]>([]);
  const [mentions, setMentions] = useState<MediaMentionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingClients, setLoadingClients] = useState(true);
  const [loadingMentions, setLoadingMentions] = useState(true);

  useEffect(() => {
    async function fetchClients() {
      try {
        const res = await fetch(`${getApiUrl()}/clients`);
        if (!res.ok) throw new Error("Failed to load clients");
        const json = await res.json();
        const list = (json.clients ?? []).map((c: { name?: string; domain?: string; competitors?: string[] }) => ({
          name: (c.name ?? "").trim(),
          domain: (c.domain ?? "").trim(),
          competitors: Array.isArray(c.competitors) ? c.competitors.map(String) : [],
        }));
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
  }, []);

  const clientObj = clients.find((c) => c.name.toLowerCase() === client.toLowerCase());
  const entities = clientObj ? [clientObj.name, ...(clientObj.competitors ?? [])] : [];
  const effectiveEntity = competitorFilter.trim() || competitor;

  useEffect(() => {
    if (!client.trim()) {
      setSummaries([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    const params = new URLSearchParams({ client });
    if (effectiveEntity) params.set("entity", effectiveEntity);
    fetch(`${getApiUrl()}/sentiment/summary?${params.toString()}`)
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(`HTTP ${res.status}`))))
      .then((data) => setSummaries(data.summaries ?? []))
      .catch(() => setSummaries([]))
      .finally(() => setLoading(false));
  }, [client, effectiveEntity]);

  useEffect(() => {
    if (!client.trim()) {
      setMentions([]);
      setLoadingMentions(false);
      return;
    }
    setLoadingMentions(true);
    const params = new URLSearchParams({ client, range });
    if (sentimentFilter) params.set("sentiment", sentimentFilter);
    if (effectiveEntity) params.set("entity", effectiveEntity);
    fetch(`${getApiUrl()}/sentiment/mentions?${params.toString()}`)
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(`HTTP ${res.status}`))))
      .then((data) => setMentions(data.mentions ?? []))
      .catch(() => setMentions([]))
      .finally(() => setLoadingMentions(false));
  }, [client, range, sentimentFilter, effectiveEntity]);

  useEffect(() => {
    if (client && competitor && !entities.includes(competitor)) setCompetitor("");
  }, [client, entities, competitor]);
  const totalArticles = summaries.reduce((s, x) => s + x.positive + x.neutral + x.negative, 0);
  const totalPositive = summaries.reduce((s, x) => s + x.positive, 0);
  const totalNeutral = summaries.reduce((s, x) => s + x.neutral, 0);
  const totalNegative = summaries.reduce((s, x) => s + x.negative, 0);

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-200">
      <nav className="border-b border-zinc-800 bg-zinc-900/50 px-4 py-3 flex flex-wrap items-center gap-3">
        <Link href="/" className="text-sm text-zinc-400 hover:text-zinc-200 transition-colors">
          ← Chat
        </Link>
        <Link href="/clients" className="text-sm text-zinc-400 hover:text-zinc-200 transition-colors">
          Clients
        </Link>
        <Link href="/media" className="text-sm text-zinc-400 hover:text-zinc-200 transition-colors">
          Media
        </Link>
        <Link
          href="/media-intelligence"
          className="text-sm text-zinc-400 hover:text-zinc-200 transition-colors"
        >
          Media Intelligence
        </Link>
        <Link
          href="/sentiment"
          className="text-sm text-emerald-400 font-medium"
        >
          Sentiment
        </Link>
      </nav>

      <div className="max-w-7xl mx-auto p-4 md:p-6">
        <header className="mb-6">
          <h1 className="text-2xl font-semibold text-zinc-100">Sentiment Analysis</h1>
          <p className="text-sm text-zinc-500 mt-1">
            Media tone for client and competitors. View counts and article-level mentions.
          </p>
        </header>

        <section className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-4 mb-6">
          <div className="flex flex-wrap items-end gap-4">
            <div className="flex items-center gap-2">
              <label className="text-sm font-medium text-zinc-400">Client</label>
              <select
                value={clients.some((c) => c.name === client) ? client : ""}
                onChange={(e) => setClient(e.target.value)}
                disabled={loadingClients}
                className="px-3 py-2 rounded-lg bg-zinc-800 border border-zinc-700 text-zinc-200 focus:outline-none focus:ring-2 focus:ring-zinc-600 min-w-[140px]"
              >
                <option value="">Select client</option>
                {clients.map((c) => (
                  <option key={c.name} value={c.name}>
                    {c.name}
                  </option>
                ))}
              </select>
              {loadingClients && (
                <span className="text-xs text-zinc-500">Loading…</span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <label className="text-sm font-medium text-zinc-400">Period</label>
              <div className="flex rounded-lg overflow-hidden border border-zinc-700">
                {RANGE_OPTIONS.map((r) => (
                  <button
                    key={r.value}
                    onClick={() => setRange(r.value)}
                    className={`px-3 py-2 text-sm font-medium transition-colors ${
                      range === r.value
                        ? "bg-zinc-600 text-zinc-100"
                        : "bg-zinc-800 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200"
                    }`}
                  >
                    {r.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <label className="text-sm font-medium text-zinc-400">Competitor</label>
              <select
                value={competitor}
                onChange={(e) => {
                  setCompetitor(e.target.value);
                  if (!e.target.value) setCompetitorFilter("");
                }}
                className="px-3 py-2 rounded-lg bg-zinc-800 border border-zinc-700 text-zinc-200 focus:outline-none focus:ring-2 focus:ring-zinc-600 min-w-[160px]"
              >
                <option value="">All (client + competitors)</option>
                {entities.map((e) => (
                  <option key={e} value={e}>
                    {e}
                  </option>
                ))}
              </select>
              <input
                type="text"
                placeholder="Filter by competitor (e.g. Zerodha)"
                value={competitorFilter}
                onChange={(e) => setCompetitorFilter(e.target.value)}
                className="px-3 py-2 rounded-lg bg-zinc-800 border border-zinc-700 text-zinc-200 placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-zinc-600 w-48"
              />
            </div>
            <div className="flex items-center gap-2">
              <label className="text-sm font-medium text-zinc-400">Sentiment</label>
              <select
                value={sentimentFilter}
                onChange={(e) => setSentimentFilter(e.target.value)}
                className="px-3 py-2 rounded-lg bg-zinc-800 border border-zinc-700 text-zinc-200 focus:outline-none focus:ring-2 focus:ring-zinc-600 min-w-[140px]"
              >
                {SENTIMENT_FILTERS.map((f) => (
                  <option key={f.value || "all"} value={f.value}>
                    {f.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </section>

        {!client.trim() ? (
          <div className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-12 text-center">
            <p className="text-zinc-400 mb-2">Select a client above to view sentiment analysis.</p>
            <p className="text-sm text-zinc-500">
              {loadingClients
                ? "Loading clients…"
                : clients.length === 0
                  ? "No clients found. Check that the backend is running and config/clients.yaml is loaded."
                  : "Choose a client from the dropdown to see sentiment counts and article mentions."}
            </p>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
              <div className="lg:col-span-2">
                <SentimentChart summaries={summaries} loading={loading} />
              </div>
              <div className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-4">
                <h3 className="text-sm font-semibold text-zinc-400 uppercase tracking-wider mb-3">
                  Article count
                </h3>
                <p className="text-3xl font-bold text-zinc-100 mb-1">{totalArticles}</p>
                <p className="text-xs text-zinc-500 mb-3">in selected period</p>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-emerald-400">Positive</span>
                    <span className="font-medium text-zinc-200">{totalPositive}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-zinc-400">Neutral</span>
                    <span className="font-medium text-zinc-200">{totalNeutral}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-rose-400">Negative</span>
                    <span className="font-medium text-zinc-200">{totalNegative}</span>
                  </div>
                </div>
              </div>
            </div>

            <section className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-4">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold text-zinc-100">Article mentions</h2>
                <span className="text-sm text-zinc-500">{mentions.length} articles</span>
              </div>
              {loadingMentions ? (
                <div className="py-16 text-center text-zinc-500">Loading mentions…</div>
              ) : mentions.length === 0 ? (
                <div className="py-16 text-center text-zinc-500">
                  No mentions with sentiment for the selected filters.
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 max-h-[720px] overflow-y-auto pr-1">
                  {mentions.map((item, i) => (
                    <SentimentMentionCard key={item.id || i} item={item} />
                  ))}
                </div>
              )}
            </section>
          </>
        )}
      </div>
    </div>
  );
}
