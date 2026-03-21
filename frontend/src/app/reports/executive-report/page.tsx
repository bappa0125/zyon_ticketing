"use client";

import Link from "next/link";
import { useState, useEffect, useCallback } from "react";
import { getApiBase } from "@/lib/api";

interface ReportMeta {
  period?: string;
  week?: string;
  data_coverage?: string;
  last_updated?: string;
}

interface ReportPayload {
  meta?: ReportMeta;
  executive_summary?: string;
  takeaways?: string[];
  section1_reputation?: Array<{
    brand: string;
    reputation_score: number;
    sentiment_pct: string;
    trend_vs_prev_7d: string;
    risk_note: string;
  }>;
  section2_media_intel?: Array<{
    brand: string;
    share_of_voice_pct: number;
    news_pct: number;
    social_pct: number;
    pr_agency_summary: string;
  }>;
  section3_coverage?: Array<{
    brand: string;
    articles_7d: number;
    sources_with_coverage: number;
    top_publications: string;
    gap_outlets: string;
  }>;
  section4_opportunities?: Array<{
    brand: string;
    quote_alerts: number;
    pub_gaps: number;
    top_opportunity: string;
  }>;
  section5_pr_intel_synopsis?: Array<{
    brand: string;
    synopsis_7d: string;
  }>;
  section6_narrative?: Array<{
    brand: string;
    narrative_shift_themes: string;
    pr_brief: string;
  }>;
  section7_ai_visibility?: Array<{
    brand: string;
    overall_index: number;
    broker_discovery: number;
    zerodha_alt: number;
    feature: number;
    problem: number;
    comparison: number;
  }>;
  section8_positioning_mix?: Array<{
    brand: string;
    forum_pct: number;
    news_pct: number;
    youtube_count: number;
    reddit_count: number;
    forum_count: number;
    total_mentions: number;
    top_topics_display: string;
    competitor_only_count: number;
    top_opportunity: string;
  }>;
  section9_narrative_analytics?: {
    executive_summary?: string;
    top_narratives?: Array<{ rank?: number; topic?: string; rationale?: string }>;
    pr_actions?: Array<{ action?: string; priority?: string }>;
    influencers?: string[];
    sentiment?: string;
    date?: string;
    days_loaded?: number;
  };
  section_forum_traction?: Array<{ brand: string; topic: string; mention_count: number; sample_titles: string }>;
  section_forum_pr_brief?: Array<{ brand: string; brief: string }>;
  section_campaign_brief?: Array<{ brand: string; brief: string }>;
  data_quality_note?: string;
  missing_data_hint?: string;
}

const POPULATE_TIMEOUT_MS = 900_000; // 15 min for Narrative Positioning + AI Brief + PR Opportunities

