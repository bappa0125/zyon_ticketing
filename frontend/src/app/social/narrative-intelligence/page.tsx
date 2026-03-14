"use client";

import { useState, useEffect, useCallback } from "react";
import { getApiBase } from "@/lib/api";

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

  const runBatch = async () => {
    setRunningBatch(true);
    try {
      const res = await fetch(`${getApiBase()}/social/narrative-positioning/run-batch`, {
        method: "POST",
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (data.ok) {
        await fetchReports();
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

        {reports.length === 0 ? (
          <div className={`${panel} py-12 text-center ${muted}`}>
            <p className="mb-2">No narrative positioning data. Run the batch or:</p>
            <code className="block text-left max-w-md mx-auto bg-[var(--ai-bg-elevated)] px-3 py-2 rounded-lg text-xs overflow-x-auto">
              docker compose exec backend python scripts/run_narrative_positioning_backfill.py
            </code>
          </div>
        ) : (
          <div className="space-y-6">
            {latest && (
              <>
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
