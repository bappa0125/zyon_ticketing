"use client";

import { useState, useEffect, useCallback } from "react";
import { getApiBase, withClientQuery } from "@/lib/api";
import { useActiveClient } from "@/context/ClientContext";

interface GroupMetric {
  group_id: string;
  name: string;
  prompts_run: number;
  company_visible_count: number;
  score_pct: number;
}

interface Snapshot {
  client: string;
  week: string;
  overall_index: number;
  group_metrics: GroupMetric[];
  engine_metrics?: { engine: string; prompts_run: number; company_visible_count: number; score_pct: number }[];
  computed_at?: string;
}

interface Recommendation {
  query: string;
  engine?: string;
  competitors_found?: string[];
  recommendation_text: string;
}

interface SamplePromptResult {
  query: string;
  group_name: string;
  answer_text: string;
  entities_found: string[];
  company_visible: boolean;
}

interface DashboardData {
  client: string;
  week: string;
  latest: Snapshot | null;
  trend: Snapshot[];
  recommendations: Recommendation[];
  samples?: SamplePromptResult[];
}

const panel =
  "rounded-2xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-4 shadow-sm";
const muted = "text-[var(--ai-muted)]";
const body = "text-[var(--ai-text-secondary)]";

// Sample card: max height for answer, expand on click
const SAMPLE_ANSWER_PREVIEW = 180;

