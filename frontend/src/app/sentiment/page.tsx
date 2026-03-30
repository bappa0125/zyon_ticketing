"use client";

import { useState, useEffect, useMemo } from "react";
import { SentimentChart, type SentimentSummary } from "@/components/SentimentChart";
import { SentimentMentionCard } from "@/components/Sentiment/SentimentMentionCard";
import type { MediaMentionItem } from "@/components/MediaIntelligence/MediaMentionCard";
import Link from "next/link";

import { getApiBase, withClientQuery } from "@/lib/api";
import { useActiveClient } from "@/context/ClientContext";
import { getEntityHex } from "@/lib/entityColors";
import { NarrativeDashboard } from "@/components/NarrativeIntelligence/NarrativeDashboard";

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

const SOURCE_OPTIONS = [
  { value: "all", label: "All" },
  { value: "news", label: "News" },
  { value: "forums", label: "Forums" },
  { value: "reddit", label: "Reddit" },
  { value: "youtube", label: "YouTube" },
] as const;

type NarrativeMeta = Record<string, { label?: string; description?: string }>;

type TwitterNarrativeChartRow = {
  narrative: string;
  entity: string;
  positive: number;
  neutral: number;
  negative: number;
  total: number;
};

type TwitterNarrativePost = {
  entity: string;
  url: string;
  text: string;
  timestamp: string | null;
  engagement: { likes?: number; retweets?: number; comments?: number };
  narrative_primary: string | null;
  narrative_tags: string[];
  sentiment: string;
  sentiment_compound?: number | null;
};

type NarrativeSentimentRow = {
  narrative: string;
  entity: string;
  positive: number;
  neutral: number;
  negative: number;
  total: number;
};

type RedditTractionRow = {
  entity: string;
  narrative: string;
  total: number;
  engagement: number;
  subreddit_count: number;
  subreddits: string[];
  origin_subreddit?: string;
  amplifier_subreddit?: string;
  stage?: string;
  surface_counts?: Record<string, number>;
  recommendations?: string[];
  evidence?: { url: string; title?: string; subreddit?: string; snippet?: string; score?: number }[];
};

type NarrativeStrategyRow = {
  narrative: string;
  theme: string;
  sentiment: string;
  strength: string;
  relevance_to_company: string;
  company_presence: string;
  gap: string;
  recommended_action: string;
  content_direction: string;
};

