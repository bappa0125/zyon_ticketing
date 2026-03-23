"use client";

import { useCallback, useEffect, useState } from "react";
import { getApiBase, withClientQuery } from "@/lib/api";
import { useActiveClient } from "@/context/ClientContext";

interface EarliestRef {
  title: string;
  url: string;
  published_at: string;
  entity: string;
  source_domain: string;
  forum_site?: string | null;
}

interface LandscapeRow {
  narrative_tag: string;
  narrative_label: string;
  counts: { publication: number; forum: number; other: number; total: number };
  sahi: { entity: string; mentions: number; share_of_voice_pct: number };
  competitor_mentions_total: number;
  gap_type: string;
  where_it_started: { publication: EarliestRef | null; caption: string };
  what_amplified_it: { forum: EarliestRef | null; caption: string };
  entity_breakdown: { entity: string; count: number }[];
  cxo_moves: string[];
}

interface ExecutiveGap {
  narrative_tag: string;
  gap_type: string;
  headline: string;
}

function Bar({
  value,
  max,
  label,
  color,
}: {
  value: number;
  max: number;
  label: string;
  color: string;
}) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="w-28 shrink-0 truncate text-[var(--ai-text-secondary)]">{label}</span>
      <div className="flex-1 h-4 rounded-full overflow-hidden bg-[var(--ai-bg-elevated)]">
        <div className="h-full rounded-full transition-all duration-700" style={{ width: `${Math.max(pct, 2)}%`, backgroundColor: color }} />
      </div>
      <span className="w-8 text-right text-xs text-[var(--ai-muted)]">{value}</span>
    </div>
  );
}

const gapStyles: Record<string, string> = {
  sahi_absent: "border-rose-500/40 bg-rose-500/10 text-rose-200",
  sahi_underindexed: "border-amber-500/40 bg-amber-500/10 text-amber-100",
  competitive: "border-[var(--ai-border)] bg-[var(--ai-surface)] text-[var(--ai-text-secondary)]",
  sahi_strong: "border-emerald-500/40 bg-emerald-500/10 text-emerald-100",
};

