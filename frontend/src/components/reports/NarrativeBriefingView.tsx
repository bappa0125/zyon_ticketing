"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { getApiBase } from "@/lib/api";

interface PackMeta {
  client?: string;
  client_name?: string;
  range_days?: number;
  generated_at?: string;
  memo_source?: string;
  entities_count?: number;
  served_from?: string;
  snapshot_computed_at?: string;
  snapshot_date?: string;
  no_snapshot?: boolean;
  message?: string;
}

interface SurfaceTotals {
  article?: number;
  forum?: number;
  other?: number;
}

interface TrendPoint {
  date: string;
  article: number;
  forum: number;
  other?: number;
  total: number;
}

function MetricBar({
  label,
  value,
  max,
  variant = "default",
}: {
  label: string;
  value: number;
  max: number;
  variant?: "default" | "muted";
}) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div className="flex items-center gap-3 text-sm">
      <span className="w-40 shrink-0 truncate text-[var(--ai-text-secondary)]">{label}</span>
      <div className="flex-1 h-2.5 rounded-full overflow-hidden bg-[var(--ai-bg-elevated)]">
        <div
          className={`h-full rounded-full transition-all duration-500 ${variant === "muted" ? "bg-[var(--ai-muted)]" : "bg-[var(--ai-accent)]"}`}
          style={{ width: `${Math.max(pct, 2)}%` }}
        />
      </div>
      <span className="w-10 text-right tabular-nums text-[var(--ai-muted)]">{value}</span>
    </div>
  );
}

function SurfaceStack({ surface }: { surface: SurfaceTotals }) {
  const pub = surface.article ?? 0;
  const forum = surface.forum ?? 0;
  const other = surface.other ?? 0;
  const total = pub + forum + other || 1;
  return (
    <div className="space-y-2">
      <div className="flex h-4 w-full max-w-xl rounded-full overflow-hidden border border-[var(--ai-border)]">
        <div className="bg-[var(--ai-accent)] h-full transition-all" style={{ width: `${(pub / total) * 100}%` }} title={`Publication ${pub}`} />
        <div className="bg-[var(--ai-accent-dim)] h-full transition-all" style={{ width: `${(forum / total) * 100}%` }} title={`Forum ${forum}`} />
        <div className="bg-[var(--ai-bg-elevated)] h-full transition-all" style={{ width: `${(other / total) * 100}%` }} title={`Other ${other}`} />
      </div>
      <div className="flex flex-wrap gap-4 text-xs text-[var(--ai-muted)]">
        <span>
          <span className="inline-block w-2 h-2 rounded-full bg-[var(--ai-accent)] mr-1 align-middle" /> Publication{" "}
          <strong className="text-[var(--ai-text)]">{pub}</strong>
        </span>
        <span>
          <span className="inline-block w-2 h-2 rounded-full bg-[var(--ai-accent-dim)] mr-1 align-middle" /> Forum{" "}
          <strong className="text-[var(--ai-text)]">{forum}</strong>
        </span>
        {other > 0 && (
          <span>
            <span className="inline-block w-2 h-2 rounded-full bg-[var(--ai-bg-elevated)] border border-[var(--ai-border)] mr-1 align-middle" /> Other{" "}
            <strong className="text-[var(--ai-text)]">{other}</strong>
          </span>
        )}
      </div>
    </div>
  );
}

function bandPolygon(
  series: TrendPoint[],
  n: number,
  pad: number,
  w: number,
  h: number,
  maxT: number,
  cumLow: (s: TrendPoint) => number,
  cumHigh: (s: TrendPoint) => number
): string {
  const innerH = h - 2 * pad;
  const baseY = h - pad;
  const xAt = (i: number) => pad + (n <= 1 ? (w - 2 * pad) / 2 : (i / (n - 1)) * (w - 2 * pad));
  const yAt = (cum: number) => baseY - (cum / maxT) * innerH;
  const pts: string[] = [];
  for (let i = 0; i < n; i++) {
    pts.push(`${xAt(i)},${yAt(cumHigh(series[i]))}`);
  }
  for (let i = n - 1; i >= 0; i--) {
    pts.push(`${xAt(i)},${yAt(cumLow(series[i]))}`);
  }
  return pts.join(" ");
}