export default function SentimentPage() {
  const { clientName: client, activeClient, ready: clientReady } = useActiveClient();
  const [competitor, setCompetitor] = useState<string>("");
  const [competitorFilter, setCompetitorFilter] = useState<string>("");
  const [range, setRange] = useState<string>("7d");
  const [sentimentFilter, setSentimentFilter] = useState<string>("");
  const [surface, setSurface] = useState<string>("all");
  const [summaries, setSummaries] = useState<SentimentSummary[]>([]);
  const [mentions, setMentions] = useState<MediaMentionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMentions, setLoadingMentions] = useState(true);

  const [twLoading, setTwLoading] = useState(true);
  const [twRefreshing, setTwRefreshing] = useState(false);
  const [twRefreshInfo, setTwRefreshInfo] = useState<string>("");
  const [twChartRows, setTwChartRows] = useState<TwitterNarrativeChartRow[]>([]);
  const [twPosts, setTwPosts] = useState<TwitterNarrativePost[]>([]);
  const [twMeta, setTwMeta] = useState<NarrativeMeta>({});

  const [nsLoading, setNsLoading] = useState(true);
  const [nsRows, setNsRows] = useState<NarrativeSentimentRow[]>([]);
  const [nsMeta, setNsMeta] = useState<NarrativeMeta>({});

  const [rtLoading, setRtLoading] = useState(true);
  const [rtRows, setRtRows] = useState<RedditTractionRow[]>([]);

  const [nsCompany, setNsCompany] = useState<string>("");
  const [nsClientType, setNsClientType] = useState<string>("Broker");
  const [nsExecLoading, setNsExecLoading] = useState<boolean>(false);
  const [nsExecRows, setNsExecRows] = useState<NarrativeStrategyRow[]>([]);
  const [nsExecError, setNsExecError] = useState<string>("");

  const entities = useMemo(() => {
    if (!activeClient) return [];
    return [activeClient.name, ...(activeClient.competitors ?? [])];
  }, [activeClient]);
  const effectiveEntity = competitorFilter.trim() || competitor;

  const dashboardCompanies = useMemo(() => {
    if (!activeClient) return [];
    const all = [activeClient.name, ...(activeClient.competitors ?? [])].filter(Boolean);
    const preferred = ["Sahi", "Zerodha", "Dhan", "Groww", "Kotak Securities"];
    const out: string[] = [];
    for (const p of preferred) if (all.includes(p)) out.push(p);
    for (const a of all) if (!out.includes(a)) out.push(a);
    return out.slice(0, 5);
  }, [activeClient]);

  useEffect(() => {
    if (!clientReady || !client?.trim()) {
      setSummaries([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    const params = new URLSearchParams({ client });
    if (effectiveEntity) params.set("entity", effectiveEntity);
    params.set("range", range);
    if (surface && surface !== "all") params.set("surface", surface);
    if (sentimentFilter) params.set("sentiment", sentimentFilter);
    fetch(withClientQuery(`${getApiBase()}/sentiment/summary?${params.toString()}`, client))
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(`HTTP ${res.status}`))))
      .then((data) => setSummaries(data.summaries ?? []))
      .catch(() => setSummaries([]))
      .finally(() => setLoading(false));
  }, [client, effectiveEntity, clientReady, surface, sentimentFilter, range]);

  useEffect(() => {
    if (!clientReady || !client?.trim()) {
      setMentions([]);
      setLoadingMentions(false);
      return;
    }
    setLoadingMentions(true);
    const params = new URLSearchParams({ client, range });
    if (sentimentFilter) params.set("sentiment", sentimentFilter);
    if (effectiveEntity) params.set("entity", effectiveEntity);
    if (surface && surface !== "all") params.set("surface", surface);
    fetch(withClientQuery(`${getApiBase()}/sentiment/mentions?${params.toString()}`, client))
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(`HTTP ${res.status}`))))
      .then((data) => setMentions(data.mentions ?? []))
      .catch(() => setMentions([]))
      .finally(() => setLoadingMentions(false));
  }, [client, range, sentimentFilter, effectiveEntity, clientReady, surface]);

  useEffect(() => {
    if (client && competitor && !entities.includes(competitor)) setCompetitor("");
  }, [client, competitor, entities]);
  const totalArticles = summaries.reduce((s, x) => s + x.positive + x.neutral + x.negative, 0);
  const totalPositive = summaries.reduce((s, x) => s + x.positive, 0);
  const totalNeutral = summaries.reduce((s, x) => s + x.neutral, 0);
  const totalNegative = summaries.reduce((s, x) => s + x.negative, 0);

  useEffect(() => {
    if (!clientReady || !client?.trim()) {
      setNsRows([]);
      setNsMeta({});
      setNsLoading(false);
      return;
    }
    setNsLoading(true);
    const params = new URLSearchParams({ client, range });
    if (surface && surface !== "all") params.set("surface", surface);
    if (effectiveEntity) params.set("entity", effectiveEntity);
    if (sentimentFilter) params.set("sentiment", sentimentFilter);
    fetch(withClientQuery(`${getApiBase()}/sentiment/narrative-sentiment?${params.toString()}`, client))
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(`HTTP ${res.status}`))))
      .then((data) => {
        setNsRows((data?.chart_rows ?? []) as NarrativeSentimentRow[]);
        setNsMeta((data?.narrative_meta ?? {}) as NarrativeMeta);
      })
      .catch(() => {
        setNsRows([]);
        setNsMeta({});
      })
      .finally(() => setNsLoading(false));
  }, [client, range, clientReady, surface, effectiveEntity, sentimentFilter]);

  useEffect(() => {
    if (!clientReady || !client?.trim()) {
      setRtRows([]);
      setRtLoading(false);
      return;
    }
    setRtLoading(true);
    const params = new URLSearchParams({ client, range });
    if (effectiveEntity) params.set("entity", effectiveEntity);
    fetch(withClientQuery(`${getApiBase()}/sentiment/reddit-traction?${params.toString()}`, client))
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(`HTTP ${res.status}`))))
      .then((data) => setRtRows((data?.rows ?? []) as RedditTractionRow[]))
      .catch(() => setRtRows([]))
      .finally(() => setRtLoading(false));
  }, [client, range, clientReady, effectiveEntity]);

  const loadTwitterNarratives = async (opts?: { refreshFirst?: boolean }) => {
    if (!clientReady || !client?.trim()) {
      setTwChartRows([]);
      setTwPosts([]);
      setTwMeta({});
      setTwLoading(false);
      return;
    }
    try {
      setTwLoading(true);
      setTwRefreshInfo("");
      if (opts?.refreshFirst) {
        setTwRefreshing(true);
        const params = new URLSearchParams({ client, range });
        const refreshRes = await fetch(withClientQuery(`${getApiBase()}/sentiment/twitter-narratives/refresh?${params.toString()}`, client), {
          method: "POST",
        });
        const refreshJson = await refreshRes.json().catch(() => null);
        if (!refreshRes.ok) {
          const detail =
            (refreshJson?.detail as string) ||
            (refreshJson?.message as string) ||
            (typeof refreshJson === "string" ? refreshJson : "");
          throw new Error(detail || `HTTP ${refreshRes.status}`);
        }
        const fetched = refreshJson?.counts?.fetched ?? 0;
        const inserted = refreshJson?.counts?.inserted ?? 0;
        const updated = refreshJson?.counts?.updated ?? 0;
        const skipped = refreshJson?.counts?.skipped ?? 0;
        const smt = refreshJson?.counts?.skipped_missing_text ?? 0;
        const smu = refreshJson?.counts?.skipped_missing_url ?? 0;
        const sbs = refreshJson?.counts?.skipped_bad_shape ?? 0;
        const previewKeys = Array.isArray(refreshJson?.first_item_preview?.keys)
          ? (refreshJson.first_item_preview.keys as string[]).slice(0, 12).join(", ")
          : "";
        const previewType = (refreshJson?.first_item_preview?.type as string) || "";
        setTwRefreshInfo(
          `Fetched ${fetched}, inserted ${inserted}, updated ${updated}, skipped ${skipped} (no text ${smt}, no url ${smu}, bad shape ${sbs}).`
          + (previewType || previewKeys ? ` First item: type=${previewType || "?"}, keys=[${previewKeys || "?"}]` : "")
        );
      }
      const params = new URLSearchParams({ client, range });
      if (effectiveEntity) params.set("entity", effectiveEntity);
      if (sentimentFilter) params.set("sentiment", sentimentFilter);
      const res = await fetch(withClientQuery(`${getApiBase()}/sentiment/twitter-narratives?${params.toString()}`, client));
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setTwChartRows((data?.chart_rows ?? []) as TwitterNarrativeChartRow[]);
      setTwPosts((data?.posts ?? []) as TwitterNarrativePost[]);
      setTwMeta((data?.narrative_meta ?? {}) as NarrativeMeta);
    } catch (e) {
      setTwChartRows([]);
      setTwPosts([]);
      setTwMeta({});
      const msg = e instanceof Error ? e.message : String(e);
      setTwRefreshInfo(msg ? `Refresh failed: ${msg}` : "Refresh failed. Check backend logs and APIFY_API_KEY.");
    } finally {
      setTwLoading(false);
      setTwRefreshing(false);
    }
  };

  useEffect(() => {
    loadTwitterNarratives();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client, range, effectiveEntity, sentimentFilter, clientReady]);

  if (!clientReady || !client) {
    return (
      <div className="min-h-screen bg-zinc-950 text-zinc-200 p-6">
        <p className="text-sm text-zinc-500">Loading client…</p>
      </div>
    );
  }

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
        {/* Narrative Intelligence: first screen — must stay above classic Sentiment blocks */}
        <NarrativeDashboard client={client} companies={dashboardCompanies} />

        <header className="mb-6 mt-2">
          <h1 className="text-2xl font-semibold text-zinc-100">Sentiment Analysis</h1>
          <p className="text-sm text-zinc-500 mt-1">
            Media tone for client and competitors. View counts and article-level mentions.
          </p>
        </header>

        <section className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-4 mb-6">
          <div className="flex flex-wrap items-end gap-4">
            <div className="flex items-center gap-2 text-sm text-zinc-400">
              <span className="font-medium">Client</span>
              <span className="text-zinc-200 font-semibold">{client}</span>
              <span className="text-xs text-zinc-500">(switch in header)</span>
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
            <div className="flex items-center gap-2">
              <label className="text-sm font-medium text-zinc-400">Source</label>
              <select
                value={surface}
                onChange={(e) => setSurface(e.target.value)}
                className="px-3 py-2 rounded-lg bg-zinc-800 border border-zinc-700 text-zinc-200 focus:outline-none focus:ring-2 focus:ring-zinc-600 min-w-[140px]"
              >
                {SOURCE_OPTIONS.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </section>

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

            <section className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-4 mb-6">
              <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
                <div>
                  <h2 className="text-lg font-semibold text-zinc-100">Narrative sentiment by taxonomy</h2>
                  <p className="text-xs text-zinc-500 mt-0.5">
                    X-axis is <span className="font-medium text-zinc-300">narrative_taxonomy.yaml</span> tag IDs. Each narrative shows client + competitors stacked by sentiment.
                  </p>
                </div>
                <div className="text-xs text-zinc-500">
                  Source: <span className="text-zinc-300 font-medium">{surface}</span>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-4 mb-3 text-xs text-zinc-500">
                <span className="font-medium text-zinc-400">Legend</span>
                <span className="inline-flex items-center gap-2">
                  <span className="w-3 h-3 rounded bg-emerald-600" />
                  Positive
                </span>
                <span className="inline-flex items-center gap-2">
                  <span className="w-3 h-3 rounded bg-zinc-500" />
                  Neutral
                </span>
                <span className="inline-flex items-center gap-2">
                  <span className="w-3 h-3 rounded bg-rose-600" />
                  Negative
                </span>
                <span className="inline-flex items-center gap-2">
                  <span className="w-3 h-3 rounded-full border border-zinc-600" />
                  Entity marker (client vs competitors)
                </span>
              </div>

              {nsLoading ? (
                <div className="py-10 text-center text-zinc-500">Loading narrative sentiment…</div>
              ) : Object.keys(nsMeta || {}).length === 0 ? (
                <div className="py-10 text-center text-zinc-500">
                  No narrative sentiment yet for this source/range. (For Reddit/YouTube this will appear after posts exist in <span className="text-zinc-300 font-medium">social_posts</span>.)
                </div>
              ) : (
                (() => {
                  // Build dense, viewport-fitting grouped-stacked bar chart in SVG.
                  const narrativeIds = Object.keys(nsMeta || {}).sort();
                  const entityList = entities.length ? entities : [];
                  const byKey = new Map<string, NarrativeSentimentRow>();
                  for (const r of nsRows) {
                    if (!r?.narrative || !r?.entity) continue;
                    byKey.set(`${r.narrative}__${r.entity}`, r);
                  }

                  // y scale: max total per (narrative, entity)
                  let yMax = 1;
                  for (const nid of narrativeIds) {
                    for (const e of entityList) {
                      const row = byKey.get(`${nid}__${e}`);
                      yMax = Math.max(yMax, row?.total || 0);
                    }
                  }
                  if (yMax < 1) yMax = 1;

                  const W = 1200; // viewBox width (scales responsively)
                  const H = 360; // viewBox height
                  const padL = 48;
                  const padR = 16;
                  const padT = 14;
                  const padB = 70;
                  const plotW = W - padL - padR;
                  const plotH = H - padT - padB;

                  const n = Math.max(1, narrativeIds.length);
                  const groupW = plotW / n;
                  const innerGap = 2;
                  const barCount = Math.max(1, entityList.length);
                  const barW = Math.max(1, Math.floor((groupW - innerGap * (barCount - 1)) / barCount));

                  const y = (v: number) => padT + plotH - (v / yMax) * plotH;
                  const h = (v: number) => (v / yMax) * plotH;

                  const tickEvery = n > 50 ? 10 : n > 25 ? 5 : n > 12 ? 2 : 1;

                  return (
                    <div className="w-full">
                      <div className="rounded-lg border border-zinc-800 bg-zinc-950/30 p-2">
                        <svg
                          viewBox={`0 0 ${W} ${H}`}
                          className="w-full h-[360px]"
                          role="img"
                          aria-label="Narrative sentiment grouped stacked bar chart"
                        >
                          {/* Axes */}
                          <line x1={padL} y1={padT} x2={padL} y2={padT + plotH} stroke="#3f3f46" strokeWidth="1" />
                          <line x1={padL} y1={padT + plotH} x2={padL + plotW} y2={padT + plotH} stroke="#3f3f46" strokeWidth="1" />

                          {/* Y ticks */}
                          {[0, 0.25, 0.5, 0.75, 1].map((p) => {
                            const val = Math.round(yMax * p);
                            const yy = y(val);
                            return (
                              <g key={p}>
                                <line x1={padL} y1={yy} x2={padL + plotW} y2={yy} stroke="#27272a" strokeWidth="1" />
                                <text x={padL - 6} y={yy + 4} textAnchor="end" fontSize="10" fill="#a1a1aa">
                                  {val}
                                </text>
                              </g>
                            );
                          })}

                          {/* Bars */}
                          {narrativeIds.map((nid, i) => {
                            const x0 = padL + i * groupW;
                            return (
                              <g key={nid}>
                                {entityList.map((e, j) => {
                                  const row =
                                    byKey.get(`${nid}__${e}`) ||
                                    ({ narrative: nid, entity: e, positive: 0, neutral: 0, negative: 0, total: 0 } as NarrativeSentimentRow);

                                  const bx = x0 + j * (barW + innerGap);
                                  const total = row.total || 0;
                                  const pos = row.positive || 0;
                                  const neu = row.neutral || 0;
                                  const neg = row.negative || 0;

                                  const entityStroke = getEntityHex(e);
                                  let yCursor = padT + plotH;
                                  const segs: Array<{ k: "positive" | "neutral" | "negative"; v: number; color: string }> = [
                                    { k: "positive", v: pos, color: "#16a34a" },
                                    { k: "neutral", v: neu, color: "#71717a" },
                                    { k: "negative", v: neg, color: "#e11d48" },
                                  ];

                                  return (
                                    <g key={e}>
                                      {/* outline so each entity is visible */}
                                      <rect
                                        x={bx}
                                        y={y(total)}
                                        width={barW}
                                        height={Math.max(0, h(total))}
                                        fill="transparent"
                                        stroke={entityStroke}
                                        strokeWidth="1"
                                      />
                                      {segs.map((s) => {
                                        if (s.v <= 0) return null;
                                        const segH = h(s.v);
                                        yCursor -= segH;
                                        return (
                                          <rect
                                            key={s.k}
                                            x={bx}
                                            y={yCursor}
                                            width={barW}
                                            height={segH}
                                            fill={s.color}
                                          >
                                            <title>
                                              {nid} • {e}\nTotal: {total}\nPositive: {pos}\nNeutral: {neu}\nNegative: {neg}
                                            </title>
                                          </rect>
                                        );
                                      })}
                                    </g>
                                  );
                                })}

                                {/* X labels (skip to fit viewport) */}
                                {i % tickEvery === 0 ? (
                                  <text
                                    x={x0 + groupW / 2}
                                    y={padT + plotH + 16}
                                    textAnchor="middle"
                                    fontSize="9"
                                    fill="#a1a1aa"
                                  >
                                    {nid}
                                  </text>
                                ) : null}
                              </g>
                            );
                          })}

                          {/* Entity legend (dots) */}
                          <g transform={`translate(${padL}, ${padT + plotH + 34})`}>
                            {entityList.slice(0, 6).map((e, idx) => {
                              const xx = idx * 190;
                              const hex = getEntityHex(e);
                              return (
                                <g key={e} transform={`translate(${xx}, 0)`}>
                                  <circle cx="6" cy="6" r="5" fill={hex} stroke="#3f3f46" strokeWidth="1" />
                                  <text x="16" y="10" fontSize="10" fill="#d4d4d8">
                                    {e}
                                  </text>
                                </g>
                              );
                            })}
                            {entityList.length > 6 ? (
                              <text x={6 * 190} y={10} fontSize="10" fill="#a1a1aa">
                                +{entityList.length - 6} more…
                              </text>
                            ) : null}
                          </g>
                        </svg>
                      </div>
                      <div className="mt-2 text-xs text-zinc-500">
                        Hover bars for exact counts. X-axis labels are auto-skipped to fit the viewport (all narratives are still included in the chart).
                      </div>

                      {/* Matrix table: every taxonomy x every entity (no guessing) */}
                      <div className="mt-4 rounded-lg border border-zinc-800 bg-zinc-950/30 overflow-hidden">
                        <div className="px-3 py-2 border-b border-zinc-800 flex items-center justify-between">
                          <div className="text-sm font-semibold text-zinc-200">Narrative per company</div>
                          <div className="text-xs text-zinc-500">
                            <span className="inline-flex items-center gap-2 mr-3">
                              <span className="w-3 h-3 rounded bg-emerald-600" /> Positive
                            </span>
                            <span className="inline-flex items-center gap-2 mr-3">
                              <span className="w-3 h-3 rounded bg-zinc-500" /> Neutral
                            </span>
                            <span className="inline-flex items-center gap-2">
                              <span className="w-3 h-3 rounded bg-rose-600" /> Negative
                            </span>
                          </div>
                        </div>
                        <div className="max-h-[520px] overflow-auto">
                          <table className="min-w-[980px] w-full text-left text-sm">
                            <thead className="sticky top-0 bg-zinc-900/80 backdrop-blur border-b border-zinc-800">
                              <tr>
                                <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-zinc-300 w-[260px]">
                                  Narrative
                                </th>
                                {entityList.map((e) => (
                                  <th key={e} className="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-zinc-300">
                                    <span className="inline-flex items-center gap-2">
                                      <span
                                        className="w-2.5 h-2.5 rounded-full border border-zinc-700"
                                        style={{ backgroundColor: getEntityHex(e) }}
                                      />
                                      {e}
                                    </span>
                                  </th>
                                ))}
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-zinc-800">
                              {narrativeIds.map((nid) => {
                                const meta = nsMeta?.[nid] || {};
                                const label = (meta.label || nid).trim();
                                const narrativeTone =
                                  label.toLowerCase().includes("risk") || label.toLowerCase().includes("fraud") || label.toLowerCase().includes("scam")
                                    ? "border-l-rose-600/70 bg-rose-500/5"
                                    : label.toLowerCase().includes("growth") || label.toLowerCase().includes("launch") || label.toLowerCase().includes("product")
                                      ? "border-l-emerald-600/70 bg-emerald-500/5"
                                      : "border-l-zinc-600/70 bg-zinc-500/5";
                                return (
                                  <tr key={nid} className={"hover:bg-zinc-900/30 border-l-2 " + narrativeTone}>
                                    <td className="px-3 py-2 align-top">
                                      <div className="text-xs text-zinc-400" title={nid}>{nid}</div>
                                      <div className="text-sm font-medium text-zinc-100 line-clamp-2" title={label}>{label}</div>
                                    </td>
                                    {entityList.map((e) => {
                                      const row =
                                        byKey.get(`${nid}__${e}`) ||
                                        ({ narrative: nid, entity: e, positive: 0, neutral: 0, negative: 0, total: 0 } as NarrativeSentimentRow);
                                      const total = row.total || 0;
                                      const pos = row.positive || 0;
                                      const neu = row.neutral || 0;
                                      const neg = row.negative || 0;
                                      const denom = total || 1;
                                      const wPos = (pos / denom) * 100;
                                      const wNeu = (neu / denom) * 100;
                                      const wNeg = (neg / denom) * 100;
                                      return (
                                        <td key={e} className="px-3 py-2 align-top">
                                          <div className="flex items-center gap-2">
                                            <div
                                              className="flex-1 h-4 rounded overflow-hidden bg-zinc-800 border border-zinc-700"
                                              title={`${nid} • ${e}\nTotal: ${total}\nPositive: ${pos}\nNeutral: ${neu}\nNegative: ${neg}`}
                                            >
                                              {total > 0 ? (
                                                <div className="w-full h-full flex">
                                                  {wPos > 0 ? (
                                                    <div
                                                      className="h-full"
                                                      style={{ width: `${wPos}%`, backgroundColor: "#16a34a" }}
                                                    />
                                                  ) : null}
                                                  {wNeu > 0 ? (
                                                    <div
                                                      className="h-full"
                                                      style={{ width: `${wNeu}%`, backgroundColor: "#71717a" }}
                                                    />
                                                  ) : null}
                                                  {wNeg > 0 ? (
                                                    <div
                                                      className="h-full"
                                                      style={{ width: `${wNeg}%`, backgroundColor: "#e11d48" }}
                                                    />
                                                  ) : null}
                                                  {wPos === 0 && wNeu === 0 && wNeg === 0 ? (
                                                    <div className="h-full" style={{ width: "100%", backgroundColor: "#71717a" }} />
                                                  ) : null}
                                                </div>
                                              ) : (
                                                <div className="h-full bg-zinc-800" style={{ width: "100%" }} />
                                              )}
                                            </div>
                                            <div className="w-8 text-right text-xs text-zinc-500 tabular-nums">{total}</div>
                                          </div>
                                        </td>
                                      );
                                    })}
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    </div>
                  );
                })()
              )}
            </section>

            <section className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-4 mb-6">
              <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
                <div>
                  <h2 className="text-lg font-semibold text-zinc-100">Twitter narrative sentiment (Apify)</h2>
                  <p className="text-xs text-zinc-500 mt-0.5">
                    Narratives come from <span className="font-medium text-zinc-300">narrative_taxonomy.yaml</span>. Tweets are fetched via Apify and stored in MongoDB.
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => loadTwitterNarratives({ refreshFirst: true })}
                    disabled={twRefreshing || !clientReady}
                    className={`px-3 py-2 rounded-lg text-sm font-medium border transition-colors ${
                      twRefreshing
                        ? "bg-zinc-800 text-zinc-500 border-zinc-700 cursor-not-allowed"
                        : "bg-zinc-800 text-zinc-200 border-zinc-700 hover:bg-zinc-700"
                    }`}
                  >
                    {twRefreshing ? "Refreshing…" : "Refresh tweets"}
                  </button>
                </div>
              </div>
              {twRefreshInfo ? (
                <div className="mb-3 text-xs text-zinc-400">
                  {twRefreshInfo}
                </div>
              ) : null}

              {twLoading ? (
                <div className="py-10 text-center text-zinc-500">Loading Twitter narratives…</div>
              ) : twChartRows.length === 0 ? (
                <div className="py-10 text-center text-zinc-500">
                  No Twitter narrative data yet. Click <span className="text-zinc-300 font-medium">Refresh tweets</span> to fetch from Apify.
                </div>
              ) : (
                <>
                  {/* Column chart: X = narrative id; within each column, per-entity stacked sentiment bar */}
                  <div className="overflow-x-auto pb-2">
                    <div className="grid grid-flow-col auto-cols-[240px] gap-3 min-h-[280px]">
                      {(() => {
                        const byNarr = new Map<string, Record<string, TwitterNarrativeChartRow>>();
                        let maxTotal = 1;
                        for (const r of twChartRows) {
                          if (!r?.narrative) continue;
                          if (!byNarr.has(r.narrative)) byNarr.set(r.narrative, {});
                          byNarr.get(r.narrative)![r.entity] = r;
                          maxTotal = Math.max(maxTotal, r.total || 0);
                        }
                        const narrativeIds = Array.from(byNarr.keys()).sort();
                        return narrativeIds.map((nid) => {
                          const meta = twMeta?.[nid] || {};
                          const label = (meta.label || nid).trim();
                          const entMap = byNarr.get(nid) || {};
                          return (
                            <div key={nid} className="rounded-lg border border-zinc-800 bg-zinc-950/30 p-3">
                              <div className="mb-2">
                                <div className="text-xs text-zinc-400 line-clamp-1" title={nid}>
                                  {nid}
                                </div>
                                <div className="text-sm font-semibold text-zinc-100 line-clamp-2" title={label}>
                                  {label}
                                </div>
                              </div>
                              <div className="space-y-2">
                                {entities.map((e) => {
                                  const row = entMap[e];
                                  if (!row || row.total <= 0) return null;
                                  const pctPos = (row.positive / (row.total || 1)) * 100;
                                  const pctNeu = (row.neutral / (row.total || 1)) * 100;
                                  const pctNeg = (row.negative / (row.total || 1)) * 100;
                                  const heightPx = Math.max(10, Math.round((row.total / maxTotal) * 26));
                                  return (
                                    <div key={e} className="flex items-center gap-2">
                                      <div className="w-20 text-[11px] text-zinc-400 truncate" title={e}>
                                        {e}
                                      </div>
                                      <div className="flex-1">
                                        <div
                                          className="w-full flex rounded overflow-hidden bg-zinc-800"
                                          style={{ height: `${heightPx}px` }}
                                          title={`${e}: ${row.total} tweets (pos ${row.positive}, neu ${row.neutral}, neg ${row.negative})`}
                                        >
                                          {pctPos > 0 && <div className="h-full bg-emerald-600" style={{ width: `${pctPos}%` }} />}
                                          {pctNeu > 0 && <div className="h-full bg-zinc-500" style={{ width: `${pctNeu}%` }} />}
                                          {pctNeg > 0 && <div className="h-full bg-rose-600" style={{ width: `${pctNeg}%` }} />}
                                        </div>
                                      </div>
                                      <div className="w-10 text-right text-[11px] text-zinc-500 tabular-nums">{row.total}</div>
                                    </div>
                                  );
                                })}
                              </div>
                              {meta.description ? (
                                <div className="mt-2 text-[11px] text-zinc-500 line-clamp-2" title={meta.description}>
                                  {meta.description}
                                </div>
                              ) : null}
                            </div>
                          );
                        });
                      })()}
                    </div>
                  </div>

                  {/* Posts table */}
                  <div className="mt-5">
                    <div className="flex items-center justify-between mb-2">
                      <h3 className="text-sm font-semibold text-zinc-300">Tweet details</h3>
                      <span className="text-xs text-zinc-500">{twPosts.length} rows (latest)</span>
                    </div>
                    <div className="overflow-auto rounded-lg border border-zinc-800">
                      <table className="min-w-[980px] w-full text-left text-sm">
                        <thead className="bg-zinc-900/60 text-zinc-300">
                          <tr>
                            <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wider">Date</th>
                            <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wider">Entity</th>
                            <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wider">Narrative</th>
                            <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wider">Sentiment</th>
                            <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wider">Engagement</th>
                            <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wider">Text</th>
                            <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wider">Link</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-zinc-800 bg-zinc-950/30">
                          {twPosts.map((p, idx) => {
                            const nid = p.narrative_primary || "";
                            const meta = nid ? (twMeta?.[nid] || {}) : {};
                            const narrLabel = nid ? (meta.label || nid) : "—";
                            const d = p.timestamp ? new Date(p.timestamp) : null;
                            const when = d ? d.toLocaleString() : "";
                            const likes = p.engagement?.likes ?? 0;
                            const rts = p.engagement?.retweets ?? 0;
                            const cmts = p.engagement?.comments ?? 0;
                            const s = (p.sentiment || "neutral").toLowerCase();
                            const sClass =
                              s === "positive"
                                ? "text-emerald-400"
                                : s === "negative"
                                  ? "text-rose-400"
                                  : "text-zinc-300";
                            return (
                              <tr key={p.url || idx} className="hover:bg-zinc-900/40">
                                <td className="px-3 py-2 text-xs text-zinc-500 whitespace-nowrap">{when}</td>
                                <td className="px-3 py-2 text-zinc-200 whitespace-nowrap">{p.entity}</td>
                                <td className="px-3 py-2 text-zinc-300">
                                  {nid ? (
                                    <span title={nid}>{narrLabel}</span>
                                  ) : (
                                    <span className="text-zinc-600">Unclassified</span>
                                  )}
                                </td>
                                <td className={`px-3 py-2 font-medium whitespace-nowrap ${sClass}`}>{s}</td>
                                <td className="px-3 py-2 text-xs text-zinc-500 whitespace-nowrap tabular-nums">
                                  ❤ {likes} · ↻ {rts} · 💬 {cmts}
                                </td>
                                <td className="px-3 py-2 text-zinc-300 max-w-[520px]">
                                  <span className="line-clamp-2">{p.text}</span>
                                </td>
                                <td className="px-3 py-2">
                                  {p.url ? (
                                    <a
                                      href={p.url}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      className="text-zinc-300 hover:text-white"
                                    >
                                      Open →
                                    </a>
                                  ) : (
                                    <span className="text-zinc-600">—</span>
                                  )}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </>
              )}
            </section>

            <section className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-4 mb-6">
              <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
                <div>
                  <h2 className="text-lg font-semibold text-zinc-100">Reddit narrative traction</h2>
                  <p className="text-xs text-zinc-500 mt-0.5">
                    Cross-subreddit narrative signals (origin, amplification, stage) with evidence links.
                  </p>
                </div>
                <div className="text-xs text-zinc-500">
                  Uses <span className="text-zinc-300 font-medium">public Reddit JSON</span> + your{" "}
                  <span className="text-zinc-300 font-medium">narrative taxonomy</span>.
                </div>
              </div>

              {rtLoading ? (
                <div className="py-12 text-center text-zinc-500">Loading Reddit traction…</div>
              ) : rtRows.length === 0 ? (
                <div className="py-12 text-center text-zinc-500">
                  No Reddit narrative traction yet for the selected client/range. Run the ingest script, then refresh.
                </div>
              ) : (
                <div className="rounded-lg border border-zinc-800 overflow-hidden">
                  <div className="max-h-[520px] overflow-auto">
                    <table className="min-w-[980px] w-full text-left text-sm">
                      <thead className="sticky top-0 bg-zinc-900/80 backdrop-blur border-b border-zinc-800">
                        <tr>
                          <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-zinc-300">Narrative</th>
                          <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-zinc-300">Entity</th>
                          <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-zinc-300 text-right">Mentions</th>
                          <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-zinc-300 text-right">Engagement</th>
                          <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-zinc-300">Stage</th>
                          <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-zinc-300">Origin → Amplified</th>
                          <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-zinc-300">Gaps / Next actions</th>
                          <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-zinc-300">Evidence</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-zinc-800">
                        {rtRows.slice(0, 80).map((r, idx) => {
                          const sc = r.surface_counts || {};
                          const gaps = [
                            (sc.news || 0) > 0 ? null : "news",
                            (sc.forums || 0) > 0 ? null : "forums",
                            (sc.youtube || 0) > 0 ? null : "youtube",
                          ].filter(Boolean) as string[];
                          const stage = (r.stage || "unknown").toLowerCase();
                          const stageColor =
                            stage === "growing"
                              ? "bg-emerald-500/15 text-emerald-200 border-emerald-600/40"
                              : stage === "declining"
                                ? "bg-rose-500/15 text-rose-200 border-rose-600/40"
                                : stage === "emerging"
                                  ? "bg-amber-500/15 text-amber-200 border-amber-600/40"
                                  : "bg-zinc-500/10 text-zinc-200 border-zinc-600/40";
                          const ev = (r.evidence || []).slice(0, 2);
                          return (
                            <tr key={`${r.narrative}__${r.entity}__${idx}`} className="hover:bg-zinc-900/30">
                              <td className="px-3 py-2 align-top">
                                <div className="text-xs text-zinc-400" title={r.narrative}>
                                  {r.narrative}
                                </div>
                                <div className="text-sm font-medium text-zinc-100">
                                  {(nsMeta?.[r.narrative]?.label || r.narrative) as string}
                                </div>
                              </td>
                              <td className="px-3 py-2 align-top">
                                <span className="inline-flex items-center gap-2">
                                  <span
                                    className="w-2.5 h-2.5 rounded-full border border-zinc-700"
                                    style={{ backgroundColor: getEntityHex(r.entity) }}
                                  />
                                  <span className="text-zinc-200">{r.entity}</span>
                                </span>
                              </td>
                              <td className="px-3 py-2 align-top text-right tabular-nums text-zinc-200">{r.total}</td>
                              <td className="px-3 py-2 align-top text-right tabular-nums text-zinc-400">{r.engagement}</td>
                              <td className="px-3 py-2 align-top">
                                <span className={`inline-flex px-2 py-1 rounded border text-xs ${stageColor}`}>{stage}</span>
                              </td>
                              <td className="px-3 py-2 align-top text-xs text-zinc-300">
                                <div className="text-zinc-400">
                                  r/{(r.origin_subreddit || "—").toString()}
                                </div>
                                <div className="text-zinc-300">
                                  → r/{(r.amplifier_subreddit || "—").toString()}
                                </div>
                                <div className="text-[11px] text-zinc-500 mt-1">
                                  {r.subreddit_count} subs
                                </div>
                              </td>
                              <td className="px-3 py-2 align-top text-xs">
                                <div className="text-zinc-400 mb-1">
                                  Gaps: {gaps.length ? gaps.join(", ") : "none"}
                                </div>
                                <div className="space-y-1">
                                  {(r.recommendations || []).slice(0, 2).map((rec, i) => (
                                    <div key={i} className="text-zinc-200">
                                      - {rec}
                                    </div>
                                  ))}
                                </div>
                              </td>
                              <td className="px-3 py-2 align-top text-xs">
                                {ev.length ? (
                                  <div className="space-y-1">
                                    {ev.map((e, i) => (
                                      <div key={i}>
                                        <a
                                          href={e.url}
                                          target="_blank"
                                          rel="noopener noreferrer"
                                          className="text-zinc-300 hover:text-white"
                                          title={e.snippet || ""}
                                        >
                                          {e.subreddit ? `r/${e.subreddit} • ` : ""}
                                          {(e.title || "Open post").slice(0, 68)}
                                          {(e.title || "").length > 68 ? "…" : ""}
                                        </a>
                                      </div>
                                    ))}
                                  </div>
                                ) : (
                                  <span className="text-zinc-600">—</span>
                                )}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                  <div className="px-3 py-2 border-t border-zinc-800 text-xs text-zinc-500">
                    Showing top {Math.min(80, rtRows.length)} by engagement. Stage = emerging/growing/mature/declining from time buckets in the selected range.
                  </div>
                </div>
              )}
            </section>

            <section className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-4 mb-6">
              <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
                <div>
                  <h2 className="text-lg font-semibold text-zinc-100">Narrative Strategy Engine (Reddit)</h2>
                  <p className="text-xs text-zinc-500 mt-0.5">
                    Theme-first narratives → gaps → actions. No stock recommendations.
                  </p>
                </div>
              </div>

              <div className="flex flex-wrap gap-2 items-center mb-3">
                <input
                  value={nsCompany}
                  onChange={(e) => setNsCompany(e.target.value)}
                  placeholder="Company (e.g., SBI, Paytm, Bajaj Finance)"
                  className="w-full md:w-[420px] px-3 py-2 rounded-lg bg-zinc-950/40 border border-zinc-800 text-zinc-200 placeholder:text-zinc-600"
                />
                <select
                  value={nsClientType}
                  onChange={(e) => setNsClientType(e.target.value)}
                  className="px-3 py-2 rounded-lg bg-zinc-950/40 border border-zinc-800 text-zinc-200"
                >
                  <option value="Bank">Bank</option>
                  <option value="NBFC">NBFC</option>
                  <option value="Fintech">Fintech</option>
                  <option value="Broker">Broker</option>
                </select>
                <button
                  disabled={nsExecLoading || !nsCompany.trim()}
                  onClick={() => {
                    const company = nsCompany.trim();
                    setNsExecError("");
                    setNsExecLoading(true);
                    fetch(
                      withClientQuery(
                        `${getApiBase()}/narrative-strategy/reddit/engine?company=${encodeURIComponent(company)}&vertical=${encodeURIComponent(
                          nsClientType.toLowerCase()
                        )}&limit=8&use_llm=false`,
                        client
                      )
                    )
                      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(`HTTP ${res.status}`))))
                      .then((data) => setNsExecRows((data ?? []) as NarrativeStrategyRow[]))
                      .catch((e) => {
                        setNsExecRows([]);
                        setNsExecError(String(e?.message || e || "Failed"));
                      })
                      .finally(() => setNsExecLoading(false));
                  }}
                  className={`px-3 py-2 rounded-lg text-sm font-medium border transition-colors ${
                    nsExecLoading || !nsCompany.trim()
                      ? "bg-zinc-800 text-zinc-500 border-zinc-700 cursor-not-allowed"
                      : "bg-zinc-800 text-zinc-200 border-zinc-700 hover:bg-zinc-700"
                  }`}
                >
                  {nsExecLoading ? "Generating…" : "Generate strategy"}
                </button>
                <div className="text-xs text-zinc-500 ml-auto">Range (for context): {range}</div>
              </div>

              {nsExecError ? <div className="text-xs text-rose-300 mb-2">{nsExecError}</div> : null}

              {nsExecLoading ? (
                <div className="py-10 text-center text-zinc-500">Generating narrative strategy…</div>
              ) : nsExecRows.length === 0 ? (
                <div className="py-8 text-center text-zinc-500">
                  Enter a company and generate. Make sure Reddit ingest has run recently.
                </div>
              ) : (
                <div className="rounded-lg border border-zinc-800 overflow-hidden">
                  <div className="max-h-[520px] overflow-auto">
                    <table className="min-w-[980px] w-full text-left text-sm">
                      <thead className="sticky top-0 bg-zinc-900/80 backdrop-blur border-b border-zinc-800">
                        <tr>
                          <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-zinc-300">Theme</th>
                          <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-zinc-300">Narrative</th>
                          <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-zinc-300">Sentiment</th>
                          <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-zinc-300">Strength</th>
                          <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-zinc-300">Presence</th>
                          <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-zinc-300">Gap</th>
                          <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-zinc-300">Recommended action</th>
                          <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-zinc-300">Content direction</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-zinc-800">
                        {nsExecRows.map((r, i) => (
                          <tr key={i} className="hover:bg-zinc-900/30 align-top">
                            <td className="px-3 py-2 text-zinc-200 font-medium">{r.theme}</td>
                            <td className="px-3 py-2 text-zinc-200">{r.narrative}</td>
                            <td className="px-3 py-2 text-zinc-300">{r.sentiment}</td>
                            <td className="px-3 py-2 text-zinc-300">{r.strength}</td>
                            <td className="px-3 py-2 text-zinc-300">{r.company_presence}</td>
                            <td className="px-3 py-2 text-zinc-300">{r.gap}</td>
                            <td className="px-3 py-2 text-zinc-200">{r.recommended_action}</td>
                            <td className="px-3 py-2 text-zinc-300">{r.content_direction}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </section>

            <section className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-4">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold text-zinc-100">
                  {surface === "reddit"
                    ? "Reddit discussions"
                    : surface === "youtube"
                      ? "YouTube videos"
                      : surface === "forums"
                        ? "Forum mentions"
                        : surface === "news"
                          ? "News mentions"
                          : "All mentions"}
                </h2>
                <span className="text-sm text-zinc-500">{mentions.length} items</span>
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
      </div>
    </div>
  );
}
