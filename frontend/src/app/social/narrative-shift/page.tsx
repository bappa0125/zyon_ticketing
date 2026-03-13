"use client";

import { useState, useEffect, useCallback } from "react";
import { getApiBase } from "@/lib/api";

interface DailyReport {
  date: string;
  executive_summary: string;
  top_narratives: { rank: number; topic: string; rationale: string }[];
  pr_actions: { action: string; priority: string }[];
  influencers: string[];
  sentiment: string;
  generated_at?: string;
}

interface NarrativeRow {
  topic: string;
  growth_pct: number;
  dominant_platform: string;
  platform_distribution?: Record<string, number>;
  influencers: string[];
  pain_points: string;
  messaging: string;
  item_count?: number;
  total_engagement?: number;
}

interface NarrativeShiftData {
  generated_at: string | null;
  narratives: NarrativeRow[];
  platform_totals: Record<string, number>;
  items_total: number;
  window_hours?: number;
}

const panel =
  "rounded-2xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-4 shadow-sm";
const muted = "text-[var(--ai-muted)]";
const body = "text-[var(--ai-text-secondary)]";
const primaryText = "text-[var(--ai-text)]";

function buildReportHtml(reports: DailyReport[]): string {
  const rows = reports
    .map(
      (r) => `
    <tr>
      <td>${r.date}</td>
      <td>${r.executive_summary || "—"}</td>
      <td>${(r.top_narratives || []).map((n) => `${n.rank}. ${n.topic}`).join("; ") || "—"}</td>
      <td>${(r.pr_actions || []).map((a) => `${a.action} (${a.priority})`).join("; ") || "—"}</td>
      <td>${(r.influencers || []).join(", ") || "—"}</td>
      <td>${r.sentiment || "—"}</td>
    </tr>
  `
    )
    .join("");
  return `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Narrative Intelligence Report</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; }
    h1 { font-size: 1.5rem; margin-bottom: 0.5rem; }
    .meta { color: #666; font-size: 0.9rem; margin-bottom: 1.5rem; }
    table { width: 100%; border-collapse: collapse; }
    th, td { border: 1px solid #ddd; padding: 0.5rem 0.75rem; text-align: left; }
    th { background: #f5f5f5; font-size: 0.85rem; }
    td { font-size: 0.9rem; }
    tr:nth-child(even) { background: #fafafa; }
  </style>
</head>
<body>
  <h1>Narrative Intelligence Report</h1>
  <p class="meta">Generated ${new Date().toISOString()} · Last ${reports.length} days</p>
  <table>
    <thead>
      <tr>
        <th>Date</th>
        <th>Executive Summary</th>
        <th>Top Narratives</th>
        <th>PR Actions</th>
        <th>Influencers</th>
        <th>Sentiment</th>
      </tr>
    </thead>
    <tbody>${rows}</tbody>
  </table>
</body>
</html>`;
}

