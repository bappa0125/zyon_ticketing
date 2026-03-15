"use client";

import { useState, useEffect, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { getApiBase } from "@/lib/api";

interface ContentSuggestion {
  place: string;
  title: string;
  theme: string;
}

interface NarrativeItem {
  theme: string;
  sentiment?: string;
  platforms?: string[];
  evidence_count?: number;
  sample_quotes?: string[];
}

interface Positioning {
  headline?: string;
  pitch_angle?: string;
  suggested_outlets?: string[];
}

interface Threat {
  narrative: string;
  severity?: string;
  response_angle?: string;
}

interface Opportunity {
  angle: string;
  outlet_match?: string;
}

interface EvidenceRef {
  platform?: string;
  url?: string;
  title?: string;
  snippet?: string;
}

interface PositioningReport {
  client: string;
  date: string;
  computed_at?: string;
  narratives: NarrativeItem[];
  positioning: Positioning;
  threats: Threat[];
  opportunities: Opportunity[];
  evidence_refs: EvidenceRef[];
  brief_summary?: string;
  content_suggestions?: ContentSuggestion[];
}

const panel =
  "rounded-2xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-4 shadow-sm";
const muted = "text-[var(--ai-muted)]";
const body = "text-[var(--ai-text-secondary)]";
const primaryText = "text-[var(--ai-text)]";

export default function NarrativeIntelligencePage() {
  const [reports, setReports] = useState<PositioningReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [runningBatch, setRunningBatch] = useState(false);
  const [clientFilter, setClientFilter] = useState<string>("Sahi");
  const [clients, setClients] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [evidenceOpen, setEvidenceOpen] = useState(false);

  const fetchReports = useCallback(async () => {
    if (!clientFilter.trim()) {
      setReports([]);
      setLoading(false);
      return;
    }
    setError(null);
    setLoading(true);
    try {
      const res = await fetch(
        `${getApiBase()}/social/narrative-positioning?client=${encodeURIComponent(clientFilter)}&days=7`
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setReports(data.reports ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setReports([]);
    } finally {
      setLoading(false);
    }
  }, [clientFilter]);

  useEffect(() => {
    async function loadClients() {
      try {
        const res = await fetch(`${getApiBase()}/clients`);
        if (!res.ok) return;
        const j = await res.json();
        const list =
          j.clients?.map((c: { name?: string }) => c.name).filter(Boolean) ?? [];
        setClients(list);
        if (list.length && !clientFilter) setClientFilter(list[0]);
      } catch {
        setClients(["Sahi"]);
      }
    }
    loadClients();
  }, []);

  useEffect(() => {
    fetchReports();
  }, [fetchReports]);

  const [batchMessage, setBatchMessage] = useState<string | null>(null);

  const runBatch = async () => {
    setRunningBatch(true);
    setError(null);
    setBatchMessage(null);
    try {
      const res = await fetch(`${getApiBase()}/social/narrative-positioning/run-batch`, {
        method: "POST",
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (data.ok) {
        const processed = data.processed ?? 0;
        setBatchMessage(processed > 0 ? `${processed} client(s) processed. Refreshing…` : "Batch ran but no clients were processed. Check backend config (clients).");
        await fetchReports();
        if (processed > 0) setTimeout(() => setBatchMessage(null), 4000);
      } else {
        setError(data.reason ?? "Batch failed");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRunningBatch(false);
    }
  };

  const latest = reports[0];

  if (loading) {
    return (
      <div className="app-page">
        <div className="mx-auto w-full max-w-[var(--ai-max-content)]">
          <h1 className="app-heading mb-2">Narrative Positioning</h1>
          <p className="text-center py-16 text-[var(--ai-muted)]">Loading…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="app-page">
      <div className="mx-auto w-full max-w-[var(--ai-max-content)]">
        <h1 className="app-heading mb-2">Narrative Positioning</h1>
        <p className={`app-subheading mb-6 ${muted}`}>
          PR-focused intelligence: narratives, positioning, threats, opportunities.
        </p>

        <div className="flex flex-wrap items-center gap-3 mb-6">
          <label className="text-sm font-medium text-[var(--ai-text-secondary)]">
            Client:
          </label>
          <select
            value={clientFilter}
            onChange={(e) => setClientFilter(e.target.value)}
            className="rounded-lg border border-[var(--ai-border)] bg-[var(--ai-surface)] px-3 py-2 text-sm text-[var(--ai-text)]"
          >
            {clients.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={fetchReports}
            disabled={loading}
            className="text-sm py-2 px-3 rounded-lg border border-[var(--ai-border)] bg-[var(--ai-surface)] hover:bg-[var(--ai-bg-elevated)] text-[var(--ai-text-secondary)] disabled:opacity-50"
          >
            Refresh
          </button>
          <button
            type="button"
            onClick={runBatch}
            disabled={runningBatch}
            className="app-btn-primary text-sm py-2 px-4 disabled:opacity-50"
          >
            {runningBatch ? "Running…" : "Run batch"}
          </button>
        </div>

        {error && (
          <div className="rounded-xl border border-[var(--ai-danger)]/50 bg-[var(--ai-danger)]/10 px-4 py-3 text-sm text-[var(--ai-danger)] mb-6">
            {error}
          </div>
        )}

        {batchMessage && (
          <div className="rounded-xl border border-[var(--ai-accent)]/50 bg-[var(--ai-accent-dim)] px-4 py-3 text-sm text-[var(--ai-accent)] mb-6">
            {batchMessage}
          </div>
        )}

        {reports.length === 0 ? (
          <div className={`${panel} py-12 text-center ${muted}`}>
            <p className="mb-2">No narrative positioning data for <strong className="text-[var(--ai-text)]">{clientFilter || "this client"}</strong>.</p>
            <p className="mb-3 text-sm">Run the batch above (same client must exist in backend config), then click Refresh. Or run from backend:</p>
            <code className="block text-left max-w-md mx-auto bg-[var(--ai-bg-elevated)] px-3 py-2 rounded-lg text-xs overflow-x-auto">
              docker compose exec backend python scripts/run_narrative_positioning_backfill.py
            </code>
          </div>
        ) : (
          <div className="space-y-6">
            {latest && (
              <>
                {/* PR Brief hero + 3 content suggestions — always visible when there is a report */}
                <section className="relative overflow-hidden rounded-2xl border border-[var(--ai-border)] bg-gradient-to-br from-[var(--ai-surface)] via-[var(--ai-surface)] to-[var(--ai-bg-elevated)] p-6 shadow-lg">
                  <style>{`
                    @keyframes briefFadeIn {
                      from { opacity: 0; transform: translateY(12px); }
                      to { opacity: 1; transform: translateY(0); }
                    }
                    @keyframes cardSlideIn {
                      from { opacity: 0; transform: translateY(16px) scale(0.98); }
                      to { opacity: 1; transform: translateY(0) scale(1); }
                    }
                    .animate-brief-in { animation: briefFadeIn 0.6s ease-out forwards; }
                    .animate-card-in { animation: cardSlideIn 0.5s ease-out forwards; }
                  `}</style>
                  <div className="absolute top-0 right-0 w-64 h-64 bg-[var(--ai-accent)]/5 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2" aria-hidden />
                  <h2 className="relative text-xl font-bold text-[var(--ai-text)] mb-4 flex items-center gap-2 opacity-0 animate-brief-in">
                    <span className="inline-flex w-2 h-6 rounded-full bg-[var(--ai-accent)]" />
                    PR Brief
                  </h2>
                  {latest.brief_summary ? (
                    <div
                      className="relative prose prose-invert prose-sm max-w-none mb-6 text-[var(--ai-text-secondary)] [&_p]:my-2 [&_strong]:text-[var(--ai-text)]"
                      style={{ animation: "briefFadeIn 0.6s ease-out 0.1s forwards", opacity: 0 }}
                    >
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{latest.brief_summary}</ReactMarkdown>
                    </div>
                  ) : (
                    <p
                      className="relative text-sm text-[var(--ai-muted)] mb-6"
                      style={{ animation: "briefFadeIn 0.6s ease-out 0.1s forwards", opacity: 0 }}
                    >
                      Run the batch to generate the PR brief (trending, client vs competitors, actions).
                    </p>
                  )}
                  <p
                    className="relative text-sm font-medium text-[var(--ai-muted)] mb-3"
                    style={{ animation: "briefFadeIn 0.6s ease-out 0.2s forwards", opacity: 0 }}
                  >
                    Content to post — title & theme by place
                  </p>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    {((latest.content_suggestions && latest.content_suggestions.length >= 3)
                      ? latest.content_suggestions
                      : [
                          { place: "Articles", title: "", theme: "" },
                          { place: "YouTube", title: "", theme: "" },
                          { place: "Reddit", title: "", theme: "" },
                        ]
                    ).map((s, i) => (
                      <div
                        key={i}
                        className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)]/80 backdrop-blur p-4 hover:border-[var(--ai-accent)]/40 hover:shadow-md transition-all duration-300"
                        style={{ animation: `cardSlideIn 0.5s ease-out ${0.35 + i * 0.12}s forwards`, opacity: 0 }}
                      >
                        <div className="flex items-center gap-2 mb-3">
                          {s.place?.toLowerCase() === "articles" && (
                            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-amber-500/15 text-amber-500">
                              <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10a2 2 0 012 2v1m2 13a2 2 0 01-2-2V7m2 13a2 2 0 002-2V9a2 2 0 00-2-2h-2m-4-3H9M7 16h6M7 8h6" /></svg>
                            </span>
                          )}
                          {s.place?.toLowerCase() === "youtube" && (
                            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-red-500/15 text-red-500">
                              <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 24 24"><path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/></svg>
                            </span>
                          )}
                          {s.place?.toLowerCase() === "reddit" && (
                            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-orange-500/15 text-orange-500">
                              <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 24 24"><path d="M12 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0zm5.01 4.744c.688 0 1.25.561 1.25 1.249a1.25 1.25 0 0 1-2.498.056l-2.597-.547-.8 3.747c1.824.07 3.48.632 4.674 1.488.308-.309.73-.491 1.207-.491.968 0 1.754.786 1.754 1.754 0 .716-.435 1.333-1.01 1.614a3.111 3.111 0 0 1 .042.52c0 2.694-3.13 4.87-7.004 4.87-3.874 0-7.004-2.176-7.004-4.87 0-.183.015-.366.043-.534A1.748 1.748 0 0 1 4.028 12c0-.968.786-1.754 1.754-1.754.463 0 .898.196 1.207.49 1.207-.883 2.878-1.43 4.744-1.487l.885-4.182a.342.342 0 0 1 .14-.197.35.35 0 0 1 .238-.042l2.906.617a1.214 1.214 0 0 1 1.108-.701zM9.25 12C8.561 12 8 12.562 8 13.25c0 .687.561 1.248 1.25 1.248.687 0 1.248-.561 1.248-1.249 0-.688-.561-1.249-1.249-1.249zm5.5 0c-.687 0-1.248.561-1.248 1.25 0 .687.561 1.248 1.249 1.248.688 0 1.249-.561 1.249-1.249 0-.687-.562-1.249-1.25-1.249zm-5.466 3.99a.327.327 0 0 0-.231.094.33.33 0 0 0 0 .463c.842.842 2.484.913 2.961.913.477 0 2.105-.056 2.961-.913a.361.361 0 0 0 .029-.463.33.33 0 0 0-.464 0c-.547.533-1.684.73-2.512.73-.828 0-1.979-.196-2.512-.73a.328.328 0 0 0-.232-.095z"/></svg>
                            </span>
                          )}
                          <span className="font-semibold text-[var(--ai-text)]">{s.place}</span>
                        </div>
                        <p className="text-sm font-medium text-[var(--ai-text)] line-clamp-2 mb-1">{s.title || "—"}</p>
                        <p className="text-xs text-[var(--ai-muted)] line-clamp-2">{s.theme || "—"}</p>
                      </div>
                    ))}
                  </div>
                </section>

                {/* Positioning block */}
                <div className={panel}>
                  <h2 className="text-lg font-semibold text-[var(--ai-text)] mb-3">
                    Positioning
                  </h2>
                  <p className={`text-base font-medium ${primaryText} mb-2`}>
                    {latest.positioning?.headline || "—"}
                  </p>
                  <p className={`text-sm ${body} mb-3`}>
                    {latest.positioning?.pitch_angle || "—"}
                  </p>
                  {latest.positioning?.suggested_outlets &&
                    latest.positioning.suggested_outlets.length > 0 && (
                      <div className="flex flex-wrap gap-2">
                        <span className="text-xs text-[var(--ai-muted)]">Suggested outlets:</span>
                        {latest.positioning.suggested_outlets.map((o, i) => (
                          <span
                            key={i}
                            className="text-xs px-2 py-1 rounded-lg bg-[var(--ai-bg-elevated)] text-[var(--ai-text-secondary)]"
                          >
                            {o}
                          </span>
                        ))}
                      </div>
                    )}
                </div>

                {/* Narratives + Threats vs Opportunities grid */}
                <div className="grid md:grid-cols-2 gap-6">
                  <div className={panel}>
                    <h2 className="text-lg font-semibold text-[var(--ai-text)] mb-3">
                      Narratives
                    </h2>
                    <div className="space-y-3">
                      {(latest.narratives || []).map((n, i) => (
                        <div
                          key={i}
                          className="rounded-lg border border-[var(--ai-border)] p-3 bg-[var(--ai-bg-elevated)]"
                        >
                          <p className="font-medium text-[var(--ai-text)]">{n.theme}</p>
                          <p className="text-xs text-[var(--ai-muted)] mt-1">
                            {n.sentiment && `Sentiment: ${n.sentiment} • `}
                            {n.platforms?.length
                              ? `Platforms: ${n.platforms.join(", ")}`
                              : ""}
                          </p>
                          {n.sample_quotes?.length ? (
                            <ul className="mt-2 text-xs text-[var(--ai-text-secondary)] list-disc list-inside">
                              {n.sample_quotes.map((q, j) => (
                                <li key={j}>{q}</li>
                              ))}
                            </ul>
                          ) : null}
                        </div>
                      ))}
                      {(!latest.narratives || latest.narratives.length === 0) && (
                        <p className={muted}>—</p>
                      )}
                    </div>
                  </div>

                  <div className="space-y-6">
                    <div className={panel}>
                      <h2 className="text-lg font-semibold text-[var(--ai-danger)] mb-3">
                        Threats
                      </h2>
                      <ul className="space-y-2">
                        {(latest.threats || []).map((t, i) => (
                          <li key={i} className="text-sm">
                            <span className="font-medium">{t.narrative}</span>
                            {t.severity && (
                              <span className={`ml-2 text-xs ${muted}`}>
                                ({t.severity})
                              </span>
                            )}
                            {t.response_angle && (
                              <p className="text-xs text-[var(--ai-accent)] mt-1">
                                Response: {t.response_angle}
                              </p>
                            )}
                          </li>
                        ))}
                        {(!latest.threats || latest.threats.length === 0) && (
                          <li className={muted}>—</li>
                        )}
                      </ul>
                    </div>

                    <div className={panel}>
                      <h2 className="text-lg font-semibold text-[var(--ai-accent)] mb-3">
                        Opportunities
                      </h2>
                      <ul className="space-y-2">
                        {(latest.opportunities || []).map((o, i) => (
                          <li key={i} className="text-sm">
                            <span className="font-medium">{o.angle}</span>
                            {o.outlet_match && (
                              <p className="text-xs text-[var(--ai-muted)] mt-0.5">
                                Outlet: {o.outlet_match}
                              </p>
                            )}
                          </li>
                        ))}
                        {(!latest.opportunities ||
                          latest.opportunities.length === 0) && (
                          <li className={muted}>—</li>
                        )}
                      </ul>
                    </div>
                  </div>
                </div>

                {/* Evidence (collapsible) */}
                {latest.evidence_refs && latest.evidence_refs.length > 0 && (
                  <div className={panel}>
                    <button
                      type="button"
                      onClick={() => setEvidenceOpen(!evidenceOpen)}
                      className="flex items-center gap-2 text-lg font-semibold text-[var(--ai-text)]"
                    >
                      Evidence ({latest.evidence_refs.length})
                      <svg
                        className={`h-4 w-4 transition-transform ${evidenceOpen ? "rotate-180" : ""}`}
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M19 9l-7 7-7-7"
                        />
                      </svg>
                    </button>
                    {evidenceOpen && (
                      <ul className="mt-4 space-y-2">
                        {latest.evidence_refs.map((e, i) => (
                          <li key={i} className="text-sm">
                            <a
                              href={e.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-[var(--ai-accent)] hover:underline"
                            >
                              [{e.platform || "source"}] {e.title || e.url || "Link"}
                            </a>
                            {e.snippet && (
                              <p className="text-xs text-[var(--ai-muted)] mt-0.5 line-clamp-2">
                                {e.snippet}
                              </p>
                            )}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}

                <p className="text-xs text-[var(--ai-muted)]">
                  Computed: {latest.computed_at || latest.date} • {reports.length} report(s)
                </p>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