function MentionTrendBlock({
  series,
  loading,
  timezoneNote,
}: {
  series: TrendPoint[];
  loading: boolean;
  timezoneNote?: string;
}) {
  const maxTotal = Math.max(...series.map((s) => s.total), 1);
  const w = 380;
  const h = 76;
  const pad = 8;
  const n = series.length || 1;

  const forumPoly =
    series.length > 0 ? bandPolygon(series, n, pad, w, h, maxTotal, () => 0, (s) => s.forum) : "";
  const articlePoly =
    series.length > 0
      ? bandPolygon(series, n, pad, w, h, maxTotal, (s) => s.forum, (s) => s.forum + s.article)
      : "";
  const otherPoly =
    series.length > 0
      ? bandPolygon(
          series,
          n,
          pad,
          w,
          h,
          maxTotal,
          (s) => s.forum + s.article,
          (s) => s.total
        )
      : "";

  if (loading) {
    return <p className="text-sm text-[var(--ai-muted)]">Loading 7-day trend…</p>;
  }
  if (!series.length) {
    return <p className="text-sm text-[var(--ai-muted)]">No mentions in this window for trend.</p>;
  }

  return (
    <div className="grid md:grid-cols-2 gap-6 items-end">
      <div>
        <svg width={w} height={h} className="overflow-visible" aria-label="Mentions trend stacked mini-series">
          <line x1={pad} y1={h - pad} x2={w - pad} y2={h - pad} stroke="var(--ai-border)" strokeWidth={1} />
          {forumPoly && (
            <polygon
              points={forumPoly}
              fill="rgba(0, 194, 255, 0.22)"
              stroke="rgba(0, 194, 255, 0.45)"
              strokeWidth={0.75}
            />
          )}
          {articlePoly && (
            <polygon
              points={articlePoly}
              fill="rgba(0, 194, 255, 0.42)"
              stroke="rgba(0, 194, 255, 0.65)"
              strokeWidth={0.75}
            />
          )}
          {otherPoly && (
            <polygon
              points={otherPoly}
              fill="rgba(255, 255, 255, 0.08)"
              stroke="rgba(255, 255, 255, 0.2)"
              strokeWidth={0.75}
            />
          )}
        </svg>
        <div className="flex flex-wrap gap-3 mt-2 text-[10px] text-[var(--ai-muted)]">
          <span>
            <span className="inline-block w-2 h-2 rounded-sm bg-[rgba(0,194,255,0.35)] mr-1 align-middle" /> Forum
          </span>
          <span>
            <span className="inline-block w-2 h-2 rounded-sm bg-[rgba(0,194,255,0.55)] mr-1 align-middle" /> Publication
          </span>
          <span>
            <span className="inline-block w-2 h-2 rounded-sm bg-white/15 border border-white/25 mr-1 align-middle" /> Other
          </span>
        </div>
        <p className="text-xs text-[var(--ai-muted)] mt-1">
          Stacked areas = signal mix per day (scaled to max day). {timezoneNote || "Buckets: UTC."}
        </p>
      </div>
      <div className="flex gap-1.5 items-end h-[80px] border-b border-[var(--ai-border)] pb-0.5">
        {series.map((s) => {
          const stack = s.article + s.forum;
          const barPx = maxTotal > 0 ? Math.max(2, Math.round((stack / maxTotal) * 56)) : 0;
          const pubPx = stack > 0 ? Math.round((s.article / stack) * barPx) : 0;
          const forumPx = barPx - pubPx;
          return (
            <div
              key={s.date}
              className="flex-1 min-w-[22px] flex flex-col justify-end items-stretch group relative"
              title={`${s.date}: ${s.total} (pub ${s.article}, forum ${s.forum})`}
            >
              <div className="w-full flex flex-col justify-end rounded-t overflow-hidden" style={{ height: barPx }}>
                {forumPx > 0 && <div className="w-full bg-[var(--ai-accent-dim)]" style={{ height: forumPx }} />}
                {pubPx > 0 && <div className="w-full bg-[var(--ai-accent)]" style={{ height: pubPx }} />}
              </div>
              <span className="text-[9px] text-center text-[var(--ai-muted)] truncate block mt-0.5 leading-none">{s.date.slice(5)}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function NarrativeBriefingView({ showReportsTabsHint = false }: { showReportsTabsHint?: boolean }) {
  const [client, setClient] = useState("Sahi");
  const [rangeDays, setRangeDays] = useState(30);
  const [pack, setPack] = useState<{
    meta?: PackMeta;
    memo?: { bullets?: string[]; raw_markdown?: string };
    surface_totals?: SurfaceTotals;
    executive_gaps?: { narrative_tag: string; gap_type: string; headline: string }[];
    exhibits?: Record<string, unknown>;
    deep_links?: Record<string, string>;
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [trendSeries, setTrendSeries] = useState<TrendPoint[]>([]);
  const [trendLoading, setTrendLoading] = useState(true);
  const [trendTzNote, setTrendTzNote] = useState<string>("");

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const q = new URLSearchParams({
        client: client.trim() || "Sahi",
        range_days: String(rangeDays),
      });
      const res = await fetch(`${getApiBase()}/social/narrative-briefing-pack?${q}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setPack(await res.json());
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setPack(null);
    } finally {
      setLoading(false);
    }
  }, [client, rangeDays]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    let cancelled = false;
    async function loadTrends() {
      setTrendLoading(true);
      try {
        const q = new URLSearchParams({ client: client.trim() || "Sahi", days: "7" });
        const res = await fetch(`${getApiBase()}/social/narrative-briefing-trends?${q}`);
        const data = await res.json();
        if (!cancelled) {
          setTrendSeries(Array.isArray(data.series) ? data.series : []);
          const eff = typeof data.timezone_effective === "string" ? data.timezone_effective : "UTC";
          const ist = eff === "Asia/Kolkata" ? " IST" : "";
          const fb = data.mongo_timezone_fallback_utc
            ? " (Mongo fell back to UTC buckets — upgrade server or use UTC-only charts.)"
            : "";
          setTrendTzNote(`Daily buckets: ${eff}${ist}.${fb}`);
        }
      } catch {
        if (!cancelled) {
          setTrendSeries([]);
          setTrendTzNote("");
        }
      } finally {
        if (!cancelled) setTrendLoading(false);
      }
    }
    loadTrends();
    return () => {
      cancelled = true;
    };
  }, [client]);

  const meta = pack?.meta;
  const surface = pack?.surface_totals || {};
  const pub = surface.article ?? 0;
  const forum = surface.forum ?? 0;
  const maxSf = Math.max(pub, forum, 1);

  const exhibits = pack?.exhibits as
    | {
        A?: { label?: string; subtitle?: string; landscape?: unknown[] };
        B?: {
          label?: string;
          subtitle?: string;
          rows?: { narrative_tag: string; forum_site: string; mention_count: number; sample_urls?: string[] }[];
        };
        C?: { label?: string; subtitle?: string; summaries?: { date?: string; narrative?: string; themes?: unknown[] }[] };
        D?: {
          label?: string;
          subtitle?: string;
          themes?: { label?: string; description?: string }[];
          posts?: { title?: string; url?: string; subreddit?: string }[];
        };
        E?: { label?: string; subtitle?: string; reports?: Record<string, unknown>[] };
      }
    | undefined;

  const forumRows = exhibits?.B?.rows || [];
  const maxForum = Math.max(...forumRows.map((r) => r.mention_count), 1);
  const landscapeRows = (exhibits?.A?.landscape || []) as Record<string, unknown>[];

  const dedupedGaps = useMemo(() => {
    const seen = new Set<string>();
    const out: { narrative_tag: string; gap_type: string; headline: string }[] = [];
    for (const g of pack?.executive_gaps || []) {
      const k = (g.narrative_tag || "").toLowerCase();
      if (!k || seen.has(k)) continue;
      seen.add(k);
      out.push(g);
    }
    return out;
  }, [pack?.executive_gaps]);

  const gapTakeaways = useMemo(
    () =>
      dedupedGaps.map(
        (g) => `${g.narrative_tag.replace(/_/g, " ")} (${g.gap_type.replace(/_/g, " ")}): ${g.headline}`
      ),
    [dedupedGaps]
  );

  const links = pack?.deep_links || {};

  if (loading && !pack) {
    return (
      <div className="app-page">
        <div className="max-w-5xl mx-auto p-6">
          <p className="text-[var(--ai-muted)]">Loading narrative briefing snapshot…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="app-page">
      <div className="max-w-5xl mx-auto p-6 pb-16">
        <header className="flex flex-wrap items-center justify-between gap-4 mb-6">
          <div>
            <h1 className="text-2xl font-semibold text-[var(--ai-text)]">Narrative executive briefing</h1>
            <p className="text-sm text-[var(--ai-muted)] mt-1">
              Stored snapshot + live 7-day mention trend. Memo from daily ingestion (no on-demand LLM).
              {showReportsTabsHint ? " Switch tabs above for intelligence tables." : " "}
              <Link href="/reports/executive-report" className="text-[var(--ai-accent)] hover:underline font-medium">
                Executive Report
              </Link>{" "}
              has full competitor tables.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Link
              href="/reports/executive-report"
              className="px-4 py-2 rounded-lg border border-[var(--ai-border)] bg-[var(--ai-surface)] text-[var(--ai-text-secondary)] font-medium text-sm hover:bg-[var(--ai-surface-hover)]"
            >
              Intelligence tables
            </Link>
            <button
              type="button"
              onClick={() => load()}
              disabled={loading}
              className="px-4 py-2 rounded-lg bg-[var(--ai-accent-dim)] text-[var(--ai-accent)] font-medium text-sm hover:bg-[var(--ai-accent)] hover:text-[var(--ai-bg)] disabled:opacity-50"
            >
              {loading ? "Loading…" : "Refresh snapshot"}
            </button>
          </div>
        </header>

        <div className="flex flex-wrap items-end gap-4 p-4 rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] mb-6">
          <label className="flex flex-col gap-1 text-xs text-[var(--ai-muted)]">
            Client
            <input
              value={client}
              onChange={(e) => setClient(e.target.value)}
              className="px-3 py-2 rounded-lg border border-[var(--ai-border)] bg-[var(--ai-bg)] text-[var(--ai-text)] text-sm w-36"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-[var(--ai-muted)]">
            Snapshot window
            <select
              value={rangeDays}
              onChange={(e) => setRangeDays(Number(e.target.value))}
              className="px-3 py-2 rounded-lg border border-[var(--ai-border)] bg-[var(--ai-bg)] text-[var(--ai-text)] text-sm"
            >
              {[14, 30, 60, 90].map((d) => (
                <option key={d} value={d}>
                  {d} days
                </option>
              ))}
            </select>
          </label>
          <div className="flex flex-wrap gap-2 text-xs ml-auto">
            {Object.entries(links).map(([k, href]) => (
              <Link
                key={k}
                href={href}
                className="px-2 py-1 rounded-md border border-[var(--ai-border)] text-[var(--ai-text-secondary)] hover:bg-[var(--ai-bg-elevated)]"
              >
                {k.replace(/_/g, " ")}
              </Link>
            ))}
          </div>
        </div>

        {err && (
          <div className="mb-4 p-4 rounded-xl border border-[var(--ai-danger)]/40 bg-[var(--ai-danger)]/10 text-sm text-[var(--ai-danger)]" role="alert">
            {err}
          </div>
        )}

        {meta?.no_snapshot && (
          <div className="mb-6 p-4 rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] text-sm text-[var(--ai-text-secondary)]" role="status">
            <p className="font-medium text-[var(--ai-text)] mb-1">No snapshot for this client / window</p>
            <p>
              {meta.message ||
                "Run master backfill (phase `narrative_briefing`) or `python scripts/run_narrative_briefing_daily.py` in the backend container."}
            </p>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-4 p-4 rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] text-xs text-[var(--ai-muted)] mb-6">
          <span>
            <strong className="text-[var(--ai-text-secondary)]">Snapshot window:</strong> {rangeDays} days
          </span>
          {meta?.client_name && (
            <span>
              <strong className="text-[var(--ai-text-secondary)]">Universe:</strong> {meta.client_name}
              {meta.entities_count != null ? ` · ${meta.entities_count} entities` : ""}
            </span>
          )}
          {(meta?.snapshot_computed_at || meta?.snapshot_date) && (
            <span>
              <strong className="text-[var(--ai-text-secondary)]">Snapshot:</strong> {meta.snapshot_date}
              {meta.snapshot_computed_at ? ` · ${new Date(meta.snapshot_computed_at).toLocaleString()}` : ""}
            </span>
          )}
          {meta?.memo_source && (
            <span>
              <strong className="text-[var(--ai-text-secondary)]">Memo:</strong> {meta.memo_source}
            </span>
          )}
        </div>

        <section className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-5 mb-6">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-[var(--ai-text)] mb-1">
            0. Seven-day mention trend (live)
          </h2>
          <p className="text-xs text-[var(--ai-muted)] mb-4">
            Daily entity_mentions for {meta?.client_name || client} + competitors — publication (accent) vs forum (dim). Sparkline shows total per day.
          </p>
          <MentionTrendBlock series={trendSeries} loading={trendLoading} timezoneNote={trendTzNote} />
          {!trendLoading && trendSeries.length > 0 && (
            <div className="overflow-x-auto mt-4">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-[var(--ai-border)]">
                    <th className="text-left py-1.5 text-[var(--ai-muted)]">Date</th>
                    <th className="text-right py-1.5 text-[var(--ai-muted)]">Pub</th>
                    <th className="text-right py-1.5 text-[var(--ai-muted)]">Forum</th>
                    <th className="text-right py-1.5 text-[var(--ai-muted)]">Total</th>
                  </tr>
                </thead>
                <tbody>
                  {trendSeries.map((s) => (
                    <tr key={s.date} className="border-b border-[var(--ai-border)]/60">
                      <td className="py-1.5 text-[var(--ai-text)]">{s.date}</td>
                      <td className="text-right tabular-nums">{s.article}</td>
                      <td className="text-right tabular-nums">{s.forum}</td>
                      <td className="text-right tabular-nums font-medium">{s.total}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-6 mb-6">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-[var(--ai-muted)] mb-3">Executive memo</h2>
          <div className="text-sm text-[var(--ai-text-secondary)] leading-relaxed briefing-memo-prose [&_strong]:text-[var(--ai-text)] [&_a]:text-[var(--ai-accent)]">
            {pack?.memo?.raw_markdown ? (
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{pack.memo.raw_markdown}</ReactMarkdown>
            ) : pack?.memo?.bullets?.length ? (
              <ul className="list-none pl-0 space-y-2">
                {pack.memo.bullets.map((b, i) => (
                  <li key={i} className="pl-4 border-l-2 border-[var(--ai-accent)]">
                    {b}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-[var(--ai-muted)]">No memo body in this snapshot.</p>
            )}
          </div>
          {gapTakeaways.length > 0 && (
            <div className="mt-6 pt-6 border-t border-[var(--ai-border)]">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--ai-muted)] mb-3">
                Priority gap bullets (deduped by narrative)
              </h3>
              <ul className="list-none pl-0 space-y-2">
                {gapTakeaways.map((t, i) => (
                  <li key={i} className="text-sm text-[var(--ai-text-secondary)] pl-4 border-l-2 border-[var(--ai-accent-dim)]">
                    {t}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>

        <section className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-5 mb-6">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-[var(--ai-text)] mb-1">
            1. Publication vs forum (snapshot window)
          </h2>
          <p className="text-xs text-[var(--ai-muted)] mb-4">
            Corpus split for {meta?.client_name || client} + competitors for the selected snapshot window.
          </p>
          <SurfaceStack surface={surface} />
          <div className="mt-6 max-w-xl space-y-2">
            <MetricBar label="Publication / article" value={pub} max={maxSf} />
            <MetricBar label="Forum" value={forum} max={maxSf} variant="muted" />
          </div>
        </section>

        <section className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-5 mb-6">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-[var(--ai-text)] mb-1">2. Forum narrative traction (tag × site)</h2>
          <p className="text-xs text-[var(--ai-muted)] mb-4">{exhibits?.B?.subtitle || "Rule-based narrative tags on forum mentions."}</p>
          {forumRows.length === 0 ? (
            <p className="text-sm text-[var(--ai-muted)] py-4 text-center">No forum narrative rows in this window.</p>
          ) : (
            <>
              <div className="mb-6 max-w-2xl space-y-2">
                {forumRows.slice(0, 8).map((r) => (
                  <MetricBar
                    key={r.narrative_tag + r.forum_site}
                    label={`${r.narrative_tag.replace(/_/g, " ")} · ${r.forum_site}`}
                    value={r.mention_count}
                    max={maxForum}
                  />
                ))}
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-[var(--ai-border)]">
                      <th className="text-left py-2 pr-4 text-[var(--ai-muted)] font-medium">Narrative</th>
                      <th className="text-left py-2 pr-4 text-[var(--ai-muted)] font-medium">Forum</th>
                      <th className="text-right py-2 px-2 text-[var(--ai-muted)] font-medium">Mentions</th>
                      <th className="text-left py-2 pl-2 text-[var(--ai-muted)] font-medium">Sample</th>
                    </tr>
                  </thead>
                  <tbody>
                    {forumRows.slice(0, 12).map((r, i) => (
                      <tr key={i} className="border-b border-[var(--ai-border)] last:border-0">
                        <td className="py-2.5 pr-4 font-medium text-[var(--ai-text)]">{r.narrative_tag.replace(/_/g, " ")}</td>
                        <td className="py-2.5 pr-4 text-[var(--ai-text-secondary)]">{r.forum_site}</td>
                        <td className="text-right py-2.5 px-2 tabular-nums">{r.mention_count}</td>
                        <td className="py-2.5 pl-2">
                          {r.sample_urls?.[0] ? (
                            <a href={r.sample_urls[0]} target="_blank" rel="noreferrer" className="text-[var(--ai-accent)] hover:underline">
                              Open thread
                            </a>
                          ) : (
                            <span className="text-[var(--ai-muted)]">—</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </section>

        <section className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-5 mb-6">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-[var(--ai-text)] mb-1">3. Narrative landscape (themes & receipts)</h2>
          <p className="text-xs text-[var(--ai-muted)] mb-4">{exhibits?.A?.subtitle}</p>
          {landscapeRows.length === 0 ? (
            <p className="text-sm text-[var(--ai-muted)] py-4 text-center">No landscape rows in snapshot.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[var(--ai-border)]">
                    <th className="text-left py-2 pr-3 text-[var(--ai-muted)] font-medium">Theme</th>
                    <th className="text-right py-2 px-2 text-[var(--ai-muted)] font-medium">Pub</th>
                    <th className="text-right py-2 px-2 text-[var(--ai-muted)] font-medium">Forum</th>
                    <th className="text-right py-2 px-2 text-[var(--ai-muted)] font-medium">SoV %</th>
                    <th className="text-left py-2 px-2 text-[var(--ai-muted)] font-medium">Gap</th>
                    <th className="text-left py-2 pl-2 text-[var(--ai-muted)] font-medium">Receipts</th>
                  </tr>
                </thead>
                <tbody>
                  {landscapeRows.map((raw, i) => {
                    const r = raw as {
                      narrative_label?: string;
                      gap_type?: string;
                      counts?: { publication?: number; forum?: number };
                      sahi?: { share_of_voice_pct?: number };
                      where_it_started?: { publication?: { title?: string; url?: string } | null };
                      what_amplified_it?: { forum?: { title?: string; url?: string } | null };
                    };
                    const pu = r.where_it_started?.publication;
                    const fo = r.what_amplified_it?.forum;
                    return (
                      <tr key={i} className="border-b border-[var(--ai-border)] last:border-0 align-top">
                        <td className="py-2.5 pr-3 font-medium text-[var(--ai-text)]">{r.narrative_label}</td>
                        <td className="text-right py-2.5 px-2 tabular-nums">{r.counts?.publication ?? 0}</td>
                        <td className="text-right py-2.5 px-2 tabular-nums">{r.counts?.forum ?? 0}</td>
                        <td className="text-right py-2.5 px-2 tabular-nums">{r.sahi?.share_of_voice_pct ?? 0}%</td>
                        <td className="py-2.5 px-2 text-[var(--ai-text-secondary)] text-xs">{r.gap_type?.replace(/_/g, " ")}</td>
                        <td className="py-2.5 pl-2 text-xs space-y-1">
                          {pu?.url && (
                            <div>
                              <span className="text-[var(--ai-muted)]">Pub: </span>
                              <a href={pu.url} target="_blank" rel="noreferrer" className="text-[var(--ai-accent)] hover:underline">
                                {pu.title || "link"}
                              </a>
                            </div>
                          )}
                          {fo?.url && (
                            <div>
                              <span className="text-[var(--ai-muted)]">Forum: </span>
                              <a href={fo.url} target="_blank" rel="noreferrer" className="text-[var(--ai-accent)] hover:underline">
                                {fo.title || "link"}
                              </a>
                            </div>
                          )}
                          {!pu?.url && !fo?.url && <span className="text-[var(--ai-muted)]">—</span>}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-5 mb-6">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-[var(--ai-text)] mb-1">4. YouTube narrative (daily snapshots)</h2>
          <p className="text-xs text-[var(--ai-muted)] mb-4">{exhibits?.C?.subtitle}</p>
          {!exhibits?.C?.summaries?.length ? (
            <p className="text-sm text-[var(--ai-muted)] py-4 text-center">No YouTube summaries in DB for this pack.</p>
          ) : (
            <ul className="space-y-4">
              {exhibits.C.summaries.map((s) => (
                <li key={s.date} className="pb-4 border-b border-[var(--ai-border)] last:border-0">
                  <p className="text-xs text-[var(--ai-muted)] mb-1">{s.date}</p>
                  <p className="text-sm text-[var(--ai-text-secondary)]">{s.narrative || "—"}</p>
                  {s.themes && s.themes.length > 0 && (
                    <p className="text-xs text-[var(--ai-muted)] mt-2">
                      Themes:{" "}
                      {s.themes
                        .map((t) => (typeof t === "string" ? t : (t as { label?: string }).label || JSON.stringify(t)))
                        .join(", ")}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-5 mb-6">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-[var(--ai-text)] mb-1">5. Reddit velocity</h2>
          <p className="text-xs text-[var(--ai-muted)] mb-4">{exhibits?.D?.subtitle}</p>
          {exhibits?.D?.themes && exhibits.D.themes.length > 0 ? (
            <div className="overflow-x-auto mb-6">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[var(--ai-border)]">
                    <th className="text-left py-2 pr-4 text-[var(--ai-muted)] font-medium">Theme</th>
                    <th className="text-left py-2 pl-2 text-[var(--ai-muted)] font-medium">Description</th>
                  </tr>
                </thead>
                <tbody>
                  {exhibits.D.themes.map((t, i) => (
                    <tr key={i} className="border-b border-[var(--ai-border)] last:border-0">
                      <td className="py-2.5 pr-4 font-medium text-[var(--ai-text)]">{t.label}</td>
                      <td className="py-2.5 pl-2 text-[var(--ai-text-secondary)]">{t.description || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-[var(--ai-muted)] mb-4">No Reddit themes in DB.</p>
          )}
          <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--ai-muted)] mb-2">Recent posts (sample)</h3>
          <ul className="space-y-1">
            {(exhibits?.D?.posts || []).slice(0, 8).map((p, i) => (
              <li key={i} className="text-sm">
                <a href={p.url} target="_blank" rel="noreferrer" className="text-[var(--ai-accent)] hover:underline">
                  <span className="text-[var(--ai-muted)] text-xs mr-2">r/{p.subreddit}</span>
                  {p.title}
                </a>
              </li>
            ))}
          </ul>
        </section>

        <section className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-5 mb-6">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-[var(--ai-text)] mb-1">6. PR narrative positioning (stored)</h2>
          <p className="text-xs text-[var(--ai-muted)] mb-4">{exhibits?.E?.subtitle}</p>
          {!exhibits?.E?.reports?.length ? (
            <p className="text-sm text-[var(--ai-muted)]">No positioning reports — run narrative positioning batch (or master backfill).</p>
          ) : (
            exhibits.E.reports.map((rep, i) => {
              const positioning = rep.positioning as { headline?: string; pitch_angle?: string } | undefined;
              const threats = rep.threats as { narrative?: string; severity?: string }[] | undefined;
              const opps = rep.opportunities as { angle?: string }[] | undefined;
              return (
                <div key={i} className="mb-6 pb-6 border-b border-[var(--ai-border)] last:border-0">
                  {positioning?.headline && <p className="font-semibold text-[var(--ai-text)] mb-2">{positioning.headline}</p>}
                  {positioning?.pitch_angle && <p className="text-sm text-[var(--ai-text-secondary)] mb-3">{positioning.pitch_angle}</p>}
                  {threats && threats.length > 0 && (
                    <div className="mb-3">
                      <p className="text-xs font-semibold text-[var(--ai-muted)] uppercase tracking-wider mb-1">Threats</p>
                      <ul className="list-none space-y-1">
                        {threats.slice(0, 6).map((t, j) => (
                          <li key={j} className="text-sm text-[var(--ai-text-secondary)] pl-3 border-l-2 border-[var(--ai-border)]">
                            <span className="text-[var(--ai-muted)]">{t.severity || "watch"}</span> — {t.narrative}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {opps && opps.length > 0 && (
                    <div>
                      <p className="text-xs font-semibold text-[var(--ai-muted)] uppercase tracking-wider mb-1">Opportunities</p>
                      <ul className="list-none space-y-1">
                        {opps.slice(0, 5).map((o, j) => (
                          <li key={j} className="text-sm text-[var(--ai-text-secondary)] pl-3 border-l-2 border-[var(--ai-accent-dim)]">
                            {o.angle}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </section>
      </div>
    </div>
  );
}
