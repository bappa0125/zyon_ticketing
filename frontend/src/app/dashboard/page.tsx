"use client";

import { useEffect, useMemo, useState } from "react";
import { ShareOfVoiceChart, type CoverageRow } from "@/components/MediaIntelligence/ShareOfVoiceChart";
import { ShareOfVoiceDonut } from "@/components/MediaIntelligence/ShareOfVoiceDonut";
import { MentionsPerDayChart, type TimelineRow } from "@/components/MediaIntelligence/MentionsPerDayChart";
import { RankedSourcesTable, type RankedSourceRow } from "@/components/MediaIntelligence/RankedSourcesTable";
import { TopPublicationsList, type PubRow } from "@/components/MediaIntelligence/TopPublicationsList";
import { getApiBase } from "@/lib/api";

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

const RANGE_OPTIONS = [
  { value: "24h", label: "24h" },
  { value: "7d", label: "7d" },
  { value: "30d", label: "30d" },
] as const;

type RangeValue = (typeof RANGE_OPTIONS)[number]["value"];

interface PulseResponse {
  client: string;
  range: string;
  total_mentions?: number;
  entity_counts?: Record<string, number>;
  dashboard: {
    client: string;
    competitors: string[];
    range: string;
    coverage: CoverageRow[];
    timeline?: TimelineRow[];
    top_publications: PubRow[];
    by_domain?: RankedSourceRow[];
  };
  topics: unknown[];
}

interface PulseArticlesRow {
  id: string;
  entity: string;
  title: string;
  summary: string;
  link: string;
  source: string;
  source_domain: string;
  journalist: string | null;
  published_at: string;
  sentiment?: string | null;
}

interface PulseArticlesResponse {
  client: string;
  competitors: string[];
  entity: string;
  range: string;
  total_articles: number;
  page: number;
  page_size: number;
  rows: PulseArticlesRow[];
}

interface AIBriefResponse {
  cached: boolean;
  generated_at?: string;
  cache_key?: string;
  brief: {
    executive_summary?: string[];
    tone_guidance?: string;
    talk_points?: string[];
    avoid_points?: string[];
    target_outlets?: { domain: string; why: string }[];
    focus_articles?: { title: string; url: string; why: string }[];
    _raw?: string;
  };
}