export default function NarrativeShiftPage() {
  const [data, setData] = useState<NarrativeShiftData | null>(null);
  const [dailyReports, setDailyReports] = useState<DailyReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [dailyLoading, setDailyLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setError(null);
    try {
      const res = await fetch(`${getApiBase()}/social/narrative-shift`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setData({
        generated_at: json.generated_at ?? null,
        narratives: Array.isArray(json.narratives) ? json.narratives : [],
        platform_totals: json.platform_totals ?? {},
        items_total: json.items_total ?? 0,
        window_hours: json.window_hours ?? 72,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const [dailyError, setDailyError] = useState<string | null>(null);

  const fetchDailyReports = useCallback(async () => {
    setDailyError(null);
    try {
      const res = await fetch(`${getApiBase()}/social/narrative-intelligence-daily?days=7`);
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`HTTP ${res.status}${text ? `: ${text.slice(0, 150)}` : ""}`);
      }
      const json = await res.json();
      setDailyReports(Array.isArray(json.reports) ? json.reports : []);
    } catch (err) {
      setDailyReports([]);
      setDailyError(err instanceof Error ? err.message : String(err));
    } finally {
      setDailyLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    fetchDailyReports();
  }, [fetchDailyReports]);

  const handleDownloadReport = () => {
    const html = buildReportHtml(dailyReports);
    const blob = new Blob([html], { type: "text/html;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `narrative-intelligence-report-${new Date().toISOString().slice(0, 10)}.html`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (loading) {
    return (
      <div className="app-page">
        <div className="mx-auto w-full max-w-[var(--ai-max-content)]">
          <h1 className="app-heading mb-2">Narrative Shift Intelligence</h1>
          <p className="text-center py-16 text-[var(--ai-muted)]">Loading…</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="app-page">
        <div className="mx-auto w-full max-w-[var(--ai-max-content)]">
          <h1 className="app-heading mb-2">Narrative Shift Intelligence</h1>
          <div className="rounded-xl border border-[var(--ai-danger)]/50 bg-[var(--ai-danger)]/10 px-4 py-3 text-sm text-[var(--ai-danger)]">
            Could not load: {error}. Run the backfill script to populate data.
          </div>
        </div>
      </div>
    );
  }

  const narratives = data?.narratives ?? [];
  const platformTotals = data?.platform_totals ?? {};
  const totalItems = Object.values(platformTotals).reduce((a, b) => a + b, 0) || 1;
  const maxEngagement = Math.max(...narratives.map((n) => n.total_engagement ?? 0), 1);

  return (
    <div className="app-page">
      <div className="mx-auto w-full max-w-[var(--ai-max-content)]">
        <h1 className="app-heading mb-2">Narrative Shift Intelligence</h1>
        <p className={`app-subheading mb-6 ${muted}`}>
          Emerging narratives from YouTube, Reddit, and news. Run backfill:{" "}
          <code className="text-xs bg-[var(--ai-surface)] px-1 rounded">python backend/scripts/run_narrative_intelligence_backfill.py</code>
        </p>
        {data?.generated_at && (
          <p className="text-sm text-[var(--ai-muted)] mb-4">
            Last run: {new Date(data.generated_at).toLocaleString()} • {data.items_total} items
          </p>
        )}

        {/* Daily Narrative Intelligence (last 7 days) */}
        <div className={`${panel} mb-6`}>
          <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
            <h2 className="text-lg font-semibold text-[var(--ai-text)]">Daily intelligence (last 7 days)</h2>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => { setDailyLoading(true); fetchDailyReports(); }}
                disabled={dailyLoading}
                className="text-sm py-2 px-3 rounded-lg border border-[var(--ai-border)] bg-[var(--ai-surface)] hover:bg-[var(--ai-bg-elevated)] text-[var(--ai-text-secondary)] disabled:opacity-50"
              >
                Refresh
              </button>
              <button
                type="button"
                onClick={handleDownloadReport}
                disabled={dailyReports.length === 0}
                className="app-btn-primary text-sm py-2 px-4"
              >
                Generate report
              </button>
            </div>
          </div>
          {dailyLoading ? (
            <div className="py-8 text-center text-[var(--ai-muted)]">Loading…</div>
          ) : dailyError ? (
            <div className="py-8 text-center">
              <p className="text-sm text-[var(--ai-danger)] mb-2">Failed to load: {dailyError}</p>
              <button type="button" onClick={() => { setDailyLoading(true); fetchDailyReports(); }} className="text-sm text-[var(--ai-accent)] hover:underline">
                Retry
              </button>
            </div>
          ) : dailyReports.length === 0 ? (
            <div className="py-8 text-center text-sm text-[var(--ai-muted)]">
              <p className="mb-2">No daily reports. Run one of:</p>
              <code className="block text-left max-w-md mx-auto bg-[var(--ai-bg-elevated)] px-3 py-2 rounded-lg text-xs overflow-x-auto">
                docker compose exec backend python scripts/run_narrative_intelligence_backfill.py
              </code>
              <p className="mt-2 text-xs">or</p>
              <code className="block text-left max-w-md mx-auto bg-[var(--ai-bg-elevated)] px-3 py-2 rounded-lg text-xs overflow-x-auto mt-1">
                docker compose exec backend python scripts/run_master_backfill.py
              </code>
              <p className="mt-2 text-xs">Note: run_narrative_shift_backfill.py alone does not populate this table.</p>
            </div>
          ) : (
            <div className="overflow-x-auto rounded-xl border border-[var(--ai-border)]">
              <table className="min-w-full divide-y divide-[var(--ai-border)]">
                <thead className="bg-[var(--ai-bg-elevated)]">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-[var(--ai-text-secondary)]">Date</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-[var(--ai-text-secondary)]">Summary</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-[var(--ai-text-secondary)]">Top narratives</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-[var(--ai-text-secondary)]">PR actions</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-[var(--ai-text-secondary)]">Influencers</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-[var(--ai-text-secondary)]">Sentiment</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--ai-border)] bg-[var(--ai-surface)]">
                  {dailyReports.map((r) => (
                    <tr key={r.date} className="hover:bg-[var(--ai-bg-elevated)]">
                      <td className="px-4 py-3 text-sm font-medium text-[var(--ai-text)]">{r.date}</td>
                      <td className="px-4 py-3 text-sm text-[var(--ai-text-secondary)] max-w-xs">
                        <span className="line-clamp-2">{r.executive_summary || "—"}</span>
                      </td>
                      <td className="px-4 py-3 text-sm text-[var(--ai-text-secondary)] max-w-[200px]">
                        {(r.top_narratives || []).map((n) => `${n.rank}. ${n.topic}`).join("; ") || "—"}
                      </td>
                      <td className="px-4 py-3 text-sm text-[var(--ai-accent)] max-w-[200px]">
                        {(r.pr_actions || []).map((a) => a.action).join("; ") || "—"}
                      </td>
                      <td className="px-4 py-3 text-sm text-[var(--ai-muted)] max-w-[160px]">
                        {(r.influencers || []).join(", ") || "—"}
                      </td>
                      <td className="px-4 py-3 text-sm text-[var(--ai-text-secondary)] capitalize">{r.sentiment || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {narratives.length === 0 && !loading && (
          <div className={`${panel} py-12 text-center ${muted}`}>
            No narrative data. Run the backfill script from the backend container.
          </div>
        )}

        {narratives.length > 0 && (
          <div className="space-y-6">
            {/* Narrative Growth (engagement as proxy) */}
            <div className={panel}>
              <h2 className="text-lg font-semibold text-[var(--ai-text)] mb-4">
                Narrative engagement
              </h2>
              <div className="space-y-2">
                {narratives.slice(0, 8).map((n, i) => {
                  const eng = n.total_engagement ?? 0;
                  const pct = maxEngagement > 0 ? (eng / maxEngagement) * 100 : 0;
                  return (
                    <div key={i} className="flex items-center gap-2">
                      <span className="text-sm w-48 shrink-0 truncate" title={n.topic}>
                        {n.topic}
                      </span>
                      <div className="flex-1 h-6 rounded bg-[var(--ai-bg-elevated)] overflow-hidden">
                        <div
                          className="h-full rounded bg-[var(--ai-accent)]/70"
                          style={{ width: `${Math.max(pct, 4)}%` }}
                        />
                      </div>
                      <span className="text-sm w-20 text-right text-[var(--ai-muted)]">
                        {eng.toLocaleString()}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Platform Distribution */}
            <div className={panel}>
              <h2 className="text-lg font-semibold text-[var(--ai-text)] mb-4">
                Platform distribution
              </h2>
              <div className="flex flex-wrap gap-4">
                {Object.entries(platformTotals).map(([platform, count]) => {
                  const pct = totalItems > 0 ? (count / totalItems) * 100 : 0;
                  return (
                    <div key={platform} className="flex items-center gap-2">
                      <span
                        className="w-3 h-3 rounded-full shrink-0"
                        style={{
                          backgroundColor:
                            platform === "youtube"
                              ? "var(--ai-accent)"
                              : platform === "reddit"
                                ? "#ff4500"
                                : "#4a9eff",
                        }}
                      />
                      <span className="text-sm capitalize">{platform}</span>
                      <span className="text-sm text-[var(--ai-muted)]">
                        {count} ({pct.toFixed(0)}%)
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Influencer Impact (aggregate top influencers) */}
            <div className={panel}>
              <h2 className="text-lg font-semibold text-[var(--ai-text)] mb-4">
                Top influencers
              </h2>
              <div className="flex flex-wrap gap-2">
                {Array.from(new Set(narratives.flatMap((n) => n.influencers || []))).slice(0, 12).map((inf, i) => (
                  <span
                    key={i}
                    className="text-sm px-2 py-1 rounded-lg bg-[var(--ai-bg-elevated)] text-[var(--ai-text-secondary)]"
                  >
                    {inf}
                  </span>
                ))}
              </div>
            </div>

            {/* Narrative Opportunity Table */}
            <div className={panel}>
              <h2 className="text-lg font-semibold text-[var(--ai-text)] mb-4">
                Narrative opportunity table
              </h2>
              <div className="overflow-x-auto rounded-xl border border-[var(--ai-border)]">
                <table className="min-w-full divide-y divide-[var(--ai-border)]">
                  <thead className="bg-[var(--ai-bg-elevated)]">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[var(--ai-text-secondary)]">
                        Topic
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[var(--ai-text-secondary)]">
                        Growth %
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[var(--ai-text-secondary)]">
                        Platform
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[var(--ai-text-secondary)]">
                        Influencers
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[var(--ai-text-secondary)]">
                        Pain points
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[var(--ai-text-secondary)]">
                        Sahi messaging
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--ai-border)] bg-[var(--ai-surface)]">
                    {narratives.map((n, i) => (
                      <tr key={i} className="hover:bg-[var(--ai-bg-elevated)]">
                        <td className="px-4 py-3 text-sm font-medium text-[var(--ai-text)] max-w-xs">
                          {n.topic}
                        </td>
                        <td className="px-4 py-3 text-sm text-[var(--ai-muted)]">
                          {n.growth_pct > 0 ? `${n.growth_pct.toFixed(1)}%` : "—"}
                        </td>
                        <td className="px-4 py-3 text-sm text-[var(--ai-text-secondary)] capitalize">
                          {n.dominant_platform}
                        </td>
                        <td className="px-4 py-3 text-sm text-[var(--ai-muted)] max-w-[160px]">
                          {(n.influencers || []).slice(0, 3).join(", ") || "—"}
                        </td>
                        <td className="px-4 py-3 text-sm text-[var(--ai-text-secondary)] max-w-[200px]">
                          <span className="line-clamp-2">{n.pain_points || "—"}</span>
                        </td>
                        <td className="px-4 py-3 text-sm text-[var(--ai-accent)] max-w-[200px]">
                          <span className="line-clamp-2">{n.messaging || "—"}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
