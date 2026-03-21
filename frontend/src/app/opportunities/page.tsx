"use client";

import { useState, useEffect, useCallback } from "react";
import { OpportunityTable, OpportunityRow } from "@/components/OpportunityTable";
import Link from "next/link";
import { getApiBase } from "@/lib/api";

type TabId = "topics" | "quote-alerts" | "outreach-drafts" | "competitor-responses";

interface QuoteAlert {
  article_url?: string;
  article_title?: string;
  detected_phrase?: string;
  suggested_action?: string;
  date?: string;
}

interface OutreachDraft {
  outlet?: string;
  domain?: string;
  competitor_mentions?: number;
  draft_line?: string;
  date?: string;
}

interface CompetitorResponse {
  article_url?: string;
  article_title?: string;
  competitor?: string;
  suggested_angle?: string;
  date?: string;
}

export default function OpportunitiesPage() {
  const [opportunities, setOpportunities] = useState<OpportunityRow[]>([]);
  const [quoteAlerts, setQuoteAlerts] = useState<QuoteAlert[]>([]);
  const [outreachDrafts, setOutreachDrafts] = useState<OutreachDraft[]>([]);
  const [competitorResponses, setCompetitorResponses] = useState<CompetitorResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingPrIntel, setLoadingPrIntel] = useState(true);
  const [runningBatch, setRunningBatch] = useState(false);
  const [lastComputedAt, setLastComputedAt] = useState<string | null>(null);
  const [clientFilter, setClientFilter] = useState<string>("Sahi");
  const [clients, setClients] = useState<string[]>([]);
  const [tab, setTab] = useState<TabId>("topics");

  const fetchOpportunities = useCallback(async () => {
    if (!clientFilter.trim()) {
      setOpportunities([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const res = await fetch(`${getApiBase()}/opportunities?client=${encodeURIComponent(clientFilter)}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setOpportunities(data.opportunities ?? []);
    } catch (err) {
      console.error("fetchOpportunities failed:", err);
      setOpportunities([]);
    } finally {
      setLoading(false);
    }
  }, [clientFilter]);

  const fetchPrIntel = useCallback(async () => {
    if (!clientFilter.trim()) {
      setQuoteAlerts([]);
      setOutreachDrafts([]);
      setCompetitorResponses([]);
      setLoadingPrIntel(false);
      return;
    }
    setLoadingPrIntel(true);
    try {
      const res = await fetch(`${getApiBase()}/opportunities/pr-intel?client=${encodeURIComponent(clientFilter)}&days=7`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setQuoteAlerts(data.quote_alerts ?? []);
      setOutreachDrafts(data.outreach_drafts ?? []);
      setCompetitorResponses(data.competitor_responses ?? []);
      setLastComputedAt(data.last_computed_at ?? null);
    } catch (err) {
      console.error("fetchPrIntel failed:", err);
      setQuoteAlerts([]);
      setOutreachDrafts([]);
      setCompetitorResponses([]);
    } finally {
      setLoadingPrIntel(false);
    }
  }, [clientFilter]);

  useEffect(() => {
    async function loadClients() {
      try {
        const res = await fetch(`${getApiBase()}/clients`);
        if (!res.ok) return;
        const j = await res.json();
        const list = j.clients?.map((c: { name?: string }) => c.name).filter(Boolean) ?? [];
        setClients(list);
        if (list.length > 0 && !clientFilter) setClientFilter(list[0]);
      } catch {
        setClients([]);
      }
    }
    loadClients();
  }, []);

  useEffect(() => {
    fetchOpportunities();
  }, [fetchOpportunities]);

  useEffect(() => {
    fetchPrIntel();
  }, [fetchPrIntel]);

  const runBatch = useCallback(async () => {
    if (!clientFilter.trim()) return;
    setRunningBatch(true);
    try {
      const res = await fetch(
        `${getApiBase()}/opportunities/run-batch?client=${encodeURIComponent(clientFilter)}`,
        { method: "POST" }
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await fetchPrIntel();
    } catch (err) {
      console.error("runBatch failed:", err);
    } finally {
      setRunningBatch(false);
    }
  }, [clientFilter, fetchPrIntel]);

  const formatLastRun = (iso: string | null) => {
    if (!iso) return null;
    try {
      const d = new Date(iso);
      return d.toLocaleString();
    } catch {
      return iso;
    }
  };

  const tabs: { id: TabId; label: string }[] = [
    { id: "topics", label: "Topic gaps" },
    { id: "quote-alerts", label: "Quote opportunities" },
    { id: "outreach-drafts", label: "Outreach drafts" },
    { id: "competitor-responses", label: "Competitor responses" },
  ];

  const cardClass = "rounded-xl border border-zinc-800 bg-zinc-900/30 overflow-hidden";
  const thClass = "px-4 py-3 text-left text-sm font-medium text-zinc-300";
  const tdClass = "px-4 py-3 text-sm text-zinc-200";
  const linkClass = "text-zinc-400 hover:text-amber-400 hover:underline truncate max-w-[280px] inline-block";

  return (
    <div className="app-page p-6">
      <div className="max-w-5xl mx-auto">
        <div className="flex items-center gap-4 mb-6 flex-wrap">
          <Link href="/" className="text-sm text-zinc-400 hover:text-zinc-200">← Chat</Link>
          <Link href="/clients" className="text-sm text-zinc-400 hover:text-zinc-200">Clients</Link>
          <Link href="/media-intelligence" className="text-sm text-zinc-400 hover:text-zinc-200">Media Intel</Link>
          <Link href="/reports/pr" className="text-sm text-zinc-400 hover:text-zinc-200">Reports</Link>
        </div>
        <h1 className="text-xl font-semibold mb-2 text-zinc-100">PR Opportunities</h1>
        <p className="text-sm text-zinc-500 mb-4">
          Topic gaps (competitors have coverage, client doesn&apos;t) and LLM-powered opportunities: quote alerts, outreach drafts, competitor response angles.
        </p>
        <div className="flex flex-wrap items-center gap-4 mb-6">
          <div className="flex items-center gap-2">
            <label className="text-sm text-zinc-400">Client</label>
            <select
              value={clientFilter}
              onChange={(e) => setClientFilter(e.target.value)}
              className="px-3 py-2 rounded-lg bg-zinc-800 border border-zinc-700 text-zinc-200 focus:outline-none focus:ring-2 focus:ring-zinc-600 min-w-[160px]"
            >
              <option value="">Select client</option>
              {clients.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>
          <button
            type="button"
            onClick={runBatch}
            disabled={!clientFilter.trim() || runningBatch}
            className="px-4 py-2 rounded-lg bg-amber-600 text-white font-medium text-sm hover:bg-amber-500 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {runningBatch ? "Generating…" : "Generate / Refresh"}
          </button>
          {lastComputedAt && (
            <span className="text-sm text-zinc-500 self-center">
              Last updated: {formatLastRun(lastComputedAt)}
            </span>
          )}
        </div>

        <div className="flex gap-2 mb-6 border-b border-zinc-800 overflow-x-auto">
          {tabs.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={`px-4 py-2.5 text-sm font-medium border-b-2 -mb-px whitespace-nowrap transition-colors ${
                tab === t.id
                  ? "border-amber-500 text-amber-400"
                  : "border-transparent text-zinc-400 hover:text-zinc-200"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {!clientFilter.trim() && (
          <div className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-8 text-center text-zinc-500">
            Select a client to view PR opportunities.
          </div>
        )}

        {clientFilter.trim() && (
          <>
            {tab === "topics" && (
              <section>
                <p className="text-sm text-zinc-500 mb-4">Topics where competitors have mentions but client has none.</p>
                <OpportunityTable opportunities={opportunities} loading={loading} />
              </section>
            )}

            {tab === "quote-alerts" && (
              <section>
                <p className="text-sm text-zinc-500 mb-4">
                  Articles that <strong className="text-zinc-400">mention your client</strong> in{" "}
                  <code className="text-zinc-400 text-xs">article_documents</code> and whose text contains
                  journalist &quot;seeking comment&quot; phrases (e.g. declined to comment, no comment, we reached out). An LLM then suggests a one-line action.
                </p>
                {loadingPrIntel && <div className="text-center py-8 text-zinc-500">Loading…</div>}
                {!loadingPrIntel && quoteAlerts.length === 0 && (
                  <div className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-6 text-zinc-400 text-sm space-y-4">
                    <p className="font-medium text-zinc-300">No quote opportunities right now — usually one of these:</p>
                    <ul className="list-disc pl-5 space-y-2 text-zinc-500">
                      <li>
                        <strong className="text-zinc-400">Batch not run for this client</strong> — Click{" "}
                        <strong className="text-amber-500/90">Generate / Refresh</strong> above (or wait for the scheduled job). Nothing is shown until the job writes rows to the database.
                      </li>
                      <li>
                        <strong className="text-zinc-400">No matching articles in the last 7 days</strong> — The scanner only looks at{" "}
                        <code className="text-xs text-zinc-400">article_documents</code> tagged with your client&apos;s configured{" "}
                        <strong className="text-zinc-400">entity names</strong> (from Clients config), with recent{" "}
                        <code className="text-xs text-zinc-400">published_at</code> or <code className="text-xs text-zinc-400">fetched_at</code>.
                      </li>
                      <li>
                        <strong className="text-zinc-400">Phrases are rare</strong> — Even with coverage, most RSS/press pieces never say things like &quot;declined to comment&quot; or &quot;could not be reached&quot;. Empty here is normal; it is not a bug.
                      </li>
                      <li>
                        <strong className="text-zinc-400">Missing body text</strong> — Phrases are searched in{" "}
                        <code className="text-xs text-zinc-400">article_text</code> (then summary/title). If ingestion only stored titles, matches are unlikely.
                      </li>
                    </ul>
                    <p className="text-xs text-zinc-600 pt-2 border-t border-zinc-800">
                      Dev: run{" "}
                      <code className="text-zinc-500">python scripts/diagnose_pr_opportunities.py --client YourClient</code> in the backend to see counts and quote-pattern candidates.
                    </p>
                  </div>
                )}
                {!loadingPrIntel && quoteAlerts.length > 0 && (
                  <div className={cardClass}>
                    <table className="min-w-full">
                      <thead className="bg-zinc-900/50">
                        <tr>
                          <th className={thClass}>Article</th>
                          <th className={thClass}>Detected phrase</th>
                          <th className={thClass}>Suggested action</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-zinc-800">
                        {quoteAlerts.map((a, i) => (
                          <tr key={i} className="hover:bg-zinc-800/30">
                            <td className={tdClass}>
                              <a href={a.article_url} target="_blank" rel="noopener noreferrer" className={linkClass} title={a.article_title}>
                                {a.article_title || a.article_url || "—"}
                              </a>
                            </td>
                            <td className={tdClass}><span className="text-amber-400/90">{a.detected_phrase || "—"}</span></td>
                            <td className={tdClass}>{a.suggested_action || "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            )}

            {tab === "outreach-drafts" && (
              <section>
                <p className="text-sm text-zinc-500 mb-4">Outlets where client has 0 coverage and competitors do. LLM-generated pitch lines.</p>
                {loadingPrIntel && <div className="text-center py-8 text-zinc-500">Loading…</div>}
                {!loadingPrIntel && outreachDrafts.length === 0 && (
                  <div className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-8 text-center text-zinc-500">
                    No outreach drafts. Run the batch job or ensure outreach targets exist.
                  </div>
                )}
                {!loadingPrIntel && outreachDrafts.length > 0 && (
                  <div className={cardClass}>
                    <table className="min-w-full">
                      <thead className="bg-zinc-900/50">
                        <tr>
                          <th className={thClass}>Outlet</th>
                          <th className={thClass}>Competitor mentions</th>
                          <th className={thClass}>Draft pitch line</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-zinc-800">
                        {outreachDrafts.map((d, i) => (
                          <tr key={i} className="hover:bg-zinc-800/30">
                            <td className={tdClass}>{d.outlet || d.domain || "—"}</td>
                            <td className={tdClass}>{d.competitor_mentions ?? "—"}</td>
                            <td className={tdClass}><span className="text-amber-400/90">{d.draft_line || "—"}</span></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            )}

            {tab === "competitor-responses" && (
              <section>
                <p className="text-sm text-zinc-500 mb-4">Competitor coverage; LLM suggests response angles for the client.</p>
                {loadingPrIntel && <div className="text-center py-8 text-zinc-500">Loading…</div>}
                {!loadingPrIntel && competitorResponses.length === 0 && (
                  <div className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-8 text-center text-zinc-500">
                    No competitor responses. Run the batch job.
                  </div>
                )}
                {!loadingPrIntel && competitorResponses.length > 0 && (
                  <div className={cardClass}>
                    <table className="min-w-full">
                      <thead className="bg-zinc-900/50">
                        <tr>
                          <th className={thClass}>Competitor / Article</th>
                          <th className={thClass}>Suggested angle</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-zinc-800">
                        {competitorResponses.map((r, i) => (
                          <tr key={i} className="hover:bg-zinc-800/30">
                            <td className={tdClass}>
                              <span className="text-zinc-400">{r.competitor}: </span>
                              <a href={r.article_url} target="_blank" rel="noopener noreferrer" className={linkClass} title={r.article_title}>
                                {r.article_title || r.article_url || "—"}
                              </a>
                            </td>
                            <td className={tdClass}><span className="text-amber-400/90">{r.suggested_angle || "—"}</span></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            )}
          </>
        )}
      </div>
    </div>
  );
}
