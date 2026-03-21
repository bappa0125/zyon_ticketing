"use client";

import { useState, useEffect, useCallback } from "react";
import { getApiBase } from "@/lib/api";
import { ShareOfVoiceChart } from "@/components/MediaIntelligence/ShareOfVoiceChart";
import { PRSummaryCard } from "@/components/MediaIntelligence/PRSummaryCard";
import { CoverageByDomain, type DomainRow } from "@/components/MediaIntelligence/CoverageByDomain";

type TabId = "overview" | "outreach" | "benchmarks" | "alerts" | "press-releases" | "pr-intel";

interface Snapshot {
  client: string;
  date: string;
  outreach_targets: { outlet: string; domain: string; client_mentions: number; competitor_mentions: number; total: number }[];
  benchmarks: { entity: string; mentions: number; sentiment_avg: number; share_of_voice_pct: number }[];
  sentiment_alerts: { alert_type: string; severity: string; negative_pct: number; negative_count: number; total_mentions: number }[];
}

interface DashboardData {
  client: string;
  competitors: string[];
  range: string;
  coverage: { entity: string; mentions: number }[];
  by_domain?: DomainRow[];
  pr_summary?: string;
  meta?: {
    unified_mentions_count?: number;
    article_documents_in_window?: number;
    media_sources_count?: number;
    articles_indexed_scan_error?: string | null;
  };
}

function formatDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function last7Days(): { from: string; to: string } {
  const end = new Date();
  const start = new Date();
  start.setDate(start.getDate() - 6);
  return { from: formatDate(start), to: formatDate(end) };
}

