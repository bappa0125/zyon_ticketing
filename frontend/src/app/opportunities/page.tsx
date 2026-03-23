"use client";

import { useState, useEffect, useCallback } from "react";
import { OpportunityTable, OpportunityRow } from "@/components/OpportunityTable";
import Link from "next/link";
import { getApiBase, withClientQuery } from "@/lib/api";
import { useActiveClient } from "@/context/ClientContext";

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
  const { clientName: clientFilter, ready: clientReady } = useActiveClient();
  const [opportunities, setOpportunities] = useState<OpportunityRow[]>([]);
  const [quoteAlerts, setQuoteAlerts] = useState<QuoteAlert[]>([]);
  const [outreachDrafts, setOutreachDrafts] = useState<OutreachDraft[]>([]);
  const [competitorResponses, setCompetitorResponses] = useState<CompetitorResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingPrIntel, setLoadingPrIntel] = useState(true);
  const [runningBatch, setRunningBatch] = useState(false);
  const [lastComputedAt, setLastComputedAt] = useState<string | null>(null);
  const [tab, setTab] = useState<TabId>("topics");

  const fetchOpportunities = useCallback(async () => {
    if (!clientReady || !clientFilter?.trim()) {
      setOpportunities([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const res = await fetch(
        withClientQuery(`${getApiBase()}/opportunities?client=${encodeURIComponent(clientFilter)}`, clientFilter)
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setOpportunities(data.opportunities ?? []);
    } catch (err) {
      console.error("fetchOpportunities failed:", err);
      setOpportunities([]);
    } finally {
      setLoading(false);
    }
  }, [clientFilter, clientReady]);

  const fetchPrIntel = useCallback(async () => {
    if (!clientReady || !clientFilter?.trim()) {
      setQuoteAlerts([]);
      setOutreachDrafts([]);
      setCompetitorResponses([]);
      setLoadingPrIntel(false);
      return;
    }
    setLoadingPrIntel(true);
    try {
      const res = await fetch(
        withClientQuery(
          `${getApiBase()}/opportunities/pr-intel?client=${encodeURIComponent(clientFilter)}&days=7`,
          clientFilter
        )
      );
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
  }, [clientFilter, clientReady]);

  useEffect(() => {
    fetchOpportunities();
  }, [fetchOpportunities]);

  useEffect(() => {
    fetchPrIntel();
  }, [fetchPrIntel]);

  const runBatch = useCallback(async () => {
    if (!clientReady || !clientFilter?.trim()) return;
    setRunningBatch(true);
    try {
      const res = await fetch(
        withClientQuery(
          `${getApiBase()}/opportunities/run-batch?client=${encodeURIComponent(clientFilter)}`,
          clientFilter
        ),
        { method: "POST" }
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await fetchPrIntel();
    } catch (err) {
      console.error("runBatch failed:", err);
    } finally {
      setRunningBatch(false);
    }
  }, [clientFilter, fetchPrIntel, clientReady]);

  const formatLastRun = (iso: string | null) => {
    if (!iso) return null;
    try {
      const d = new Date(iso);
      return d.toLocaleString();
    } catch {
      return iso;
    }
  };

  if (!clientReady || !clientFilter) {
    return (
      <div className="app-page p-6">
        <p className="text-sm text-zinc-500">Loading client…</p>
      </div>
    );
  }

  const tabs: { id: TabId; label: string }[] = [
    { id: "topics", label: "Topic gaps" },
    { id: "quote-alerts", label: "Story comment alerts" },
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
          Topic gaps (competitors have coverage, client doesn&apos;t), plus story comment alerts (no-comment wording in ingested news), outreach drafts, and competitor response angles — each tab explains what it is in plain language.
        </p>
        <div className="flex flex-wrap items-center gap-4 mb-6">
          <p className="text-sm text-zinc-400">
            Client: <strong className="text-zinc-200">{clientFilter}</strong>
          </p>
          <button
            type="button"
            onClick={runBatch}
            disabled={!clientFilter?.trim() || runningBatch}
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

        {!clientFilter?.trim() && (
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
              <section className="space-y-6">
                {/* Plain-language explainer for MD + day-to-day use */}
                <div className="rounded-xl border-2 border-amber-600/40 bg-amber-950/20 p-5 sm:p-6 space-y-4">
                  <h2 className="text-base font-semibold text-zinc-100 leading-snug">
                    Story comment alerts — what you&apos;re looking at
                  </h2>
                  <div className="space-y-3 text-sm text-zinc-300 leading-relaxed">
                    <p>
                      <strong className="text-zinc-100">In one line:</strong> We scan <strong className="text-zinc-100">recent news we already ingested</strong> and flag stories where the <strong className="text-zinc-100">wording suggests someone did not give the journalist a quote</strong> (for example &quot;declined to comment&quot; or &quot;did not respond&quot;). We only include stories that <strong className="text-zinc-100">also mention the client you selected</strong> at the top of this page.
                    </p>
                    <p>
                      <strong className="text-zinc-100">Example:</strong> An article says{" "}
                      <em className="text-zinc-200 not-italic border-l-2 border-amber-500/60 pl-3 block my-2 py-1 bg-zinc-900/40 rounded-r">
                        &quot;The bank <span className="text-amber-400/95">declined to comment</span> on the probe.&quot;
                      </em>{" "}
                      If that same piece mentions your client somewhere, it may appear here. Your team still <strong className="text-zinc-100">reads the full story</strong> to see <strong className="text-zinc-100">who</strong> declined and whether <strong className="text-zinc-100">pitching your client&apos;s perspective</strong> is appropriate and approved.
                    </p>
                    <div className="rounded-lg bg-zinc-900/60 border border-zinc-700 p-4 space-y-2">
                      <p className="text-xs font-semibold uppercase tracking-wide text-amber-500/90">What to do next (call to action)</p>
                      <ol className="list-decimal pl-5 space-y-2 text-zinc-300">
                        <li>
                          Click <strong className="text-amber-400">Generate / Refresh</strong> (top of page) so this list is built from the latest saved news — otherwise you may see nothing.
                        </li>
                        <li>
                          For each row: <strong className="text-zinc-100">open the article</strong> → confirm the situation → find <strong className="text-zinc-100">the right reporter or desk</strong> → follow your <strong className="text-zinc-100">internal / compliance process</strong> before contacting anyone.
                        </li>
                        <li>
                          Treat the &quot;Suggested action&quot; column as a <strong className="text-zinc-100">starter idea</strong>, not approved messaging.
                        </li>
                      </ol>
                    </div>
                    <div className="rounded-lg border border-zinc-700/80 bg-zinc-950/40 p-4 space-y-2">
                      <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">What this tab is not</p>
                      <ul className="list-disc pl-5 space-y-1.5 text-zinc-400 text-sm">
                        <li>It is <strong className="text-zinc-300">not</strong> HARO, Twitter &quot;journalists seeking sources,&quot; or a live newswire of every quote request.</li>
                        <li>An empty list is <strong className="text-zinc-300">often normal</strong> — most articles never use those exact phrases.</li>
                        <li>It does <strong className="text-zinc-300">not</strong> replace judgment: the &quot;no comment&quot; may refer to another company, not your client.</li>
                      </ul>
                    </div>
                    <p className="text-xs text-zinc-500 pt-1">
                      <strong className="text-zinc-400">For leadership:</strong> This is a <strong className="text-zinc-300">narrow, automated research hint</strong> layered on owned media data — valuable when it fires, but not the same as a full opportunity pipeline.
                    </p>
                  </div>
                </div>

                <details className="rounded-lg border border-zinc-800 bg-zinc-900/20 px-4 py-3 text-sm text-zinc-500">
                  <summary className="cursor-pointer text-zinc-400 hover:text-zinc-300 font-medium">
                    Technical details (optional — for ops / engineering)
                  </summary>
                  <ul className="list-disc pl-5 mt-3 space-y-1.5 text-xs text-zinc-500">
                    <li>Source: <code className="text-zinc-400">article_documents</code> with client entities (Clients config), last ~7 days, text from body / summary / title.</li>
                    <li>Diagnostics: <code className="text-zinc-400">python scripts/diagnose_pr_opportunities.py --client YourClient</code> in the backend.</li>
                  </ul>
                </details>

                {loadingPrIntel && <div className="text-center py-8 text-zinc-500">Loading…</div>}
                {!loadingPrIntel && quoteAlerts.length === 0 && (
                  <div className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-6 text-zinc-400 text-sm space-y-3">
                    <p className="font-medium text-zinc-300">No rows in the table right now</p>
                    <p className="text-zinc-500">
                      That is expected if you haven&apos;t clicked <strong className="text-amber-500/90">Generate / Refresh</strong> yet, or if none of your recent ingested articles both <strong className="text-zinc-400">mention this client</strong> and <strong className="text-zinc-400">contain phrases</strong> like the example in the amber box above. Scroll up — the yellow box explains what this feature does and does not promise.
                    </p>
                  </div>
                )}
                {!loadingPrIntel && quoteAlerts.length > 0 && (
                  <>
                    <p className="text-sm text-zinc-500">
                      Below: starter list only. Each row needs <strong className="text-zinc-400">human review</strong> before outreach (see steps in the amber box above).
                    </p>
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
                  </>
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