export default function DashboardPage() {
  const [clients, setClients] = useState<{ name: string }[]>([]);
  const [client, setClient] = useState<string>("");
  const [range, setRange] = useState<RangeValue>("7d");
  const [loadingClients, setLoadingClients] = useState(true);
  const [loading, setLoading] = useState(false);
  const [pulse, setPulse] = useState<PulseResponse | null>(null);
  const [aiBusy, setAiBusy] = useState(false);
  const [aiError, setAiError] = useState<string>("");
  const [aiBrief, setAiBrief] = useState<AIBriefResponse | null>(null);
  const [articles, setArticles] = useState<PulseArticlesRow[]>([]);
  const [articlesTotal, setArticlesTotal] = useState(0);
  const [articlesPage, setArticlesPage] = useState(1);
  const [articlesLoading, setArticlesLoading] = useState(false);
  const [selectedEntity, setSelectedEntity] = useState<string>("");

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${getApiBase()}/clients`);
        if (!res.ok) throw new Error("clients failed");
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
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const downloadUrl = useMemo(() => {
    if (!client.trim()) return "";
    const params = new URLSearchParams({ client: client.trim(), range });
    return `${getApiBase()}/reports/pulse.html?${params.toString()}`;
  }, [client, range]);

  const pdfDownloadUrl = useMemo(() => {
    if (!client.trim()) return "";
    const params = new URLSearchParams({ client: client.trim(), range });
    return `${getApiBase()}/reports/pulse.pdf?${params.toString()}`;
  }, [client, range]);

  useEffect(() => {
    if (!client.trim()) {
      setAiBrief(null);
      setAiError("");
      return;
    }
    let cancelled = false;
    setAiError("");
    (async () => {
      try {
        const params = new URLSearchParams({ client: client.trim(), range });
        const res = await fetch(`${getApiBase()}/reports/ai-brief?${params.toString()}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (!cancelled && data.brief) {
          setAiBrief({
            cached: true,
            generated_at: data.generated_at,
            brief: data.brief,
          });
        } else if (!cancelled) {
          setAiBrief(null);
        }
      } catch (e) {
        if (!cancelled) setAiError(e instanceof Error ? e.message : "Failed to load");
        if (!cancelled) setAiBrief(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [client, range]);

  useEffect(() => {
    if (!client.trim()) {
      setPulse(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    (async () => {
      try {
        const params = new URLSearchParams({ client: client.trim(), range });
        const res = await fetch(`${getApiBase()}/reports/pulse?${params.toString()}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = (await res.json()) as PulseResponse;
        if (!cancelled) setPulse(data);
      } catch (e) {
        console.error(e);
        if (!cancelled) setPulse(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [client, range]);

  const dashboard = pulse?.dashboard;
  const coverage = dashboard?.coverage ?? [];
  const timeline = dashboard?.timeline ?? [];
  const byDomain = dashboard?.by_domain ?? [];
  const entities = useMemo(
    () =>
      dashboard?.client
        ? [dashboard.client, ...(dashboard.competitors ?? []).filter((c: string) => c !== dashboard.client)]
        : [],
    [dashboard]
  );
  const pubs = dashboard?.top_publications ?? [];
  const totalMentions =
    pulse?.total_mentions ?? coverage.reduce((s, c) => s + (c.mentions || 0), 0);

  // Sync selected entity when dashboard/entities change
  useEffect(() => {
    if (!dashboard?.client) return;
    // Keep current selection if still valid
    if (selectedEntity && entities.includes(selectedEntity)) {
      return;
    }
    // Default to client
    if (entities.length > 0) {
      setSelectedEntity(entities[0]);
      setArticlesPage(1);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dashboard, entities]);

  // Load articles for selected entity
  useEffect(() => {
    if (!client.trim() || !selectedEntity) {
      setArticles([]);
      setArticlesTotal(0);
      return;
    }
    let cancelled = false;
    setArticlesLoading(true);
    (async () => {
      try {
        const params = new URLSearchParams({
          client: client.trim(),
          range,
          entity: selectedEntity,
          page: String(articlesPage),
          page_size: "25",
        });
        const res = await fetch(`${getApiBase()}/reports/pulse/articles?${params.toString()}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = (await res.json()) as PulseArticlesResponse;
        if (!cancelled) {
          setArticles(data.rows || []);
          setArticlesTotal(data.total_articles || 0);
        }
      } catch (e) {
        console.error(e);
        if (!cancelled) {
          setArticles([]);
          setArticlesTotal(0);
        }
      } finally {
        if (!cancelled) setArticlesLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [client, range, selectedEntity, articlesPage]);

  return (
    <div className="app-page">
      <div className="w-full">
        <header className="flex flex-wrap items-center justify-between gap-4 py-4 border-b border-[var(--mw-border)] mb-6">
          <div>
            <h1 className="text-xl font-semibold text-[var(--mw-text)]">Executive PR Pulse</h1>
            <p className="text-sm text-[var(--mw-muted)] mt-1">
              Interactive view + downloadable HTML brief.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <select
              value={client}
              onChange={(e) => setClient(e.target.value)}
              disabled={loadingClients}
              className="app-select min-w-[160px]"
            >
              {loadingClients ? (
                <option value="">Loading…</option>
              ) : (
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
            <select
              value={range}
              onChange={(e) => setRange(e.target.value as RangeValue)}
              className="app-select"
            >
              {RANGE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
            <a
              href={downloadUrl || "#"}
              onClick={(e) => {
                if (!downloadUrl) e.preventDefault();
              }}
              className={downloadUrl ? "app-btn-secondary" : "app-btn-secondary opacity-50 pointer-events-none"}
            >
              Download HTML brief
            </a>
            <a
              href={pdfDownloadUrl || "#"}
              onClick={(e) => {
                if (!pdfDownloadUrl) e.preventDefault();
              }}
              className={pdfDownloadUrl ? "app-btn-primary" : "app-btn-primary opacity-50 pointer-events-none"}
            >
              Download PDF
            </a>
          </div>
        </header>

        {!client.trim() && (
          <div className="app-card-muted p-8 text-center text-[var(--mw-muted)]">
            Select a client to view the pulse.
          </div>
        )}

        {client.trim() && (
          <>
            <section className="mb-6 animate-ai-stagger">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                <div className="app-card p-4">
                  <p className="text-xs text-[var(--mw-muted)] uppercase tracking-wider">Total mentions</p>
                  <p className="text-2xl font-semibold text-[var(--mw-text)] mt-1">
                    {loading ? "—" : totalMentions}
                  </p>
                  <p className="text-xs text-[var(--mw-muted)] mt-1">in selected period</p>
                </div>
                <div className="md:col-span-2">
                  <ShareOfVoiceChart
                    coverage={coverage}
                    loading={loading}
                    clientName={dashboard?.client}
                  />
                </div>
              </div>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
                <MentionsPerDayChart
                  timeline={timeline}
                  entities={entities}
                  clientName={dashboard?.client}
                  loading={loading}
                />
                <ShareOfVoiceDonut
                  coverage={coverage}
                  loading={loading}
                  clientName={dashboard?.client}
                />
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                <RankedSourcesTable
                  rows={byDomain}
                  clientName={dashboard?.client ?? ""}
                  competitorNames={dashboard?.competitors ?? []}
                  loading={loading}
                />
                <TopPublicationsList items={pubs} loading={loading} />
              </div>
              <div className="mt-4 grid grid-cols-1">
                <div className="app-card p-4">
                  <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
                    <div>
                      <h3 className="text-sm font-semibold text-[var(--mw-text)]">Articles by entity</h3>
                      <p className="text-xs text-[var(--mw-muted)] mt-1">
                        Titles, sources and summaries for mentions in this period.
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <label className="text-xs text-[var(--mw-muted)]">Entity</label>
                      <select
                        value={selectedEntity}
                        onChange={(e) => {
                          setSelectedEntity(e.target.value);
                          setArticlesPage(1);
                        }}
                        className="app-select"
                      >
                        {entities.map((e) => (
                          <option key={e} value={e}>
                            {e === dashboard?.client ? `${e} (client)` : e}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>
                  {articlesLoading ? (
                    <div className="text-sm text-[var(--mw-muted)]">Loading articles…</div>
                  ) : !articles.length ? (
                    <div className="text-sm text-[var(--mw-muted)]">
                      No articles found for this entity in the selected period.
                    </div>
                  ) : (
                    <>
                      <div className="overflow-x-auto rounded-xl border border-[var(--mw-border)]">
                        <table className="min-w-full divide-y divide-[var(--mw-border)] text-sm">
                          <thead className="bg-[var(--mw-surface-2)]">
                            <tr>
                              <th className="px-3 py-2 text-left text-xs font-medium text-[var(--mw-muted)] uppercase tracking-wider">
                                Title
                              </th>
                              <th className="px-3 py-2 text-left text-xs font-medium text-[var(--mw-muted)] uppercase tracking-wider">
                                Source
                              </th>
                              <th className="px-3 py-2 text-left text-xs font-medium text-[var(--mw-muted)] uppercase tracking-wider">
                                Journalist
                              </th>
                              <th className="px-3 py-2 text-left text-xs font-medium text-[var(--mw-muted)] uppercase tracking-wider">
                                Summary
                              </th>
                              <th className="px-3 py-2 text-right text-xs font-medium text-[var(--mw-muted)] uppercase tracking-wider">
                                Date
                              </th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-[var(--mw-border)]">
                            {articles.map((row) => (
                              <tr key={row.id} className="hover:bg-[var(--mw-surface-2)]/70">
                                <td className="px-3 py-2 align-top">
                                  {row.link ? (
                                    <a
                                      href={row.link}
                                      target="_blank"
                                      rel="noreferrer"
                                      className="text-sm text-[var(--mw-primary)] hover:underline font-medium"
                                    >
                                      {row.title}
                                    </a>
                                  ) : (
                                    <span className="text-sm text-[var(--mw-text)]">{row.title}</span>
                                  )}
                                </td>
                                <td className="px-3 py-2 align-top text-sm text-[var(--mw-text-secondary)]">
                                  {row.source || row.source_domain || "—"}
                                </td>
                                <td className="px-3 py-2 align-top text-sm text-[var(--mw-text-secondary)]">
                                  {row.journalist || "cannot be verified"}
                                </td>
                                <td className="px-3 py-2 align-top text-sm text-[var(--mw-text-secondary)]">
                                  {row.summary || "—"}
                                </td>
                                <td className="px-3 py-2 align-top text-right text-xs text-[var(--mw-muted)] whitespace-nowrap">
                                  {formatDate(row.published_at)}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                      <div className="mt-2 flex items-center justify-between text-xs text-[var(--mw-muted)]">
                        <span>
                          Showing {(articlesPage - 1) * 25 + 1}-
                          {Math.min(articlesPage * 25, articlesTotal)} of {articlesTotal} articles
                        </span>
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            disabled={articlesPage <= 1}
                            onClick={() => setArticlesPage((p) => Math.max(1, p - 1))}
                            className={
                              articlesPage <= 1
                                ? "app-btn-secondary opacity-50 cursor-not-allowed"
                                : "app-btn-secondary"
                            }
                          >
                            Previous
                          </button>
                          <button
                            type="button"
                            disabled={articlesPage * 25 >= articlesTotal}
                            onClick={() => setArticlesPage((p) => p + 1)}
                            className={
                              articlesPage * 25 >= articlesTotal
                                ? "app-btn-secondary opacity-50 cursor-not-allowed"
                                : "app-btn-secondary"
                            }
                          >
                            Next
                          </button>
                        </div>
                      </div>
                    </>
                  )}
                </div>
              </div>
            </section>

            <section className="mb-6 app-card p-4">
              <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
                <div>
                  <h3 className="text-sm font-semibold text-[var(--mw-text)]">AI PR Brief (guarded)</h3>
                  <p className="text-xs text-[var(--mw-muted)] mt-1">
                    Loaded from DB (generated daily). Use Refresh to regenerate now.
                  </p>
                </div>
                <button
                  type="button"
                  disabled={aiBusy || !client.trim()}
                  onClick={async () => {
                    if (!client.trim()) return;
                    setAiBusy(true);
                    setAiError("");
                    try {
                      const res = await fetch(`${getApiBase()}/reports/ai-brief`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ client: client.trim(), range }),
                      });
                      if (!res.ok) {
                        const text = await res.text();
                        throw new Error(text || `HTTP ${res.status}`);
                      }
                      const json = (await res.json()) as AIBriefResponse;
                      setAiBrief(json);
                    } catch (e) {
                      console.error(e);
                      setAiError(e instanceof Error ? e.message : "AI brief failed");
                      setAiBrief(null);
                    } finally {
                      setAiBusy(false);
                    }
                  }}
                  className={aiBusy ? "app-btn-secondary opacity-50 cursor-not-allowed" : "app-btn-primary"}
                >
                  {aiBusy ? "Generating…" : "Refresh brief"}
                </button>
              </div>

              {aiError && (
                <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg p-3 mb-3">
                  {aiError}
                </div>
              )}

              {!aiBrief && !aiBusy && !aiError && (
                <div className="text-sm text-[var(--mw-muted)]">
                  No AI brief in DB yet. Run daily job or click Refresh to generate.
                </div>
              )}

              {aiBrief && (
                <div className="space-y-4">
                  <div className="flex flex-wrap items-center gap-2 text-xs text-[var(--mw-muted)]">
                    <span className="px-2 py-1 rounded-full border border-[var(--mw-border)] bg-[var(--mw-surface-2)]">
                      {aiBrief.cached ? "Cached" : "Fresh"}
                    </span>
                    {aiBrief.generated_at && <span>Generated: {aiBrief.generated_at}</span>}
                  </div>

                  {!!aiBrief.brief?.executive_summary?.length && (
                    <div>
                      <p className="text-xs text-[var(--mw-muted)] uppercase tracking-wider mb-2">Executive summary</p>
                      <ul className="list-disc pl-5 space-y-1 text-sm text-[var(--mw-text)]">
                        {aiBrief.brief.executive_summary.map((x, i) => (
                          <li key={i}>{x}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {aiBrief.brief?.tone_guidance && (
                    <div>
                      <p className="text-xs text-[var(--mw-muted)] uppercase tracking-wider mb-2">Tone</p>
                      <p className="text-sm text-[var(--mw-text-secondary)]">{aiBrief.brief.tone_guidance}</p>
                    </div>
                  )}

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <p className="text-xs text-[var(--mw-muted)] uppercase tracking-wider mb-2">Talk points</p>
                      <ul className="list-disc pl-5 space-y-1 text-sm text-[var(--mw-text)]">
                        {(aiBrief.brief.talk_points ?? []).map((x, i) => (
                          <li key={i}>{x}</li>
                        ))}
                      </ul>
                    </div>
                    <div>
                      <p className="text-xs text-[var(--mw-muted)] uppercase tracking-wider mb-2">Avoid</p>
                      <ul className="list-disc pl-5 space-y-1 text-sm text-[var(--mw-text)]">
                        {(aiBrief.brief.avoid_points ?? []).map((x, i) => (
                          <li key={i}>{x}</li>
                        ))}
                      </ul>
                    </div>
                  </div>

                  {!!(aiBrief.brief.target_outlets ?? []).length && (
                    <div>
                      <p className="text-xs text-[var(--mw-muted)] uppercase tracking-wider mb-2">Target outlets</p>
                      <div className="overflow-x-auto rounded-lg border border-[var(--mw-border)]">
                        <table className="min-w-full divide-y divide-[var(--mw-border)]">
                          <thead className="bg-[var(--mw-surface-2)]">
                            <tr>
                              <th className="px-3 py-2 text-left text-xs font-medium text-[var(--mw-muted)] uppercase tracking-wider">
                                Domain
                              </th>
                              <th className="px-3 py-2 text-left text-xs font-medium text-[var(--mw-muted)] uppercase tracking-wider">
                                Why
                              </th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-[var(--mw-border)]">
                            {(aiBrief.brief.target_outlets ?? []).map((r, i) => (
                              <tr key={i} className="hover:bg-slate-50">
                                <td className="px-3 py-2 text-sm text-[var(--mw-text)]">{r.domain}</td>
                                <td className="px-3 py-2 text-sm text-[var(--mw-text-secondary)]">{r.why}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                  {!!(aiBrief.brief.focus_articles ?? []).length && (
                    <div>
                      <p className="text-xs text-[var(--mw-muted)] uppercase tracking-wider mb-2">Focus articles</p>
                      <div className="space-y-2">
                        {(aiBrief.brief.focus_articles ?? []).map((a, i) => (
                          <div key={i} className="rounded-lg border border-[var(--mw-border)] bg-[var(--mw-surface-2)] p-3">
                            <a
                              href={a.url}
                              target="_blank"
                              rel="noreferrer"
                              className="text-sm text-[var(--mw-primary)] hover:underline font-medium"
                            >
                              {a.title}
                            </a>
                            <p className="text-sm text-[var(--mw-text-secondary)] mt-1">{a.why}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {aiBrief.brief?._raw && (
                    <details className="text-xs text-[var(--mw-muted)]">
                      <summary className="cursor-pointer">Raw model output (fallback)</summary>
                      <pre className="whitespace-pre-wrap mt-2">{aiBrief.brief._raw}</pre>
                    </details>
                  )}
                </div>
              )}
            </section>

            {!loading && !pulse && (
              <div className="app-card-muted p-6 text-[var(--mw-muted)]">
                No data found for this client/range yet.
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