export default function ReportsPage() {
  const [clients, setClients] = useState<string[]>([]);
  const [client, setClient] = useState("");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [tab, setTab] = useState<TabId>("overview");

  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [dashboardData, setDashboardData] = useState<DashboardData | null>(null);
  const [pressReleases, setPressReleases] = useState<{ id: string; url?: string; title?: string; published_at?: string }[]>([]);
  const [pickups, setPickups] = useState<{ article_url?: string; article_title?: string; published_at?: string }[]>([]);

  const [loadingSnapshots, setLoadingSnapshots] = useState(false);
  const [loadingDashboard, setLoadingDashboard] = useState(false);
  const [loadingPR, setLoadingPR] = useState(false);

  useEffect(() => {
    const { from, to } = last7Days();
    setFromDate(from);
    setToDate(to);
  }, []);

  useEffect(() => {
    async function fetchClients() {
      try {
        const res = await fetch(`${getApiBase()}/pr-reports/clients`);
        if (!res.ok) return;
        const json = await res.json();
        const list = json.clients ?? [];
        setClients(list);
        if (list.length > 0 && !client) setClient(list[0]);
      } catch {
        setClients([]);
      }
    }
    fetchClients();
  }, []);

  const rangeParam = useCallback(() => {
    if (!fromDate || !toDate) return "7d";
    const d1 = new Date(fromDate).getTime();
    const d2 = new Date(toDate).getTime();
    const days = Math.ceil((d2 - d1) / (24 * 60 * 60 * 1000)) + 1;
    if (days <= 1) return "24h";
    if (days <= 7) return "7d";
    return "30d";
  }, [fromDate, toDate]);

  const fetchSnapshots = useCallback(async () => {
    if (!client.trim() || !fromDate || !toDate) return;
    setLoadingSnapshots(true);
    try {
      const params = new URLSearchParams({ client, from_date: fromDate, to_date: toDate });
      const res = await fetch(`${getApiBase()}/pr-reports/snapshots?${params}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setSnapshots(data.snapshots ?? []);
    } catch (e) {
      console.error(e);
      setSnapshots([]);
    } finally {
      setLoadingSnapshots(false);
    }
  }, [client, fromDate, toDate]);

  const fetchDashboard = useCallback(async () => {
    if (!client.trim()) return;
    setLoadingDashboard(true);
    try {
      const params = new URLSearchParams({ client, range: rangeParam() });
      const res = await fetch(`${getApiBase()}/media-intelligence/dashboard?${params}`, {
        cache: "no-store",
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setDashboardData(json);
    } catch (e) {
      console.error(e);
      setDashboardData(null);
    } finally {
      setLoadingDashboard(false);
    }
  }, [client, rangeParam]);

  const fetchPressReleasesAndPickups = useCallback(async () => {
    if (!client.trim()) return;
    setLoadingPR(true);
    try {
      const [relRes, pickRes] = await Promise.all([
        fetch(`${getApiBase()}/pr-reports/press-releases?client=${encodeURIComponent(client)}`),
        fetch(`${getApiBase()}/pr-reports/press-release-pickups?client=${encodeURIComponent(client)}`),
      ]);
      if (relRes.ok) {
        const j = await relRes.json();
        setPressReleases(j.press_releases ?? []);
      }
      if (pickRes.ok) {
        const j = await pickRes.json();
        setPickups(j.pickups ?? []);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoadingPR(false);
    }
  }, [client]);

  useEffect(() => {
    if (client.trim()) {
      fetchSnapshots();
      fetchDashboard();
      fetchPressReleasesAndPickups();
    }
  }, [client, fromDate, toDate, fetchSnapshots, fetchDashboard, fetchPressReleasesAndPickups]);

  const handleExport = () => {
    if (!client.trim() || !fromDate || !toDate) return;
    const u = `${getApiBase()}/pr-reports/export/html?client=${encodeURIComponent(client)}&from_date=${fromDate}&to_date=${toDate}`;
    window.open(u, "_blank", "noopener");
  };

  const entities = dashboardData ? [dashboardData.client, ...(dashboardData.competitors || [])] : [];
  const totalMentions = dashboardData?.coverage?.reduce((s, c) => s + c.mentions, 0) ?? 0;

  const tabs: { id: TabId; label: string }[] = [
    { id: "overview", label: "Overview" },
    { id: "outreach", label: "Outreach targets" },
    { id: "benchmarks", label: "Benchmarks" },
    { id: "alerts", label: "Sentiment alerts" },
    { id: "press-releases", label: "Press releases" },
    { id: "pr-intel", label: "PR Intelligence" },
  ];

  return (
    <div className="app-page">
      <div className="max-w-6xl mx-auto p-6">
        <header className="mb-6">
          <h1 className="text-2xl font-semibold text-[var(--ai-text)]">PR Reports</h1>
          <p className="text-sm text-[var(--ai-muted)] mt-1">
            Unified reporting: coverage, outreach targets, benchmarks, sentiment alerts, press release pickups. Per-day history from batch jobs.
          </p>
        </header>

        <section className="flex flex-wrap items-center gap-4 mb-6 p-4 rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)]">
          <div className="flex items-center gap-2">
            <label className="text-sm text-[var(--ai-muted)]">Client</label>
            <select
              value={client}
              onChange={(e) => setClient(e.target.value)}
              className="px-3 py-2 rounded-lg bg-[var(--ai-bg-elevated)] border border-[var(--ai-border)] text-[var(--ai-text)] focus:outline-none focus:ring-2 focus:ring-[var(--ai-accent)] min-w-[160px]"
            >
              <option value="">Select client</option>
              {clients.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-2">
            <label className="text-sm text-[var(--ai-muted)]">From</label>
            <input
              type="date"
              value={fromDate}
              onChange={(e) => setFromDate(e.target.value)}
              className="px-3 py-2 rounded-lg bg-[var(--ai-bg-elevated)] border border-[var(--ai-border)] text-[var(--ai-text)]"
            />
          </div>
          <div className="flex items-center gap-2">
            <label className="text-sm text-[var(--ai-muted)]">To</label>
            <input
              type="date"
              value={toDate}
              onChange={(e) => setToDate(e.target.value)}
              className="px-3 py-2 rounded-lg bg-[var(--ai-bg-elevated)] border border-[var(--ai-border)] text-[var(--ai-text)]"
            />
          </div>
          <button
            type="button"
            onClick={handleExport}
            disabled={!client.trim() || !fromDate || !toDate}
            className="px-4 py-2 rounded-lg bg-[var(--ai-accent)] text-[var(--ai-bg)] font-medium text-sm hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Export HTML
          </button>
        </section>

        <div className="flex gap-2 mb-6 border-b border-[var(--ai-border)] overflow-x-auto">
          {tabs.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={`px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px whitespace-nowrap ${
                tab === t.id
                  ? "border-[var(--ai-accent)] text-[var(--ai-accent)]"
                  : "border-transparent text-[var(--ai-text-secondary)] hover:text-[var(--ai-text)]"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {!client.trim() && (
          <div className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-8 text-center text-[var(--ai-muted)]">
            Select a client to view PR reports.
          </div>
        )}

        {client.trim() && (
          <>
            {tab === "overview" && (
              <section className="space-y-6">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-4">
                    <p className="text-xs text-[var(--ai-muted)] uppercase tracking-wider">Total mentions</p>
                    <p className="text-2xl font-semibold text-[var(--ai-text)] mt-1">
                      {loadingDashboard ? "—" : totalMentions}
                    </p>
                  </div>
                  <div className="md:col-span-2">
                    <ShareOfVoiceChart
                      coverage={dashboardData?.coverage ?? []}
                      loading={loadingDashboard}
                      clientName={dashboardData?.client}
                    />
                  </div>
                </div>
                {client.toLowerCase() === "sahi" && (
                  <PRSummaryCard
                    client={client}
                    range={rangeParam()}
                    prSummary={dashboardData?.pr_summary ?? ""}
                    loading={loadingDashboard}
                  />
                )}
                <CoverageByDomain
                  byDomain={dashboardData?.by_domain ?? []}
                  entities={entities}
                  clientName={dashboardData?.client ?? ""}
                  competitors={dashboardData?.competitors ?? []}
                  loading={loadingDashboard}
                  onSelectDomain={() => {}}
                  selectedDomain={null}
                  pipelineMeta={dashboardData?.meta}
                />
              </section>
            )}

            {tab === "outreach" && (
              <section>
                <h2 className="text-lg font-medium text-[var(--ai-text)] mb-4">Outreach targets (per day)</h2>
                <p className="text-sm text-[var(--ai-muted)] mb-4">Outlets where client has 0 mentions and competitors have coverage.</p>
                {loadingSnapshots && <p className="text-[var(--ai-muted)]">Loading…</p>}
                {!loadingSnapshots && snapshots.length === 0 && (
                  <p className="text-[var(--ai-muted)]">No snapshots for this range. Run the batch job or wait for daily run.</p>
                )}
                {!loadingSnapshots && snapshots.length > 0 && (
                  <div className="space-y-6">
                    {snapshots.map((s) => (
                      <div key={s.date} className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] overflow-hidden">
                        <div className="px-4 py-2 bg-[var(--ai-bg-elevated)] text-sm font-medium text-[var(--ai-text)]">
                          {s.date}
                        </div>
                        <div className="overflow-x-auto">
                          <table className="w-full text-sm">
                            <thead>
                              <tr className="border-b border-[var(--ai-border)]">
                                <th className="text-left px-4 py-2 text-[var(--ai-muted)]">Outlet</th>
                                <th className="text-right px-4 py-2 text-[var(--ai-muted)]">Client</th>
                                <th className="text-right px-4 py-2 text-[var(--ai-muted)]">Competitors</th>
                              </tr>
                            </thead>
                            <tbody>
                              {(s.outreach_targets ?? []).slice(0, 10).map((o, i) => (
                                <tr key={i} className="border-b border-[var(--ai-border)] last:border-0">
                                  <td className="px-4 py-2 text-[var(--ai-text)]">{o.outlet || o.domain}</td>
                                  <td className="px-4 py-2 text-right text-[var(--ai-text-secondary)]">{o.client_mentions ?? 0}</td>
                                  <td className="px-4 py-2 text-right text-[var(--ai-text-secondary)]">{o.competitor_mentions ?? 0}</td>
                                </tr>
                              ))}
                              {(!s.outreach_targets || s.outreach_targets.length === 0) && (
                                <tr><td colSpan={3} className="px-4 py-4 text-[var(--ai-muted)] text-center">None</td></tr>
                              )}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </section>
            )}

            {tab === "benchmarks" && (
              <section>
                <h2 className="text-lg font-medium text-[var(--ai-text)] mb-4">Competitive benchmarks (per day)</h2>
                <p className="text-sm text-[var(--ai-muted)] mb-4">Mentions, sentiment avg, share of voice per entity.</p>
                {loadingSnapshots && <p className="text-[var(--ai-muted)]">Loading…</p>}
                {!loadingSnapshots && snapshots.length === 0 && (
                  <p className="text-[var(--ai-muted)]">No snapshots for this range.</p>
                )}
                {!loadingSnapshots && snapshots.length > 0 && (
                  <div className="space-y-6">
                    {snapshots.map((s) => (
                      <div key={s.date} className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] overflow-hidden">
                        <div className="px-4 py-2 bg-[var(--ai-bg-elevated)] text-sm font-medium text-[var(--ai-text)]">
                          {s.date}
                        </div>
                        <div className="overflow-x-auto">
                          <table className="w-full text-sm">
                            <thead>
                              <tr className="border-b border-[var(--ai-border)]">
                                <th className="text-left px-4 py-2 text-[var(--ai-muted)]">Entity</th>
                                <th className="text-right px-4 py-2 text-[var(--ai-muted)]">Mentions</th>
                                <th className="text-right px-4 py-2 text-[var(--ai-muted)]">Sentiment</th>
                                <th className="text-right px-4 py-2 text-[var(--ai-muted)]">Share %</th>
                              </tr>
                            </thead>
                            <tbody>
                              {(s.benchmarks ?? []).map((b, i) => (
                                <tr key={i} className="border-b border-[var(--ai-border)] last:border-0">
                                  <td className="px-4 py-2 text-[var(--ai-text)]">{b.entity}</td>
                                  <td className="px-4 py-2 text-right text-[var(--ai-text-secondary)]">{b.mentions}</td>
                                  <td className="px-4 py-2 text-right text-[var(--ai-text-secondary)]">{b.sentiment_avg?.toFixed(2) ?? "—"}</td>
                                  <td className="px-4 py-2 text-right text-[var(--ai-text-secondary)]">{b.share_of_voice_pct ?? "—"}%</td>
                                </tr>
                              ))}
                              {(!s.benchmarks || s.benchmarks.length === 0) && (
                                <tr><td colSpan={4} className="px-4 py-4 text-[var(--ai-muted)] text-center">No data</td></tr>
                              )}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </section>
            )}

            {tab === "alerts" && (
              <section>
                <h2 className="text-lg font-medium text-[var(--ai-text)] mb-4">Sentiment alerts (per day)</h2>
                <p className="text-sm text-[var(--ai-muted)] mb-4">Negative sentiment spikes. Data from batch job.</p>
                {loadingSnapshots && <p className="text-[var(--ai-muted)]">Loading…</p>}
                {!loadingSnapshots && snapshots.length === 0 && (
                  <p className="text-[var(--ai-muted)]">No snapshots for this range.</p>
                )}
                {!loadingSnapshots && snapshots.length > 0 && (
                  <div className="space-y-6">
                    {snapshots.map((s) => (
                      <div key={s.date} className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] overflow-hidden">
                        <div className="px-4 py-2 bg-[var(--ai-bg-elevated)] text-sm font-medium text-[var(--ai-text)]">
                          {s.date}
                        </div>
                        <div className="p-4">
                          {(s.sentiment_alerts ?? []).length === 0 && (
                            <p className="text-[var(--ai-muted)]">No alerts</p>
                          )}
                          {(s.sentiment_alerts ?? []).map((a, i) => (
                            <div
                              key={i}
                              className={`p-3 rounded-lg mb-2 last:mb-0 ${
                                (a.severity || "").toLowerCase() === "high"
                                  ? "bg-red-500/10 border border-red-500/30"
                                  : "bg-amber-500/10 border border-amber-500/30"
                              }`}
                            >
                              <span className="font-medium text-[var(--ai-text)]">{a.alert_type}</span> — Negative:{" "}
                              {a.negative_pct}% ({a.negative_count}/{a.total_mentions} mentions)
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </section>
            )}

            {tab === "press-releases" && (
              <section>
                <h2 className="text-lg font-medium text-[var(--ai-text)] mb-4">Press release pickups</h2>
                {loadingPR && <p className="text-[var(--ai-muted)]">Loading…</p>}
                {!loadingPR && (
                  <>
                    <div className="mb-6">
                      <h3 className="text-sm font-medium text-[var(--ai-text-secondary)] mb-2">Press releases</h3>
                      {(pressReleases ?? []).length === 0 && <p className="text-[var(--ai-muted)]">None added.</p>}
                      <ul className="list-disc list-inside text-sm text-[var(--ai-text-secondary)]">
                        {pressReleases.map((pr) => (
                          <li key={pr.id}>
                            <a href={pr.url} target="_blank" rel="noopener noreferrer" className="text-[var(--ai-accent)] hover:underline">
                              {pr.title || pr.url || "Untitled"}
                            </a>{" "}
                            ({pr.published_at})
                          </li>
                        ))}
                      </ul>
                    </div>
                    <div>
                      <h3 className="text-sm font-medium text-[var(--ai-text-secondary)] mb-2">Pickups</h3>
                      {pickups.length === 0 && <p className="text-[var(--ai-muted)]">No pickups found.</p>}
                      <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="border-b border-[var(--ai-border)]">
                              <th className="text-left px-4 py-2 text-[var(--ai-muted)]">Article</th>
                              <th className="text-left px-4 py-2 text-[var(--ai-muted)]">Published</th>
                            </tr>
                          </thead>
                          <tbody>
                            {pickups.map((p, i) => (
                              <tr key={i} className="border-b border-[var(--ai-border)] last:border-0">
                                <td className="px-4 py-2">
                                  <a href={p.article_url} target="_blank" rel="noopener noreferrer" className="text-[var(--ai-accent)] hover:underline">
                                    {(p.article_title || p.article_url || "—").slice(0, 80)}
                                  </a>
                                </td>
                                <td className="px-4 py-2 text-[var(--ai-text-secondary)]">{p.published_at ?? "—"}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </>
                )}
              </section>
            )}

            {tab === "pr-intel" && (
              <section>
                <p className="text-sm text-[var(--ai-muted)] mb-4">Topic–article mapping, first mentions, amplifiers, journalist–outlets.</p>
                <a
                  href={`/pr-intelligence?client=${encodeURIComponent(client)}`}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[var(--ai-accent-dim)] text-[var(--ai-accent)] font-medium hover:opacity-90"
                >
                  Open PR Intelligence
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                  </svg>
                </a>
              </section>
            )}
          </>
        )}
      </div>
    </div>
  );
}