export default function AiSearchVisibilityPage() {
  const { clientName: clientFilter, ready: clientReady } = useActiveClient();
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [weeks, setWeeks] = useState(8);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [expandedSampleIndex, setExpandedSampleIndex] = useState<number | null>(null);

  const fetchDashboard = useCallback(async () => {
    if (!clientReady || !clientFilter?.trim()) {
      setData(null);
      setLoading(false);
      return;
    }
    setError(null);
    setLoading(true);
    try {
      const res = await fetch(
        withClientQuery(
          `${getApiBase()}/social/ai-search-visibility/dashboard?client=${encodeURIComponent(clientFilter)}&weeks=${Math.min(weeks, 52)}`,
          clientFilter
        )
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setData(json);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [clientFilter, weeks, clientReady]);

  useEffect(() => {
    fetchDashboard();
  }, [fetchDashboard]);

  const runRefresh = async () => {
    setRefreshing(true);
    setError(null);
    setMessage(null);
    try {
      const res = await fetch(`${getApiBase()}/social/ai-search-visibility/refresh`, { method: "POST" });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail ?? `HTTP ${res.status}`);
      }
      const result = await res.json();
      if (result.ok) {
        const processed = result.processed ?? 0;
        setMessage(
          processed > 0
            ? `Pipeline ran: ${processed} new run(s). Refreshing…`
            : "Pipeline ran (no new runs; data may be cached for this week)."
        );
        await fetchDashboard();
        if (processed > 0) setTimeout(() => setMessage(null), 5000);
      } else {
        setError(result.reason ?? "Pipeline failed");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRefreshing(false);
    }
  };

  if (!clientReady || !clientFilter) {
    return (
      <div className="app-page">
        <div className="mx-auto w-full max-w-[var(--ai-max-content)] p-6">
          <p className={muted}>Loading client…</p>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="app-page">
        <div className="mx-auto w-full max-w-[var(--ai-max-content)]">
          <h1 className="app-heading mb-2">AI Search Visibility</h1>
          <p className="text-center py-16 text-[var(--ai-muted)]">Loading…</p>
        </div>
      </div>
    );
  }

  const latest = data?.latest;
  const trend = data?.trend ?? [];
  const recommendations = data?.recommendations ?? [];
  const samples = data?.samples ?? [];

  return (
    <div className="app-page">
      <div className="mx-auto w-full max-w-[var(--ai-max-content)]">
        <h1 className="app-heading mb-2">AI Search Visibility</h1>
        <p className={`app-subheading mb-6 ${muted}`}>
          How visible is your company in AI-generated answers (e.g. Perplexity). Weekly metrics and recommendations.
        </p>

        <div className="flex flex-wrap items-center gap-3 mb-6">
          <p className="text-sm font-medium text-[var(--ai-text-secondary)]">
            Client: <span className="text-[var(--ai-text)]">{clientFilter}</span>
          </p>
          <label className="text-sm font-medium text-[var(--ai-text-secondary)]">Trend weeks:</label>
          <select
            value={weeks}
            onChange={(e) => setWeeks(Number(e.target.value))}
            className="rounded-lg border border-[var(--ai-border)] bg-[var(--ai-surface)] px-3 py-2 text-sm text-[var(--ai-text)]"
          >
            <option value={4}>4</option>
            <option value={8}>8</option>
            <option value={12}>12</option>
          </select>
          <button
            type="button"
            onClick={fetchDashboard}
            disabled={loading}
            className="text-sm py-2 px-3 rounded-lg border border-[var(--ai-border)] bg-[var(--ai-surface)] hover:bg-[var(--ai-bg-elevated)] text-[var(--ai-text-secondary)] disabled:opacity-50"
          >
            Refresh
          </button>
          <button
            type="button"
            onClick={runRefresh}
            disabled={refreshing}
            className="app-btn-primary text-sm py-2 px-4 disabled:opacity-50"
          >
            {refreshing ? "Running pipeline…" : "Run pipeline now"}
          </button>
        </div>

        {error && (
          <div className="rounded-xl border border-[var(--ai-danger)]/50 bg-[var(--ai-danger)]/10 px-4 py-3 text-sm text-[var(--ai-danger)] mb-6">
            {error}
          </div>
        )}
        {message && (
          <div className="rounded-xl border border-[var(--ai-accent)]/50 bg-[var(--ai-accent-dim)] px-4 py-3 text-sm text-[var(--ai-accent)] mb-6">
            {message}
          </div>
        )}

        {!latest ? (
          <div className={`${panel} py-12 text-center ${muted}`}>
            <p className="mb-2">No visibility data for <strong className="text-[var(--ai-text)]">{clientFilter}</strong> yet.</p>
            <p className="mb-3 text-sm">
              Run the pipeline above (or wait for the weekly Sunday 02:00 UTC job). Ensure{" "}
              <code className="bg-[var(--ai-bg-elevated)] px-1 rounded">ai_search_visibility.enabled</code> and{" "}
              <code className="bg-[var(--ai-bg-elevated)] px-1 rounded">OPENROUTER_API_KEY</code> are set.
            </p>
            <code className="block text-left max-w-md mx-auto bg-[var(--ai-bg-elevated)] px-3 py-2 rounded-lg text-xs overflow-x-auto mt-2">
              POST /api/social/ai-search-visibility/refresh
            </code>
          </div>
        ) : (
          <div className="space-y-6">
            {/* Sample prompts & results — visually engaging with CSS animation */}
            {samples.length > 0 && (
              <section className={panel}>
                <style>{`
                  @keyframes sampleCardEnter {
                    from { opacity: 0; transform: translateY(20px) scale(0.98); }
                    to { opacity: 1; transform: translateY(0) scale(1); }
                  }
                  @keyframes promptPulse {
                    0%, 100% { border-color: var(--ai-border); }
                    50% { border-color: var(--ai-accent); }
                  }
                  .sample-card {
                    animation: sampleCardEnter 0.5s ease-out forwards;
                    transform-origin: top center;
                  }
                  .sample-card:hover {
                    border-color: var(--ai-accent);
                    box-shadow: 0 0 0 1px var(--ai-accent), 0 8px 24px -8px rgba(0,0,0,0.25);
                  }
                  .prompt-bar {
                    animation: promptPulse 2s ease-in-out 0.5s;
                  }
                `}</style>
                <h2 className="text-lg font-semibold text-[var(--ai-text)] mb-1">Sample prompts & results</h2>
                <p className="text-sm text-[var(--ai-muted)] mb-5">
                  Example queries we ran and how AI answered. Green = your brand appeared; amber = opportunity to improve.
                </p>
                <div className="grid gap-5 sm:grid-cols-1 lg:grid-cols-2">
                  {samples.map((s, i) => (
                    <div
                      key={`${s.query}-${i}`}
                      className="sample-card rounded-xl border border-[var(--ai-border)] bg-[var(--ai-bg-elevated)] overflow-hidden transition-all duration-300"
                      style={{ animationDelay: `${i * 80}ms` }}
                    >
                      <div className="prompt-bar border-b border-[var(--ai-border)] bg-[var(--ai-surface)] px-4 py-3">
                        <span className="text-xs font-medium uppercase tracking-wider text-[var(--ai-muted)]">
                          {s.group_name}
                        </span>
                        <p className="mt-1 text-sm font-medium text-[var(--ai-text)] leading-snug">
                          &ldquo;{s.query}&rdquo;
                        </p>
                        <div className="mt-2 flex items-center gap-2">
                          <span
                            className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${
                              s.company_visible
                                ? "bg-emerald-500/20 text-emerald-400"
                                : "bg-amber-500/20 text-amber-400"
                            }`}
                          >
                            <span
                              className={`h-1.5 w-1.5 rounded-full ${
                                s.company_visible ? "bg-emerald-400" : "bg-amber-400"
                              }`}
                            />
                            {s.company_visible ? "Visible in answer" : "Not in answer"}
                          </span>
                          {s.entities_found?.length > 0 && (
                            <span className="text-xs text-[var(--ai-muted)]">
                              Entities: {s.entities_found.slice(0, 3).join(", ")}
                              {s.entities_found.length > 3 ? "…" : ""}
                            </span>
                          )}
                        </div>
                      </div>
                      <div className="px-4 py-3">
                        <p className="text-xs font-medium text-[var(--ai-muted)] mb-2">AI answer</p>
                        <div
                          className={`text-sm ${body} whitespace-pre-wrap break-words transition-all duration-300 overflow-hidden`}
                          style={{
                            maxHeight: expandedSampleIndex === i ? "2000px" : SAMPLE_ANSWER_PREVIEW,
                          }}
                        >
                          {s.answer_text || "— No answer text stored —"}
                        </div>
                        {s.answer_text && s.answer_text.length > 100 && (
                          <button
                            type="button"
                            onClick={() => setExpandedSampleIndex(expandedSampleIndex === i ? null : i)}
                            className="mt-2 text-xs font-medium text-[var(--ai-accent)] hover:underline"
                          >
                            {expandedSampleIndex === i ? "Show less" : "Show more"}
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {/* Overall AI Visibility Index */}
            <section className={panel}>
              <h2 className="text-sm font-medium text-[var(--ai-muted)] mb-1">Overall AI Visibility Index</h2>
              <p className="text-4xl font-bold text-[var(--ai-text)]">{latest.overall_index}%</p>
              <p className="text-xs text-[var(--ai-muted)] mt-1">
                Week {latest.week} • {latest.group_metrics?.reduce((s, g) => s + g.prompts_run, 0) ?? 0} prompts run
              </p>
            </section>

            {/* By prompt group */}
            <section className={panel}>
              <h2 className="text-lg font-semibold text-[var(--ai-text)] mb-4">By prompt group</h2>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-[var(--ai-border)]">
                      <th className="text-left py-2 pr-4 text-[var(--ai-muted)] font-medium">Group</th>
                      <th className="text-right py-2 px-2 text-[var(--ai-muted)] font-medium">Prompts run</th>
                      <th className="text-right py-2 px-2 text-[var(--ai-muted)] font-medium">Company visible</th>
                      <th className="text-right py-2 pl-2 text-[var(--ai-muted)] font-medium">Score %</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(latest.group_metrics ?? []).map((g) => (
                      <tr key={g.group_id} className="border-b border-[var(--ai-border)]/60">
                        <td className="py-2 pr-4 text-[var(--ai-text)]">{g.name}</td>
                        <td className="text-right py-2 px-2 text-[var(--ai-text-secondary)]">{g.prompts_run}</td>
                        <td className="text-right py-2 px-2 text-[var(--ai-text-secondary)]">{g.company_visible_count}</td>
                        <td className="text-right py-2 pl-2 font-medium text-[var(--ai-accent)]">{g.score_pct}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            {/* Trend */}
            {trend.length > 0 && (
              <section className={panel}>
                <h2 className="text-lg font-semibold text-[var(--ai-text)] mb-4">Trend (last {trend.length} weeks)</h2>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-[var(--ai-border)]">
                        <th className="text-left py-2 pr-4 text-[var(--ai-muted)] font-medium">Week</th>
                        <th className="text-right py-2 pl-2 text-[var(--ai-muted)] font-medium">Visibility index %</th>
                      </tr>
                    </thead>
                    <tbody>
                      {trend.map((s) => (
                        <tr key={s.week} className="border-b border-[var(--ai-border)]/60">
                          <td className="py-2 pr-4 text-[var(--ai-text)]">{s.week}</td>
                          <td className="text-right py-2 pl-2 font-medium text-[var(--ai-accent)]">{s.overall_index}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            )}

            {/* Recommendations */}
            <section className={panel}>
              <h2 className="text-lg font-semibold text-[var(--ai-text)] mb-4">Recommendations</h2>
              {recommendations.length === 0 ? (
                <p className={muted}>No recommendations for this week. Visibility is present or no competitor-only answers yet.</p>
              ) : (
                <ul className="space-y-3">
                  {recommendations.map((r, i) => (
                    <li key={i} className="rounded-lg border border-[var(--ai-border)] bg-[var(--ai-bg-elevated)] p-3 text-sm">
                      <p className="font-medium text-[var(--ai-text)] mb-1">{r.query}</p>
                      <p className={body}>{r.recommendation_text}</p>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
        )}
      </div>
    </div>
  );
}