export default function ExecutiveReportPage() {
  const [report, setReport] = useState<ReportPayload | null>(null);
  const [generatedAt, setGeneratedAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [populating, setPopulating] = useState(false);
  const [populateMessage, setPopulateMessage] = useState<string | null>(null);

  const fetchReport = useCallback(async (refresh = false) => {
    if (refresh) setRefreshing(true);
    else setLoading(true);
    if (!refresh) setError(null);
    const REPORT_TIMEOUT_MS = 300_000; // 5 min — report build can take 1–3 min; avoid client abort before server responds
    const controller = new AbortController();
    const timeoutId = refresh ? window.setTimeout(() => controller.abort(), REPORT_TIMEOUT_MS) : undefined;
    try {
      const url = `${getApiBase()}/reports/executive-competitor?range=7d${refresh ? "&refresh=true" : ""}`;
      const res = await fetch(url, { signal: controller.signal });
      const text = await res.text();
      if (res.status === 502) {
        setError(
          "502 Bad Gateway: the request took too long and the gateway timed out. Report generation can take 1–3 minutes. If using Docker, run: docker compose up -d --force-recreate nginx. Otherwise set NEXT_PUBLIC_API_URL=http://localhost:8000/api and ensure the backend runs on port 8000 so the request bypasses the dev proxy."
        );
        setReport(null);
        setGeneratedAt(null);
        return;
      }
      let data: { report?: unknown; generated_at?: string; error?: string; message?: string; detail?: string } = {};
      try {
        if (text) data = JSON.parse(text) as typeof data;
      } catch (parseErr) {
        console.error("Executive report: invalid JSON response", parseErr);
        setError("Server returned an invalid response. Check browser console (F12) for details.");
        setReport(null);
        setGeneratedAt(null);
        return;
      }
      if (!res.ok) {
        const msg = data.detail || data.message || data.error || "Failed to load report";
        console.error("Executive report API error", res.status, msg);
        setError(msg);
        setReport(null);
        setGeneratedAt(null);
        return;
      }
      setReport((data.report ?? null) as ReportPayload | null);
      setGeneratedAt(data.generated_at ?? null);
      if (data.report == null) {
        const msg = data.error || data.message || "Report build failed or no report generated yet. Run backfill or try again.";
        setError(msg);
      } else {
        setError(null);
      }
    } catch (e) {
      const isAbort = e instanceof Error && e.name === "AbortError";
      const msg = isAbort
        ? "Request timed out after 5 minutes. Report generation can take 1–3 minutes. Please try again or check that the backend is not overloaded."
        : (e instanceof Error ? e.message : "Network error");
      console.error("Executive report fetch failed", e);
      setError(msg);
      setReport(null);
      setGeneratedAt(null);
    } finally {
      if (timeoutId) window.clearTimeout(timeoutId);
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  const populateData = useCallback(async () => {
    setPopulating(true);
    setPopulateMessage(null);
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), POPULATE_TIMEOUT_MS);
    try {
      const res = await fetch(`${getApiBase()}/reports/executive-competitor/populate`, {
        method: "POST",
        signal: controller.signal,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setPopulateMessage(data.detail || data.reason || "Populate failed.");
        return;
      }
      const names = (data.client_names || []).join(", ") || data.clients + " clients";
      setPopulateMessage(`Done. Narrative Positioning, AI Brief, and PR Opportunities ran for: ${names}. Click «Refresh report» to regenerate.`);
    } catch (e) {
      const isAbort = e instanceof Error && e.name === "AbortError";
      setPopulateMessage(isAbort ? "Request timed out. Populate can take 5–15 minutes. Try again or run backfill from the command line." : (e instanceof Error ? e.message : "Network error"));
    } finally {
      window.clearTimeout(timeoutId);
      setPopulating(false);
    }
  }, []);

  useEffect(() => {
    fetchReport();
  }, [fetchReport]);

  if (loading && !report) {
    return (
      <div className="app-page">
        <div className="max-w-5xl mx-auto p-6">
          <p className="text-[var(--ai-muted)]">Loading Executive Competitor Intelligence report…</p>
        </div>
      </div>
    );
  }

  if (refreshing) {
    return (
      <div className="app-page" aria-busy="true" aria-live="polite">
        <div className="max-w-5xl mx-auto p-6 min-h-[40vh] flex flex-col justify-center">
          <h1 className="text-2xl font-semibold text-[var(--ai-text)]">Executive Report</h1>
          <div className="mt-6 p-8 rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] text-center">
            <p className="text-[var(--ai-text)] font-medium">Generating report…</p>
            <p className="text-sm text-[var(--ai-muted)] mt-2">This can take 1–3 minutes. Do not close the page.</p>
          </div>
        </div>
      </div>
    );
  }

  if (error && !report) {
    return (
      <div className="app-page">
        <div className="max-w-5xl mx-auto p-6 min-h-[40vh]">
          <h1 className="text-2xl font-semibold text-[var(--ai-text)]">Executive Report</h1>
          <p className="mt-2 text-[var(--ai-text)] rounded-lg bg-[var(--ai-surface)] border border-[var(--ai-border)] p-4" role="alert">{error}</p>
          <button
            type="button"
            onClick={() => {
              setRefreshing(true);
              setError(null);
              window.setTimeout(() => fetchReport(true), 0);
            }}
            disabled={refreshing}
            className="mt-4 px-4 py-2 rounded-lg bg-[var(--ai-accent)] text-[var(--ai-bg)] font-medium text-sm hover:opacity-90 disabled:opacity-50"
          >
            {refreshing ? "Generating…" : "Generate report now"}
          </button>
        </div>
      </div>
    );
  }

  if (!report) {
    return (
      <div className="app-page">
        <div className="max-w-5xl mx-auto p-6 min-h-[40vh]">
          <h1 className="text-2xl font-semibold text-[var(--ai-text)]">Executive Report</h1>
          <p className="mt-2 text-[var(--ai-text-secondary)]">No report available. Click below to generate one (this may take 1–3 minutes).</p>
          <button
            type="button"
            onClick={() => {
              setRefreshing(true);
              setError(null);
              window.setTimeout(() => fetchReport(true), 0);
            }}
            disabled={refreshing}
            className="mt-4 px-4 py-2 rounded-lg bg-[var(--ai-accent)] text-[var(--ai-bg)] font-medium text-sm hover:opacity-90 disabled:opacity-50"
          >
            {refreshing ? "Generating…" : "Generate report now"}
          </button>
        </div>
      </div>
    );
  }

  const meta = report.meta || {};
  const section1 = report?.section1_reputation || [];
  const section2 = report?.section2_media_intel || [];
  const section3 = report?.section3_coverage || [];
  const section4 = report?.section4_opportunities || [];
  const section5 = report?.section5_pr_intel_synopsis || [];
  const section6 = report?.section6_narrative || [];
  const section7 = report?.section7_ai_visibility || [];
  const section8 = report?.section8_positioning_mix || [];
  const sectionForumTraction = report?.section_forum_traction || [];
  const sectionForumPrBrief = report?.section_forum_pr_brief || [];
  const sectionCampaignBrief = report?.section_campaign_brief || [];

  return (
    <div className="app-page">
      <div className="max-w-5xl mx-auto p-6">
        <header className="flex flex-wrap items-center justify-between gap-4 mb-6">
          <div>
            <h1 className="text-2xl font-semibold text-[var(--ai-text)]">Executive Competitor Intelligence</h1>
            <p className="text-sm text-[var(--ai-muted)] mt-1">
              Unified view: Reputation • Media Intel • Coverage • PR Opportunities • PR Intelligence • Narrative • AI Search Visibility • Positioning Mix (forum vs news, topics, gaps).{" "}
              <Link href="/reports/narrative-briefing" className="text-[var(--ai-accent)] hover:underline font-medium whitespace-nowrap">
                Open narrative briefing →
              </Link>
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={populateData}
              disabled={refreshing || populating}
              className="px-4 py-2 rounded-lg border border-[var(--ai-border)] bg-[var(--ai-surface)] text-[var(--ai-text-secondary)] font-medium text-sm hover:bg-[var(--ai-surface-hover)] disabled:opacity-50"
              title="Run Narrative Positioning, AI Brief, and PR Opportunities for all brands (uses LLM; 5–15 min)"
            >
              {populating ? "Populating… (5–15 min)" : "Populate data for all brands"}
            </button>
            <button
              type="button"
              onClick={() => {
                setRefreshing(true);
                window.setTimeout(() => fetchReport(true), 0);
              }}
              disabled={refreshing || populating}
              className="px-4 py-2 rounded-lg bg-[var(--ai-accent-dim)] text-[var(--ai-accent)] font-medium text-sm hover:bg-[var(--ai-accent)] hover:text-[var(--ai-bg)] disabled:opacity-50"
            >
              {refreshing ? "Generating…" : "Refresh report"}
            </button>
          </div>
        </header>

        {report.missing_data_hint && (
          <div className="mb-4 p-4 rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] text-sm text-[var(--ai-text-secondary)]" role="status">
            <p className="font-medium text-[var(--ai-text)] mb-1">Missing data for some brands?</p>
            <p className="mb-2">{report.missing_data_hint}</p>
            <button
              type="button"
              onClick={populateData}
              disabled={populating}
              className="text-sm px-3 py-1.5 rounded-lg bg-[var(--ai-accent-dim)] text-[var(--ai-accent)] hover:opacity-90 disabled:opacity-50"
            >
              {populating ? "Populating…" : "Populate data for all brands"}
            </button>
          </div>
        )}

        {populateMessage && (
          <div className="mb-4 p-4 rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] text-sm text-[var(--ai-text-secondary)]" role="alert">
            {populateMessage}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-4 p-4 rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] text-xs text-[var(--ai-muted)] mb-6">
          {meta.period && <span><strong className="text-[var(--ai-text-secondary)]">Period:</strong> {meta.period}</span>}
          {meta.week && <span><strong className="text-[var(--ai-text-secondary)]">Week:</strong> {meta.week}</span>}
          {meta.data_coverage && <span><strong className="text-[var(--ai-text-secondary)]">Data coverage:</strong> {meta.data_coverage}</span>}
          {(meta.last_updated || generatedAt) && (
            <span><strong className="text-[var(--ai-text-secondary)]">Last updated:</strong> {meta.last_updated || generatedAt || "—"}</span>
          )}
        </div>

        {report?.executive_summary && (
          <div className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-6 mb-6">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-[var(--ai-muted)] mb-3">Executive summary</h2>
            <p className="text-[var(--ai-text-secondary)] text-sm leading-relaxed mb-4">{report.executive_summary}</p>
            {report.takeaways && report.takeaways.length > 0 && (
              <ul className="list-none pl-0 space-y-2">
                {report.takeaways.map((t, i) => (
                  <li key={i} className="text-sm text-[var(--ai-text-secondary)] pl-4 border-l-2 border-[var(--ai-accent)]">
                    {t}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {/* 1. Reputation & Sentiment */}
        <section className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-5 mb-6">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-[var(--ai-text)] mb-1">1. Reputation & sentiment (Pulse)</h2>
          <p className="text-xs text-[var(--ai-muted)] mb-3">Source: Pulse — Reputation score, Sentiment distribution</p>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--ai-border)]">
                  <th className="text-left py-2 pr-4 text-[var(--ai-muted)] font-medium">Brand</th>
                  <th className="text-right py-2 px-2 text-[var(--ai-muted)] font-medium">Reputation score</th>
                  <th className="text-right py-2 px-2 text-[var(--ai-muted)] font-medium">Sentiment (pos / neu / neg)</th>
                  <th className="text-right py-2 px-2 text-[var(--ai-muted)] font-medium">Trend vs prev 7d</th>
                  <th className="text-left py-2 pl-2 text-[var(--ai-muted)] font-medium">Risk / note</th>
                </tr>
              </thead>
              <tbody>
                {section1.map((r, i) => (
                  <tr key={i} className="border-b border-[var(--ai-border)] last:border-0">
                    <td className="py-2.5 pr-4 font-medium text-[var(--ai-text)]">{r.brand}</td>
                    <td className="text-right py-2.5 px-2 tabular-nums">{r.reputation_score}</td>
                    <td className="text-right py-2.5 px-2 tabular-nums">{r.sentiment_pct}</td>
                    <td className="text-right py-2.5 px-2">{r.trend_vs_prev_7d}</td>
                    <td className="py-2.5 pl-2 text-[var(--ai-text-secondary)]">{r.risk_note}</td>
                  </tr>
                ))}
                {section1.length === 0 && (
                  <tr><td colSpan={5} className="py-4 text-center text-[var(--ai-muted)]">No data</td></tr>
                )}
              </tbody>
            </table>
          </div>
          {report?.data_quality_note && <p className="text-xs text-[var(--ai-muted)] mt-3">{report.data_quality_note}</p>}
        </section>

        {/* 2. Media Intel */}
        <section className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-5 mb-6">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-[var(--ai-text)] mb-1">2. PR agency summary & share of voice (Media Intelligence)</h2>
          <p className="text-xs text-[var(--ai-muted)] mb-3">Source: Media Intelligence — PR agency summary, Share of voice</p>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--ai-border)]">
                  <th className="text-left py-2 pr-4 text-[var(--ai-muted)] font-medium">Brand</th>
                  <th className="text-right py-2 px-2 text-[var(--ai-muted)] font-medium">Share of voice %</th>
                  <th className="text-right py-2 px-2 text-[var(--ai-muted)] font-medium">News</th>
                  <th className="text-right py-2 px-2 text-[var(--ai-muted)] font-medium">Social</th>
                  <th className="text-left py-2 pl-2 text-[var(--ai-muted)] font-medium">PR agency summary (1 line)</th>
                </tr>
              </thead>
              <tbody>
                {section2.map((r, i) => (
                  <tr key={i} className="border-b border-[var(--ai-border)] last:border-0">
                    <td className="py-2.5 pr-4 font-medium text-[var(--ai-text)]">{r.brand}</td>
                    <td className="text-right py-2.5 px-2 tabular-nums">{r.share_of_voice_pct}%</td>
                    <td className="text-right py-2.5 px-2 tabular-nums">{r.news_pct}%</td>
                    <td className="text-right py-2.5 px-2 tabular-nums">{r.social_pct}%</td>
                    <td className="py-2.5 pl-2 text-[var(--ai-text-secondary)] max-w-md truncate" title={r.pr_agency_summary}>{r.pr_agency_summary}</td>
                  </tr>
                ))}
                {section2.length === 0 && <tr><td colSpan={5} className="py-4 text-center text-[var(--ai-muted)]">No data</td></tr>}
              </tbody>
            </table>
          </div>
        </section>

        {/* 3. Coverage */}
        <section className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-5 mb-6">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-[var(--ai-text)] mb-1">3. Coverage intel for PR team (Coverage)</h2>
          <p className="text-xs text-[var(--ai-muted)] mb-3">Source: Coverage — Articles count, Publication targeting</p>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--ai-border)]">
                  <th className="text-left py-2 pr-4 text-[var(--ai-muted)] font-medium">Brand</th>
                  <th className="text-right py-2 px-2 text-[var(--ai-muted)] font-medium">Articles (7d)</th>
                  <th className="text-right py-2 px-2 text-[var(--ai-muted)] font-medium">Sources with coverage</th>
                  <th className="text-left py-2 pl-2 text-[var(--ai-muted)] font-medium">Top publications</th>
                  <th className="text-left py-2 pl-2 text-[var(--ai-muted)] font-medium">Gap (outlets to target)</th>
                </tr>
              </thead>
              <tbody>
                {section3.map((r, i) => (
                  <tr key={i} className="border-b border-[var(--ai-border)] last:border-0">
                    <td className="py-2.5 pr-4 font-medium text-[var(--ai-text)]">{r.brand}</td>
                    <td className="text-right py-2.5 px-2 tabular-nums">{r.articles_7d}</td>
                    <td className="text-right py-2.5 px-2 tabular-nums">{r.sources_with_coverage}</td>
                    <td className="py-2.5 pl-2 text-[var(--ai-text-secondary)]">{r.top_publications}</td>
                    <td className="py-2.5 pl-2 text-[var(--ai-text-secondary)]">{r.gap_outlets}</td>
                  </tr>
                ))}
                {section3.length === 0 && <tr><td colSpan={5} className="py-4 text-center text-[var(--ai-muted)]">No data</td></tr>}
              </tbody>
            </table>
          </div>
        </section>

        {/* 4. PR opportunities */}
        <section className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-5 mb-6">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-[var(--ai-text)] mb-1">4. PR opportunities (Action / Opportunity)</h2>
          <p className="text-xs text-[var(--ai-muted)] mb-3">Source: Opportunities — Quote alerts, Publication gaps, Outreach</p>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--ai-border)]">
                  <th className="text-left py-2 pr-4 text-[var(--ai-muted)] font-medium">Brand</th>
                  <th className="text-right py-2 px-2 text-[var(--ai-muted)] font-medium">Quote alerts</th>
                  <th className="text-right py-2 px-2 text-[var(--ai-muted)] font-medium">Pub. gaps</th>
                  <th className="text-left py-2 pl-2 text-[var(--ai-muted)] font-medium">Top opportunity</th>
                </tr>
              </thead>
              <tbody>
                {section4.map((r, i) => (
                  <tr key={i} className="border-b border-[var(--ai-border)] last:border-0">
                    <td className="py-2.5 pr-4 font-medium text-[var(--ai-text)]">{r.brand}</td>
                    <td className="text-right py-2.5 px-2 tabular-nums">{r.quote_alerts}</td>
                    <td className="text-right py-2.5 px-2 tabular-nums">{r.pub_gaps}</td>
                    <td className="py-2.5 pl-2 text-[var(--ai-text-secondary)] max-w-md" title={r.top_opportunity}>{r.top_opportunity}</td>
                  </tr>
                ))}
                {section4.length === 0 && <tr><td colSpan={4} className="py-4 text-center text-[var(--ai-muted)]">No data</td></tr>}
              </tbody>
            </table>
          </div>
        </section>

        {/* 5. PR Intelligence 7d synopsis */}
        <section className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-5 mb-6">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-[var(--ai-text)] mb-1">5. PR Intelligence — 7-day synopsis</h2>
          <p className="text-xs text-[var(--ai-muted)] mb-3">Source: PR Intelligence / AI brief — 7-day summary</p>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--ai-border)]">
                  <th className="text-left py-2 pr-4 text-[var(--ai-muted)] font-medium">Brand</th>
                  <th className="text-left py-2 pl-2 text-[var(--ai-muted)] font-medium">7-day synopsis</th>
                </tr>
              </thead>
              <tbody>
                {section5.map((r, i) => (
                  <tr key={i} className="border-b border-[var(--ai-border)] last:border-0">
                    <td className="py-2.5 pr-4 font-medium text-[var(--ai-text)] align-top">{r.brand}</td>
                    <td className="py-2.5 pl-2 text-[var(--ai-text-secondary)] align-top max-w-2xl">{r.synopsis_7d}</td>
                  </tr>
                ))}
                {section5.length === 0 && <tr><td colSpan={2} className="py-4 text-center text-[var(--ai-muted)]">No data</td></tr>}
              </tbody>
            </table>
          </div>
        </section>

        {/* 6. Narrative & PR brief */}
        <section className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-5 mb-6">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-[var(--ai-text)] mb-1">6. Narrative shift & PR brief (per company)</h2>
          <p className="text-xs text-[var(--ai-muted)] mb-3">Source: Narrative Shift, Narrative Positioning (PR brief)</p>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--ai-border)]">
                  <th className="text-left py-2 pr-4 text-[var(--ai-muted)] font-medium">Brand</th>
                  <th className="text-left py-2 pl-2 text-[var(--ai-muted)] font-medium">Narrative shift (top themes)</th>
                  <th className="text-left py-2 pl-2 text-[var(--ai-muted)] font-medium">PR brief (2–3 lines)</th>
                </tr>
              </thead>
              <tbody>
                {section6.map((r, i) => (
                  <tr key={i} className="border-b border-[var(--ai-border)] last:border-0">
                    <td className="py-2.5 pr-4 font-medium text-[var(--ai-text)] align-top">{r.brand}</td>
                    <td className="py-2.5 pl-2 text-[var(--ai-text-secondary)] align-top max-w-xs">{r.narrative_shift_themes}</td>
                    <td className="py-2.5 pl-2 text-[var(--ai-text-secondary)] align-top max-w-md border-l border-[var(--ai-border)]">{r.pr_brief}</td>
                  </tr>
                ))}
                {section6.length === 0 && <tr><td colSpan={3} className="py-4 text-center text-[var(--ai-muted)]">No data</td></tr>}
              </tbody>
            </table>
          </div>
        </section>

        {/* 7. AI Search Visibility */}
        <section className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-5 mb-6">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-[var(--ai-text)] mb-1">7. AI Search Visibility — comparison</h2>
          <p className="text-xs text-[var(--ai-muted)] mb-3">Source: AI Search Visibility page</p>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--ai-border)]">
                  <th className="text-left py-2 pr-4 text-[var(--ai-muted)] font-medium">Brand</th>
                  <th className="text-right py-2 px-1 text-[var(--ai-muted)] font-medium">Overall index</th>
                  <th className="text-right py-2 px-1 text-[var(--ai-muted)] font-medium">Broker discovery</th>
                  <th className="text-right py-2 px-1 text-[var(--ai-muted)] font-medium">Zerodha alt.</th>
                  <th className="text-right py-2 px-1 text-[var(--ai-muted)] font-medium">Feature</th>
                  <th className="text-right py-2 px-1 text-[var(--ai-muted)] font-medium">Problem</th>
                  <th className="text-right py-2 px-1 text-[var(--ai-muted)] font-medium">Comparison</th>
                </tr>
              </thead>
              <tbody>
                {section7.map((r, i) => (
                  <tr key={i} className="border-b border-[var(--ai-border)] last:border-0">
                    <td className="py-2.5 pr-4 font-medium text-[var(--ai-text)]">{r.brand}</td>
                    <td className="text-right py-2.5 px-1 tabular-nums">{r.overall_index}%</td>
                    <td className="text-right py-2.5 px-1 tabular-nums">{r.broker_discovery}%</td>
                    <td className="text-right py-2.5 px-1 tabular-nums">{r.zerodha_alt}%</td>
                    <td className="text-right py-2.5 px-1 tabular-nums">{r.feature}%</td>
                    <td className="text-right py-2.5 px-1 tabular-nums">{r.problem}%</td>
                    <td className="text-right py-2.5 px-1 tabular-nums">{r.comparison}%</td>
                  </tr>
                ))}
                {section7.length === 0 && <tr><td colSpan={7} className="py-4 text-center text-[var(--ai-muted)]">No data</td></tr>}
              </tbody>
            </table>
          </div>
        </section>

        {/* 8. Positioning mix — YouTube, Reddit, Forums, forum vs news, topics, gaps */}
        <section className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-5 mb-6">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-[var(--ai-text)] mb-1">8. Positioning mix (YouTube, Reddit, Forums & evidence)</h2>
          <p className="text-xs text-[var(--ai-muted)] mb-3">Source: Social posts (YouTube, Reddit), entity mentions (forums vs news), topics, competitor-only articles. Use to inform ad/PR/social next moves.</p>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--ai-border)]">
                  <th className="text-left py-2 pr-4 text-[var(--ai-muted)] font-medium">Brand</th>
                  <th className="text-right py-2 px-1 text-[var(--ai-muted)] font-medium">YouTube</th>
                  <th className="text-right py-2 px-1 text-[var(--ai-muted)] font-medium">Reddit</th>
                  <th className="text-right py-2 px-1 text-[var(--ai-muted)] font-medium">Forums</th>
                  <th className="text-right py-2 px-1 text-[var(--ai-muted)] font-medium">Forum %</th>
                  <th className="text-right py-2 px-1 text-[var(--ai-muted)] font-medium">News %</th>
                  <th className="text-right py-2 px-1 text-[var(--ai-muted)] font-medium">Mentions</th>
                  <th className="text-left py-2 pl-2 text-[var(--ai-muted)] font-medium">Top topics</th>
                  <th className="text-right py-2 px-1 text-[var(--ai-muted)] font-medium">Gaps</th>
                  <th className="text-left py-2 pl-2 text-[var(--ai-muted)] font-medium">Top opportunity</th>
                </tr>
              </thead>
              <tbody>
                {section8.map((r, i) => (
                  <tr key={i} className="border-b border-[var(--ai-border)] last:border-0">
                    <td className="py-2.5 pr-4 font-medium text-[var(--ai-text)]">{r.brand}</td>
                    <td className="text-right py-2.5 px-1 tabular-nums">{r.youtube_count ?? 0}</td>
                    <td className="text-right py-2.5 px-1 tabular-nums">{r.reddit_count ?? 0}</td>
                    <td className="text-right py-2.5 px-1 tabular-nums">{r.forum_count ?? 0}</td>
                    <td className="text-right py-2.5 px-1 tabular-nums">{r.forum_pct}%</td>
                    <td className="text-right py-2.5 px-1 tabular-nums">{r.news_pct}%</td>
                    <td className="text-right py-2.5 px-1 tabular-nums">{r.total_mentions}</td>
                    <td className="py-2.5 pl-2 text-[var(--ai-text-secondary)] max-w-xs truncate" title={r.top_topics_display}>{r.top_topics_display}</td>
                    <td className="text-right py-2.5 px-1 tabular-nums">{r.competitor_only_count}</td>
                    <td className="py-2.5 pl-2 text-[var(--ai-text-secondary)] max-w-xs truncate" title={r.top_opportunity}>{r.top_opportunity}</td>
                  </tr>
                ))}
                {section8.length === 0 && <tr><td colSpan={10} className="py-4 text-center text-[var(--ai-muted)]">No data</td></tr>}
              </tbody>
            </table>
          </div>
        </section>

        {/* 9. Narrative analytics (7d) — global synthesis from Reddit, YouTube, narrative shift */}
        {report?.section9_narrative_analytics && (report.section9_narrative_analytics.days_loaded ?? 0) > 0 && (
          <section className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-5 mb-6">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-[var(--ai-text)] mb-1">9. Narrative analytics (7d)</h2>
            <p className="text-xs text-[var(--ai-muted)] mb-3">Source: Narrative Intelligence Daily — synthesis from Reddit themes, YouTube summaries, narrative shift. One report per day; below is the latest.</p>
            <div className="space-y-4">
              {report.section9_narrative_analytics.executive_summary && (
                <div>
                  <h3 className="text-xs font-medium text-[var(--ai-muted)] uppercase tracking-wider mb-1">Executive summary</h3>
                  <p className="text-sm text-[var(--ai-text-secondary)] leading-relaxed">{report.section9_narrative_analytics.executive_summary}</p>
                </div>
              )}
              <div className="grid gap-4 sm:grid-cols-2">
                {(report.section9_narrative_analytics.top_narratives?.length ?? 0) > 0 && (
                  <div>
                    <h3 className="text-xs font-medium text-[var(--ai-muted)] uppercase tracking-wider mb-2">Top narratives</h3>
                    <ul className="list-none space-y-1.5">
                      {report.section9_narrative_analytics.top_narratives!.map((n, i) => (
                        <li key={i} className="text-sm">
                          <span className="font-medium text-[var(--ai-text)]">{n.rank ?? i + 1}. {n.topic || "—"}</span>
                          {n.rationale && <p className="text-xs text-[var(--ai-muted)] mt-0.5">{n.rationale}</p>}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {(report.section9_narrative_analytics.pr_actions?.length ?? 0) > 0 && (
                  <div>
                    <h3 className="text-xs font-medium text-[var(--ai-muted)] uppercase tracking-wider mb-2">PR actions</h3>
                    <ul className="list-none space-y-1.5">
                      {report.section9_narrative_analytics.pr_actions!.map((a, i) => (
                        <li key={i} className="text-sm flex items-start gap-2">
                          <span className={`shrink-0 text-xs px-1.5 py-0.5 rounded ${(a.priority || "").toLowerCase() === "high" ? "bg-[var(--ai-danger)]/20 text-[var(--ai-danger)]" : "bg-[var(--ai-accent-dim)] text-[var(--ai-accent)]"}`}>{a.priority || "medium"}</span>
                          <span className="text-[var(--ai-text-secondary)]">{a.action || "—"}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-4 text-xs text-[var(--ai-muted)]">
                {report.section9_narrative_analytics.sentiment && (
                  <span><strong className="text-[var(--ai-text-secondary)]">Sentiment:</strong> {report.section9_narrative_analytics.sentiment}</span>
                )}
                {report.section9_narrative_analytics.date && (
                  <span><strong className="text-[var(--ai-text-secondary)]">Latest date:</strong> {report.section9_narrative_analytics.date}</span>
                )}
                {(report.section9_narrative_analytics.influencers?.length ?? 0) > 0 && (
                  <span><strong className="text-[var(--ai-text-secondary)]">Influencers:</strong> {report.section9_narrative_analytics.influencers!.slice(0, 5).join(", ")}</span>
                )}
              </div>
            </div>
          </section>
        )}

        {/* 10. Forum topics traction (detailed table) */}
        {sectionForumTraction.length > 0 && (
          <section className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-5 mb-6">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-[var(--ai-text)] mb-1">10. Forum topics (traction)</h2>
            <p className="text-xs text-[var(--ai-muted)] mb-3">Topics with most forum mentions per brand. Use for PR/content angles.</p>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[var(--ai-border)]">
                    <th className="text-left py-2 pr-4 text-[var(--ai-muted)] font-medium">Brand</th>
                    <th className="text-left py-2 px-2 text-[var(--ai-muted)] font-medium">Topic</th>
                    <th className="text-right py-2 px-2 text-[var(--ai-muted)] font-medium">Mentions</th>
                    <th className="text-left py-2 pl-2 text-[var(--ai-muted)] font-medium">Sample titles</th>
                  </tr>
                </thead>
                <tbody>
                  {sectionForumTraction.map((r, i) => (
                    <tr key={i} className="border-b border-[var(--ai-border)] last:border-0">
                      <td className="py-2.5 pr-4 font-medium text-[var(--ai-text)]">{r.brand}</td>
                      <td className="py-2.5 px-2 text-[var(--ai-text-secondary)]">{r.topic}</td>
                      <td className="text-right py-2.5 px-2 tabular-nums">{r.mention_count}</td>
                      <td className="py-2.5 pl-2 text-[var(--ai-muted)] max-w-xs truncate" title={r.sample_titles}>{r.sample_titles}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {/* 11. Forum PR brief (actionable for PR team from forum perspective) */}
        {sectionForumPrBrief.length > 0 && (
          <section className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-5 mb-6">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-[var(--ai-text)] mb-1">11. Forum PR brief (actionable)</h2>
            <p className="text-xs text-[var(--ai-muted)] mb-3">LLM-generated bullets for the PR team from forum perspective. Grounded in forum topics and mentions.</p>
            <div className="space-y-4">
              {sectionForumPrBrief.map((r, i) => (
                <div key={i} className="rounded-lg border border-[var(--ai-border)] bg-[var(--ai-bg-elevated)] p-3">
                  <h3 className="text-xs font-medium text-[var(--ai-muted)] mb-2">{r.brand}</h3>
                  <div className="text-sm text-[var(--ai-text-secondary)] whitespace-pre-line">{r.brief || "—"}</div>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* 12. Campaign / content brief (for Pictory, Copy.ai, etc.) */}
        {sectionCampaignBrief.length > 0 && (
          <section className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-5 mb-6">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-[var(--ai-text)] mb-1">12. Campaign / content brief</h2>
            <p className="text-xs text-[var(--ai-muted)] mb-3">Actionable brief per brand (angles, headline, script prompt). Use with tools like Pictory, Copy.ai. Suggestions only.</p>
            <div className="space-y-4">
              {sectionCampaignBrief.map((r, i) => (
                <div key={i} className="rounded-lg border border-[var(--ai-border)] bg-[var(--ai-bg-elevated)] p-3">
                  <h3 className="text-xs font-medium text-[var(--ai-muted)] mb-2">{r.brand}</h3>
                  <div className="text-sm text-[var(--ai-text-secondary)] whitespace-pre-line">{r.brief || "—"}</div>
                </div>
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
