"use client";

import { useState, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { CoverageChart, CoverageRow } from "@/components/CoverageChart";
import Link from "next/link";
import { getApiBase, withClientQuery } from "@/lib/api";
import { useActiveClient } from "@/context/ClientContext";

interface CompetitorOnlyArticle {
  url: string;
  title: string;
  summary: string;
  source_domain: string;
  published_at: string;
  entities: string[];
  author?: string | null;
  ai_summary?: string | null;
}

interface MentionRow {
  url: string;
  title: string;
  summary: string;
  source_domain: string;
  published_at: string;
  entity: string;
  author?: string | null;
}

const TABLE_HEAD_CLASS =
  "text-left py-3 px-4 text-zinc-300 font-medium border-b border-zinc-700 bg-zinc-800/80";
const TABLE_CELL_CLASS = "py-3 px-4 text-zinc-200 border-b border-zinc-800";
const TABLE_CELL_MUTED = "py-3 px-4 text-zinc-400 border-b border-zinc-800";

export default function CoveragePage() {
  const { clientName: clientFilter, ready: clientReady } = useActiveClient();
  const [coverage, setCoverage] = useState<CoverageRow[]>([]);
  const [competitorOnly, setCompetitorOnly] = useState<{
    has_competitor_only_articles: boolean;
    count: number;
    articles: CompetitorOnlyArticle[];
  } | null>(null);
  const [counts, setCounts] = useState<{
    total_articles: number;
    articles_with_client_mentioned: number;
    competitor_only_articles: number;
    articles_with_entities_populated: number;
    pipeline_note?: string;
  } | null>(null);
  const [mentions, setMentions] = useState<{ mentions: MentionRow[]; count: number } | null>(null);
  const [prSummary, setPrSummary] = useState<{
    summary: string | null;
    date: string | null;
    computed_at: string | null;
  } | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchCoverage() {
      const cname = clientFilter?.trim() ?? "";
      if (!clientReady || !cname) {
        setCoverage([]);
        setCompetitorOnly(null);
        setCounts(null);
        setMentions(null);
        setPrSummary(null);
        setLoading(false);
        return;
      }
      setLoading(true);
      try {
        const [covRes, compRes, countsRes, mentionsRes, summaryRes] = await Promise.all([
          fetch(
            withClientQuery(
              `${getApiBase()}/coverage/competitors?client=${encodeURIComponent(cname)}`,
              cname
            )
          ),
          fetch(
            withClientQuery(
              `${getApiBase()}/coverage/competitor-only-articles?client=${encodeURIComponent(cname)}&limit=20`,
              cname
            )
          ),
          fetch(
            withClientQuery(
              `${getApiBase()}/coverage/article-counts?client=${encodeURIComponent(cname)}`,
              cname
            )
          ),
          fetch(
            withClientQuery(
              `${getApiBase()}/coverage/mentions?client=${encodeURIComponent(cname)}&limit=20`,
              cname
            )
          ),
          fetch(
            withClientQuery(
              `${getApiBase()}/coverage/pr-summary?client=${encodeURIComponent(cname)}`,
              cname
            )
          ),
        ]);
        if (!covRes.ok) throw new Error(`HTTP ${covRes.status}`);
        if (!compRes.ok) throw new Error(`HTTP ${compRes.status}`);
        if (!countsRes.ok) throw new Error(`HTTP ${countsRes.status}`);
        const covData = await covRes.json();
        const compData = await compRes.json();
        const countsData = await countsRes.json();
        const mentionsData = mentionsRes.ok ? await mentionsRes.json() : { mentions: [], count: 0 };
        const summaryData = summaryRes.ok ? await summaryRes.json() : { summary: null, date: null, computed_at: null };

        setCoverage(covData.coverage ?? []);
        setCompetitorOnly({
          has_competitor_only_articles: compData.has_competitor_only_articles ?? false,
          count: compData.count ?? 0,
          articles: compData.articles ?? [],
        });
        setCounts({
          total_articles: countsData.total_articles ?? 0,
          articles_with_client_mentioned: countsData.articles_with_client_mentioned ?? 0,
          competitor_only_articles: countsData.competitor_only_articles ?? 0,
          articles_with_entities_populated: countsData.articles_with_entities_populated ?? 0,
          pipeline_note: countsData.pipeline_note,
        });
        setMentions({
          mentions: mentionsData.mentions ?? [],
          count: mentionsData.count ?? 0,
        });
        setPrSummary({
          summary: summaryData.summary ?? null,
          date: summaryData.date ?? null,
          computed_at: summaryData.computed_at ?? null,
        });
      } catch (err) {
        console.error("fetchCoverage failed:", err);
        setCoverage([]);
        setCompetitorOnly(null);
        setCounts(null);
        setMentions(null);
        setPrSummary(null);
      } finally {
        setLoading(false);
      }
    }
    fetchCoverage();
    // clientFilter + clientReady drive refetch when header client changes
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: sync fetches to active client
  }, [clientFilter, clientReady]);

  if (!clientReady || !clientFilter) {
    return (
      <div className="app-page min-h-screen bg-zinc-950 text-zinc-100 p-6">
        <p className="text-zinc-400">Loading client…</p>
      </div>
    );
  }

  return (
    <div className="app-page min-h-screen bg-zinc-950 text-zinc-100">
      <div className="max-w-5xl mx-auto px-4 py-6 md:px-6 md:py-8">
        <nav className="flex flex-wrap items-center gap-3 mb-6 text-base">
          <Link href="/" className="text-zinc-400 hover:text-zinc-200 transition-colors">
            ← Chat
          </Link>
          <Link href="/clients" className="text-zinc-400 hover:text-zinc-200 transition-colors">
            Clients
          </Link>
          <Link href="/media" className="text-zinc-400 hover:text-zinc-200 transition-colors">
            Media
          </Link>
          <Link href="/media-intelligence" className="text-zinc-400 hover:text-zinc-200 transition-colors">
            Media Intelligence
          </Link>
          <Link href="/sentiment" className="text-zinc-400 hover:text-zinc-200 transition-colors">
            Sentiment
          </Link>
          <Link href="/topics" className="text-zinc-400 hover:text-zinc-200 transition-colors">
            Topics
          </Link>
        </nav>

        <header className="mb-6">
          <h1 className="text-2xl font-semibold text-zinc-100 tracking-tight">
            Competitor Coverage
          </h1>
          <p className="mt-2 text-base text-zinc-300 max-w-xl">
            Compare media mentions for your client and competitors. Use the summary below for actionable PR intel (refreshed once per day).
          </p>
        </header>

        <p className="mb-6 text-base text-zinc-400">
          Client: <strong className="text-zinc-100">{clientFilter}</strong> (header switcher)
        </p>

        <CoverageChart coverage={coverage} loading={loading} />

        {/* PR summary at top — LLM-generated once per day */}
        {clientFilter && (
          <section className="mt-8 rounded-xl border border-zinc-800 bg-zinc-900/40 p-5">
            <h2 className="text-lg font-semibold text-zinc-100 mb-1">
              Coverage intel for PR team
            </h2>
            <p className="text-sm text-zinc-400 mb-4">
              Summary of client vs competitor coverage and recommended actions (generated once per day).
            </p>
            {loading ? (
              <div className="text-zinc-400 py-4">Loading summary…</div>
            ) : prSummary?.summary ? (
              <div className="rounded-lg bg-zinc-950 border border-zinc-800 p-4">
                {prSummary.date && (
                  <p className="text-sm text-zinc-500 mb-3">
                    As of {prSummary.date}
                    {prSummary.computed_at && (
                      <span className="ml-2">· Last run: {new Date(prSummary.computed_at).toLocaleString()}</span>
                    )}
                  </p>
                )}
                <div className="prose prose-invert prose-sm max-w-none text-zinc-200 [&_h2]:text-zinc-100 [&_h2]:text-base [&_ul]:my-2 [&_li]:my-0.5 [&_p]:my-2">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{prSummary.summary}</ReactMarkdown>
                </div>
              </div>
            ) : (
              <div className="text-zinc-400 py-4">
                No summary yet. Run the daily coverage summary batch (scheduler or master backfill) to generate it.
              </div>
            )}
          </section>
        )}

        {/* Article counts — legible text */}
        {counts && (
          <section className="mt-8 rounded-xl border border-zinc-800 bg-zinc-900/40 p-5">
            <h2 className="text-lg font-semibold text-zinc-100 mb-3">
              Article counts
            </h2>
            <ul className="text-base text-zinc-300 space-y-2 mb-3">
              <li>
                <span className="font-medium text-zinc-200">Total articles in DB:</span>{" "}
                {counts.total_articles}
              </li>
              <li>
                <span className="font-medium text-zinc-200">Articles with {clientFilter} in entities:</span>{" "}
                {counts.articles_with_client_mentioned}
              </li>
              <li>
                <span className="font-medium text-zinc-200">Competitor-only (no {clientFilter}, only competitors):</span>{" "}
                {counts.competitor_only_articles}
              </li>
              <li>
                <span className="font-medium text-zinc-200">Articles with entities populated:</span>{" "}
                {counts.articles_with_entities_populated}
              </li>
            </ul>
            {counts.pipeline_note && (
              <p className="text-sm text-zinc-500 italic">{counts.pipeline_note}</p>
            )}
          </section>
        )}

        {/* Table 1: Competitor-only articles — Summary + Journalist columns, Media Intelligence style */}
        <section className="mt-8 rounded-xl border border-zinc-800 bg-zinc-900/40 p-5">
          <h2 className="text-lg font-semibold text-zinc-100 mb-2">
            Competitor-only articles (client not mentioned)
          </h2>
          <p className="text-base text-zinc-400 mb-4 max-w-2xl">
            Articles where entity detection found only competitors (e.g. Zerodha, Upstox) and no {clientFilter}.
          </p>
          {loading ? (
            <p className="text-zinc-400 py-4">Loading…</p>
          ) : competitorOnly ? (
            <>
              <div className="flex items-center gap-2 mb-4">
                <span className="text-base font-medium text-zinc-200">Present:</span>
                <span className="text-base font-semibold text-emerald-400">
                  {competitorOnly.has_competitor_only_articles ? "Yes" : "No"}
                </span>
                {competitorOnly.has_competitor_only_articles && (
                  <span className="text-base text-zinc-400">({competitorOnly.count} article(s))</span>
                )}
              </div>
              {competitorOnly.articles.length > 0 ? (
                <div className="overflow-x-auto rounded-lg border border-zinc-700">
                  <table className="min-w-full text-base">
                    <thead>
                      <tr>
                        <th className={TABLE_HEAD_CLASS}>Title</th>
                        <th className={TABLE_HEAD_CLASS}>Source</th>
                        <th className={TABLE_HEAD_CLASS}>Entities</th>
                        <th className={TABLE_HEAD_CLASS}>Summary</th>
                        <th className={TABLE_HEAD_CLASS}>Journalist</th>
                        <th className={TABLE_HEAD_CLASS}>Link</th>
                      </tr>
                    </thead>
                    <tbody>
                      {competitorOnly.articles.map((a, i) => (
                        <tr key={i} className="hover:bg-zinc-800/50 transition-colors">
                          <td className={`${TABLE_CELL_CLASS} max-w-[240px]`} title={a.title}>
                            <span className="line-clamp-2">{a.title || "—"}</span>
                          </td>
                          <td className={TABLE_CELL_MUTED}>{a.source_domain || "—"}</td>
                          <td className={TABLE_CELL_MUTED}>
                            {(a.entities || []).join(", ") || "—"}
                          </td>
                          <td className={`${TABLE_CELL_CLASS} max-w-[280px]`} title={a.ai_summary || a.summary || ""}>
                            <span className="line-clamp-2 text-zinc-300">
                              {a.ai_summary || a.summary || "—"}
                            </span>
                          </td>
                          <td className={TABLE_CELL_MUTED}>{a.author || "—"}</td>
                          <td className={TABLE_CELL_CLASS}>
                            {a.url ? (
                              <a
                                href={a.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-zinc-400 hover:text-zinc-200 underline"
                              >
                                Open
                              </a>
                            ) : (
                              "—"
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : null}
            </>
          ) : null}
        </section>

        {/* Table 2: Mentions of client and competitors */}
        <section className="mt-8 rounded-xl border border-zinc-800 bg-zinc-900/40 p-5">
          <h2 className="text-lg font-semibold text-zinc-100 mb-2">
            Mentions of client and competitors
          </h2>
          <p className="text-base text-zinc-400 mb-4 max-w-2xl">
            Articles where the client or any competitor is mentioned (from entity_mentions).
          </p>
          {loading ? (
            <p className="text-zinc-400 py-4">Loading…</p>
          ) : mentions && mentions.mentions.length > 0 ? (
            <>
              <div className="mb-4 text-base text-zinc-400">
                Showing up to 20 of {mentions.count} mention(s).
              </div>
              <div className="overflow-x-auto rounded-lg border border-zinc-700">
                <table className="min-w-full text-base">
                  <thead>
                    <tr>
                      <th className={TABLE_HEAD_CLASS}>Title</th>
                      <th className={TABLE_HEAD_CLASS}>Source</th>
                      <th className={TABLE_HEAD_CLASS}>Entity</th>
                      <th className={TABLE_HEAD_CLASS}>Summary</th>
                      <th className={TABLE_HEAD_CLASS}>Journalist</th>
                      <th className={TABLE_HEAD_CLASS}>Link</th>
                    </tr>
                  </thead>
                  <tbody>
                    {mentions.mentions.map((m, i) => (
                      <tr key={i} className="hover:bg-zinc-800/50 transition-colors">
                        <td className={`${TABLE_CELL_CLASS} max-w-[240px]`} title={m.title}>
                          <span className="line-clamp-2">{m.title || "—"}</span>
                        </td>
                        <td className={TABLE_CELL_MUTED}>{m.source_domain || "—"}</td>
                        <td className={TABLE_CELL_MUTED}>{m.entity || "—"}</td>
                        <td className={`${TABLE_CELL_CLASS} max-w-[280px]`} title={m.summary || ""}>
                          <span className="line-clamp-2 text-zinc-300">
                            {m.summary || "—"}
                          </span>
                        </td>
                        <td className={TABLE_CELL_MUTED}>{m.author || "—"}</td>
                        <td className={TABLE_CELL_CLASS}>
                          {m.url ? (
                            <a
                              href={m.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-zinc-400 hover:text-zinc-200 underline"
                            >
                              Open
                            </a>
                          ) : (
                            "—"
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <p className="text-zinc-400 py-4">No mentions found for this client.</p>
          )}
        </section>
      </div>
    </div>
  );
}