export default function NarrativeLandscapePage() {
  const { clientName: client, ready: clientReady } = useActiveClient();
  const [rangeDays, setRangeDays] = useState(30);
  const [rows, setRows] = useState<LandscapeRow[]>([]);
  const [gaps, setGaps] = useState<ExecutiveGap[]>([]);
  const [frame, setFrame] = useState<Record<string, string> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!clientReady || !client?.trim()) {
      setRows([]);
      setGaps([]);
      setFrame(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        client: client.trim(),
        range_days: String(rangeDays),
        top_tags: "15",
      });
      const res = await fetch(
        withClientQuery(`${getApiBase()}/social/narrative-landscape?${params}`, client)
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (data.error) setError(data.error);
      setRows(Array.isArray(data.landscape) ? data.landscape : []);
      setGaps(Array.isArray(data.executive_gaps) ? data.executive_gaps : []);
      setFrame(typeof data.frame === "object" ? data.frame : null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setRows([]);
      setGaps([]);
    } finally {
      setLoading(false);
    }
  }, [client, rangeDays, clientReady]);

  useEffect(() => {
    load();
  }, [load]);

  if (!clientReady || !client) {
    return (
      <div className="app-page p-6">
        <p className="text-sm text-[var(--ai-muted)]">Loading client…</p>
      </div>
    );
  }

  return (
    <div className="app-page">
      <div className="mx-auto w-full max-w-[var(--ai-max-content)]">
        <h1 className="app-heading mb-2">Narrative landscape</h1>
        <p className="app-subheading mb-6 max-w-3xl">
          CXO-ready view: where themes surface in <strong>publications</strong> vs <strong>forums</strong>, how{" "}
          <strong>Sahi</strong> compares to competitors on each narrative, flagged gaps, and suggested moves.
        </p>

        <div className="flex flex-wrap items-end gap-4 mb-8">
          <p className="text-sm text-[var(--ai-text-secondary)] pb-2">
            Client: <strong className="text-[var(--ai-text)]">{client}</strong>
          </p>
          <label className="flex flex-col gap-1 text-sm text-[var(--ai-text-secondary)]">
            Window (days)
            <select
              value={rangeDays}
              onChange={(e) => setRangeDays(Number(e.target.value))}
              className="rounded-lg border border-[var(--ai-border)] bg-[var(--ai-bg)] px-3 py-2 text-[var(--ai-text)]"
            >
              {[14, 30, 60, 90].map((d) => (
                <option key={d} value={d}>
                  {d} days
                </option>
              ))}
            </select>
          </label>
          <button type="button" onClick={() => load()} disabled={loading} className="app-btn-secondary text-sm py-2 px-4">
            {loading ? "Loading…" : "Refresh"}
          </button>
        </div>

        {frame && (
          <div className="grid md:grid-cols-3 gap-3 mb-8 text-sm text-[var(--ai-text-secondary)]">
            <div className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-4">
              <div className="text-xs uppercase tracking-wide text-[var(--ai-muted)] mb-1">Origin</div>
              {frame.origin}
            </div>
            <div className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-4">
              <div className="text-xs uppercase tracking-wide text-[var(--ai-muted)] mb-1">Amplifier</div>
              {frame.amplifier}
            </div>
            <div className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-4">
              <div className="text-xs uppercase tracking-wide text-[var(--ai-muted)] mb-1">Gap</div>
              {frame.gap}
            </div>
          </div>
        )}

        {error && (
          <div className="mb-6 rounded-xl border border-[var(--ai-danger)]/50 bg-[var(--ai-danger)]/10 px-4 py-3 text-sm text-[var(--ai-danger)]">
            {error}
          </div>
        )}

        {gaps.length > 0 && (
          <section className="mb-10">
            <h2 className="text-lg font-semibold text-[var(--ai-text)] mb-3">Executive gap summary</h2>
            <ul className="space-y-2">
              {gaps.map((g) => (
                <li
                  key={g.narrative_tag + g.gap_type}
                  className={`rounded-xl border px-4 py-3 text-sm ${gapStyles[g.gap_type] || gapStyles.competitive}`}
                >
                  <span className="font-medium">{g.narrative_tag.replace(/_/g, " ")}</span>
                  <span className="opacity-80"> — {g.headline}</span>
                </li>
              ))}
            </ul>
          </section>
        )}

        <section className="space-y-10">
          {rows.map((row) => {
            const maxPubForum = Math.max(row.counts.publication, row.counts.forum, 1);
            const maxEnt = Math.max(...row.entity_breakdown.map((e) => e.count), 1);
            return (
              <article
                key={row.narrative_tag}
                className="rounded-2xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-6 shadow-sm"
              >
                <div className="flex flex-wrap items-start justify-between gap-4 mb-4">
                  <div>
                    <h2 className="text-xl font-semibold text-[var(--ai-text)]">{row.narrative_label}</h2>
                    <p className="text-xs text-[var(--ai-muted)] mt-1">
                      {row.sahi.entity} share of voice:{" "}
                      <strong className="text-[var(--ai-text)]">{row.sahi.share_of_voice_pct}%</strong> ({row.sahi.mentions}{" "}
                      / {row.counts.total} mentions)
                    </p>
                  </div>
                  <span
                    className={`text-xs font-medium uppercase tracking-wide px-3 py-1 rounded-full border ${
                      gapStyles[row.gap_type] || gapStyles.competitive
                    }`}
                  >
                    {row.gap_type.replace(/_/g, " ")}
                  </span>
                </div>

                <div className="grid lg:grid-cols-2 gap-6 mb-6">
                  <div>
                    <h3 className="text-sm font-medium text-[var(--ai-text)] mb-2">Publication vs forum (volume)</h3>
                    <Bar label="Publication" value={row.counts.publication} max={maxPubForum} color="#6366f1" />
                    <div className="h-2" />
                    <Bar label="Forum" value={row.counts.forum} max={maxPubForum} color="#f97316" />
                    <p className="text-xs text-[var(--ai-muted)] mt-3">
                      Higher forum bar → traders are debating this theme; higher publication bar → press/RSS led the window.
                    </p>
                  </div>
                  <div>
                    <h3 className="text-sm font-medium text-[var(--ai-text)] mb-2">Who owns the narrative (entities)</h3>
                    <div className="space-y-1">
                      {row.entity_breakdown.slice(0, 8).map((e) => (
                        <Bar
                          key={e.entity}
                          label={e.entity}
                          value={e.count}
                          max={maxEnt}
                          color={e.entity === row.sahi.entity ? "#22c55e" : "var(--ai-accent)"}
                        />
                      ))}
                    </div>
                  </div>
                </div>

                <div className="grid md:grid-cols-2 gap-4 mb-6 text-sm">
                  <div className="rounded-xl bg-[var(--ai-bg)] p-4 border border-[var(--ai-border)]">
                    <div className="text-xs uppercase text-[var(--ai-muted)] mb-1">Where it started (in window)</div>
                    <p className="text-[var(--ai-text-secondary)] mb-2">{row.where_it_started.caption}</p>
                    {row.where_it_started.publication ? (
                      <a
                        href={row.where_it_started.publication.url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-[var(--ai-accent)] hover:underline block font-medium"
                      >
                        {row.where_it_started.publication.title || row.where_it_started.publication.url}
                      </a>
                    ) : (
                      <span className="text-[var(--ai-muted)]">—</span>
                    )}
                  </div>
                  <div className="rounded-xl bg-[var(--ai-bg)] p-4 border border-[var(--ai-border)]">
                    <div className="text-xs uppercase text-[var(--ai-muted)] mb-1">What amplified it (forums)</div>
                    <p className="text-[var(--ai-text-secondary)] mb-2">{row.what_amplified_it.caption}</p>
                    {row.what_amplified_it.forum ? (
                      <>
                        <a
                          href={row.what_amplified_it.forum.url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-[var(--ai-accent)] hover:underline block font-medium"
                        >
                          {row.what_amplified_it.forum.title || row.what_amplified_it.forum.url}
                        </a>
                        {row.what_amplified_it.forum.forum_site && (
                          <span className="text-xs text-[var(--ai-muted)]">{row.what_amplified_it.forum.forum_site}</span>
                        )}
                      </>
                    ) : (
                      <span className="text-[var(--ai-muted)]">—</span>
                    )}
                  </div>
                </div>

                <div>
                  <h3 className="text-sm font-medium text-[var(--ai-text)] mb-2">How to use this position (CXO moves)</h3>
                  <ul className="list-disc pl-5 space-y-1 text-[var(--ai-text-secondary)] text-sm">
                    {row.cxo_moves.map((m, i) => (
                      <li key={i}>{m}</li>
                    ))}
                  </ul>
                </div>
              </article>
            );
          })}
        </section>

        {!loading && rows.length === 0 && !error && (
          <p className="text-[var(--ai-muted)] text-sm">No tagged mentions in this window. Run ingestion and entity backfill.</p>
        )}
      </div>
    </div>
  );
}
