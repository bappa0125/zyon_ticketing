"use client";

import { useState, useEffect, useCallback } from "react";
import { getApiBase, withClientQuery } from "@/lib/api";
import { useActiveClient } from "@/context/ClientContext";

interface ForumMention {
  entity: string;
  title: string;
  summary: string;
  source_domain: string;
  url: string;
  published_at: string;
  sentiment?: string;
}

interface ForumTopicTraction {
  topic: string;
  mention_count: number;
  sample_titles: string[];
  sample_urls?: string[];
}

interface ThemeDigestThread {
  title: string;
  url: string;
  strength: number;
  published_at?: string;
}

interface ThemeDigestTheme {
  theme_id: string;
  label: string;
  description?: string;
  thread_count: number;
  keyword_hit_score: number;
  sample_threads: ThemeDigestThread[];
}

interface ThemeDigestSection {
  forum_site: string;
  themes: ThemeDigestTheme[];
}

interface PRDeliverable {
  id: string;
  title: string;
  purpose?: string;
  executive_summary?: string;
  bullets?: string[];
  themes_ranked?: {
    theme_id: string;
    label: string;
    thread_count_total: number;
    keyword_score_total: number;
    lead_example?: { title?: string; url?: string; forum_site?: string };
  }[];
  example_threads?: {
    theme_id?: string;
    theme_label?: string;
    title?: string;
    url?: string;
    forum_site?: string;
  }[];
}

interface PRDeliverablesPack {
  cover_line?: string;
  deliverables?: PRDeliverable[];
}

interface ForumThemeDigest {
  digest_date?: string;
  range_days?: number;
  computed_at?: string;
  disclaimer?: string;
  forum_sites_configured?: string[];
  include_reddit?: boolean;
  surfaces_with_data?: string[];
  sections?: ThemeDigestSection[];
  pr_deliverables?: PRDeliverablesPack;
  stats?: {
    article_documents_scanned?: number;
    forum_documents_scored?: number;
    reddit_posts_scanned?: number;
    reddit_posts_scored?: number;
  };
}

function BoldInline({ text }: { text: string }) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return (
    <>
      {parts.map((part, i) => {
        if (part.startsWith("**") && part.endsWith("**")) {
          return (
            <strong key={i} className="text-[var(--ai-text)]">
              {part.slice(2, -2)}
            </strong>
          );
        }
        return <span key={i}>{part}</span>;
      })}
    </>
  );
}

export default function ForumMentionsPage() {
  const { clientName, ready: clientReady } = useActiveClient();
  const [mentions, setMentions] = useState<ForumMention[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [count, setCount] = useState(0);
  const [topicsTraction, setTopicsTraction] = useState<ForumTopicTraction[]>([]);
  const [topicsLoading, setTopicsLoading] = useState(true);
  const [themeDigest, setThemeDigest] = useState<ForumThemeDigest | null>(null);
  const [digestSource, setDigestSource] = useState<string>("");
  const [digestLoading, setDigestLoading] = useState(true);
  const [digestRefreshing, setDigestRefreshing] = useState(false);

  const fetchThemeDigest = useCallback(async (live: boolean) => {
    if (live) setDigestRefreshing(true);
    else setDigestLoading(true);
    try {
      const params = new URLSearchParams({ days: "7" });
      if (live) params.set("live", "true");
      const path = `${getApiBase()}/social/forum-theme-digest?${params}`;
      const res = await fetch(
        clientReady && clientName ? withClientQuery(path, clientName) : path
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: { digest?: ForumThemeDigest; source?: string } = await res.json();
      setThemeDigest(data.digest ?? null);
      setDigestSource(data.source ?? "");
    } catch {
      setThemeDigest(null);
      setDigestSource("");
    } finally {
      setDigestLoading(false);
      setDigestRefreshing(false);
    }
  }, [clientName, clientReady]);

  const runDigestRefresh = useCallback(async () => {
    setDigestRefreshing(true);
    try {
      const base = `${getApiBase()}/social/forum-theme-digest/refresh`;
      const res = await fetch(
        clientReady && clientName ? withClientQuery(base, clientName) : base,
        { method: "POST" }
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await fetchThemeDigest(false);
    } catch {
      /* keep prior digest */
    } finally {
      setDigestRefreshing(false);
    }
  }, [fetchThemeDigest, clientName, clientReady]);

  const fetchTopicsTraction = useCallback(async () => {
    setTopicsLoading(true);
    try {
      const params = new URLSearchParams({ range_days: "14", top_n: "15" });
      const cn = clientName?.trim() ?? "";
      if (clientReady && cn) params.set("client", cn);
      const path = `${getApiBase()}/social/forum-mentions/topics?${params}`;
      const res = await fetch(
        clientReady && clientName ? withClientQuery(path, clientName) : path
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: { topics?: ForumTopicTraction[] } = await res.json();
      setTopicsTraction(Array.isArray(data.topics) ? data.topics : []);
    } catch {
      setTopicsTraction([]);
    } finally {
      setTopicsLoading(false);
    }
  }, [clientName, clientReady]);

  const fetchMentions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ limit: "80", range_days: "14" });
      const cn = clientName?.trim() ?? "";
      if (clientReady && cn) params.set("entity", cn);
      const path = `${getApiBase()}/social/forum-mentions?${params}`;
      const res = await fetch(
        clientReady && clientName ? withClientQuery(path, clientName) : path
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: { mentions?: ForumMention[]; count?: number } = await res.json();
      setMentions(Array.isArray(data.mentions) ? data.mentions : []);
      setCount(data.count ?? 0);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      setMentions([]);
      setCount(0);
    } finally {
      setLoading(false);
    }
  }, [clientName, clientReady]);

  useEffect(() => {
    fetchMentions();
  }, [fetchMentions]);
  useEffect(() => {
    fetchTopicsTraction();
  }, [fetchTopicsTraction]);
  useEffect(() => {
    fetchThemeDigest(false);
  }, [fetchThemeDigest]);

  const bySource = mentions.reduce<Record<string, number>>((acc, m) => {
    const s = m.source_domain || "—";
    acc[s] = (acc[s] || 0) + 1;
    return acc;
  }, {});
  const sourceEntries = Object.entries(bySource).sort((a, b) => b[1] - a[1]).slice(0, 8);

  if (!clientReady || !clientName) {
    return (
      <div className="app-page p-6">
        <p className="text-sm text-[var(--ai-muted)]">Loading client…</p>
      </div>
    );
  }

  return (
    <div className="app-page">
      <div className="mx-auto w-full max-w-[var(--ai-max-content)]">
        <h1 className="app-heading mb-2">Forum mentions</h1>
        <p className="app-subheading mb-6">
          Mentions from monitored forums (Traderji, TradingQnA, ValuePickr, etc.). Entity detection runs on ingested forum threads.
        </p>

        <section className="mb-8 rounded-xl border border-[var(--ai-accent)]/25 bg-[var(--ai-accent-dim)]/30 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3 mb-2">
            <h2 className="text-sm font-semibold text-[var(--ai-text)]">
              Retail discourse themes (unbranded)
            </h2>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => fetchThemeDigest(true)}
                disabled={digestLoading || digestRefreshing}
                className="app-btn-secondary text-xs py-1.5 px-3"
              >
                {digestRefreshing ? "Recomputing…" : "Recompute now"}
              </button>
              <button
                type="button"
                onClick={() => runDigestRefresh()}
                disabled={digestRefreshing}
                className="app-btn-secondary text-xs py-1.5 px-3"
              >
                Run scheduled job
              </button>
            </div>
          </div>
          <p className="text-xs text-[var(--ai-muted)] mb-3">
            <strong>Indian forums</strong> (ValuePickr, TradingQnA, Traderji) from{" "}
            <code className="text-[var(--ai-accent)]">article_documents</code>
            {themeDigest?.include_reddit !== false ? (
              <>
                {" "}
                + <strong>Reddit</strong> from <code className="text-[var(--ai-accent)]">social_posts</code>
              </>
            ) : null}
            . Themes: <code className="text-[var(--ai-accent)]">narrative_taxonomy.yaml</code> — no brand entity
            required. Includes a <strong>3-part PR pack</strong> for weekly retainers. For meme velocity also use{" "}
            <strong>Social → Reddit trending</strong>.
          </p>
          {digestLoading && !themeDigest ? (
            <div className="py-4 text-center text-[var(--ai-muted)] text-sm">Loading digest…</div>
          ) : !themeDigest ||
            (!(themeDigest.sections && themeDigest.sections.length) &&
              !(themeDigest.pr_deliverables?.deliverables && themeDigest.pr_deliverables.deliverables.length > 0)) ? (
            <div className="py-4 text-sm text-[var(--ai-muted)]">
              No digest yet. Ingest forum RSS/HTML threads (and run Reddit monitor), then{" "}
              <button type="button" className="text-[var(--ai-accent)] underline" onClick={() => runDigestRefresh()}>
                run the digest job
              </button>{" "}
              or <code className="text-xs">GET /api/social/forum-theme-digest?live=true</code>.
            </div>
          ) : (
            <>
              <p className="text-[10px] uppercase tracking-wider text-[var(--ai-muted)] mb-1">
                {themeDigest.digest_date} · last {themeDigest.range_days ?? 7}d · {digestSource}
                {themeDigest.surfaces_with_data?.length
                  ? ` · surfaces: ${themeDigest.surfaces_with_data.join(", ")}`
                  : ""}
                {themeDigest.stats?.forum_documents_scored != null
                  ? ` · ${themeDigest.stats.forum_documents_scored} forum docs`
                  : ""}
                {themeDigest.stats?.reddit_posts_scored != null && themeDigest.stats.reddit_posts_scored > 0
                  ? ` · ${themeDigest.stats.reddit_posts_scored} reddit posts`
                  : ""}
              </p>
              {themeDigest.disclaimer && (
                <p className="text-xs text-[var(--ai-text-secondary)] border-l-2 border-[var(--ai-border-strong)] pl-3 mb-4 italic">
                  {themeDigest.disclaimer}
                </p>
              )}

              {themeDigest.pr_deliverables?.cover_line && (
                <p className="text-sm font-medium text-[var(--ai-text)] mb-3">{themeDigest.pr_deliverables.cover_line}</p>
              )}

              {themeDigest.pr_deliverables?.deliverables && themeDigest.pr_deliverables.deliverables.length > 0 && (
                <div className="mb-8 grid gap-4 md:grid-cols-3">
                  {themeDigest.pr_deliverables.deliverables.map((d) => (
                    <div
                      key={d.id}
                      className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-4 flex flex-col"
                    >
                      <h3 className="text-sm font-semibold text-[var(--ai-accent)] mb-1">{d.title}</h3>
                      {d.purpose && (
                        <p className="text-[10px] text-[var(--ai-muted)] uppercase tracking-wide mb-2">{d.purpose}</p>
                      )}
                      {d.executive_summary && (
                        <p className="text-xs text-[var(--ai-text-secondary)] mb-3 leading-relaxed">
                          <BoldInline text={d.executive_summary} />
                        </p>
                      )}
                      <ul className="text-xs text-[var(--ai-text-secondary)] space-y-2 flex-1 list-disc list-inside">
                        {(d.bullets || []).slice(0, 8).map((b, idx) => (
                          <li key={idx}>
                            <BoldInline text={b} />
                          </li>
                        ))}
                      </ul>
                      {d.themes_ranked && d.themes_ranked.length > 0 && (
                        <div className="mt-3 pt-3 border-t border-[var(--ai-border)] text-[10px] text-[var(--ai-muted)]">
                          <p className="font-medium text-[var(--ai-text-secondary)] mb-1">Lead examples</p>
                          {d.themes_ranked.slice(0, 4).map((tr) => {
                            const lt = tr.lead_example?.title?.trim() || "";
                            const short = lt.length > 56 ? `${lt.slice(0, 56)}…` : lt;
                            return (
                              <div key={tr.theme_id} className="mb-2">
                                <span className="text-[var(--ai-text)]">{tr.label}</span>
                                {tr.lead_example?.url && (
                                  <>
                                    {" "}
                                    <a
                                      href={tr.lead_example.url}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      className="text-[var(--ai-accent)] hover:underline break-all"
                                      title={lt || undefined}
                                    >
                                      {short || "Open example"}
                                    </a>
                                    <span className="text-[var(--ai-muted)]"> · {tr.lead_example.forum_site}</span>
                                  </>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      )}
                      {d.example_threads && d.example_threads.length > 0 && (
                        <ul className="mt-3 pt-3 border-t border-[var(--ai-border)] text-[10px] space-y-1.5">
                          {d.example_threads.slice(0, 6).map((ex, idx) => (
                            <li key={idx} className="text-[var(--ai-text-secondary)]">
                              {ex.url ? (
                                <a
                                  href={ex.url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="text-[var(--ai-accent)] hover:underline break-all"
                                >
                                  {ex.title?.trim() || ex.theme_label || "Open thread"}
                                </a>
                              ) : (
                                <span>{ex.theme_label}</span>
                              )}
                              {ex.forum_site ? (
                                <span className="text-[var(--ai-muted)]"> · {ex.forum_site}</span>
                              ) : null}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  ))}
                </div>
              )}

              <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--ai-muted)] mb-3">
                Theme detail by surface
              </h3>
              <div className="space-y-6">
                {(themeDigest.sections || []).map((sec) => (
                  <div key={sec.forum_site}>
                    <h3 className="text-xs font-bold uppercase tracking-wider text-[var(--ai-accent)] mb-2">
                      {sec.forum_site}
                    </h3>
                    <div className="space-y-4">
                      {(sec.themes || []).slice(0, 12).map((th) => (
                        <div
                          key={th.theme_id}
                          className="rounded-lg border border-[var(--ai-border)] bg-[var(--ai-surface)] p-3"
                        >
                          <div className="flex flex-wrap items-baseline justify-between gap-2 mb-1">
                            <span className="text-sm font-medium text-[var(--ai-text)]">{th.label}</span>
                            <span className="text-xs text-[var(--ai-muted)] tabular-nums">
                              {th.thread_count} threads · score {th.keyword_hit_score}
                            </span>
                          </div>
                          {th.description && (
                            <p className="text-xs text-[var(--ai-text-secondary)] mb-2">{th.description}</p>
                          )}
                          <ul className="space-y-1.5 text-xs">
                            {(th.sample_threads || []).map((t, j) => (
                              <li key={j}>
                                <a
                                  href={t.url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="text-[var(--ai-accent)] hover:underline break-all"
                                >
                                  {t.title}
                                </a>
                                <span className="text-[var(--ai-muted)] ml-1">({t.strength})</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
              {(themeDigest.sections || []).length === 0 && (
                <p className="text-xs text-[var(--ai-muted)] mt-4">
                  No per-surface theme rows yet — PR pack above may still reflect sparse data. Run ingestion and refresh.
                </p>
              )}
            </>
          )}
        </section>

        <div className="flex flex-wrap items-center gap-4 mb-6">
          <p className="text-sm text-[var(--ai-text-secondary)]">
            Client / entity: <strong className="text-[var(--ai-text)]">{clientName}</strong>
          </p>
          <button
            type="button"
            onClick={() => fetchMentions()}
            disabled={loading}
            className="app-btn-secondary text-sm py-2 px-3"
          >
            {loading ? "Loading…" : "Refresh"}
          </button>
          {count >= 0 && (
            <span className="text-sm text-[var(--ai-muted)]">
              {count} mention{count !== 1 ? "s" : ""} (last 14 days)
            </span>
          )}
        </div>

        {error && (
          <div className="mb-6 rounded-xl border border-[var(--ai-danger)]/50 bg-[var(--ai-danger)]/10 px-4 py-3 text-sm text-[var(--ai-danger)]">
            {error}
          </div>
        )}

        {!error && (
          <section className="mb-6 rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-4">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-[var(--ai-muted)] mb-3">Topics by traction (forums)</h2>
            <p className="text-xs text-[var(--ai-muted)] mb-3">Topics with most forum mentions (last 14 days). Use for PR/content angles.</p>
            {topicsLoading ? (
              <div className="py-4 text-center text-[var(--ai-muted)]">Loading…</div>
            ) : topicsTraction.length === 0 ? (
              <div className="py-4 text-center text-[var(--ai-muted)]">No topic data. Run forum ingestion and article topics pipeline.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-[var(--ai-border)] text-sm">
                  <thead>
                    <tr>
                      <th className="text-left py-2 pr-4 text-[var(--ai-text-secondary)] font-medium">Topic</th>
                      <th className="text-right py-2 px-2 text-[var(--ai-text-secondary)] font-medium">Mentions</th>
                      <th className="text-left py-2 pl-2 text-[var(--ai-text-secondary)] font-medium">Sample titles</th>
                    </tr>
                  </thead>
                  <tbody>
                    {topicsTraction.map((t, i) => (
                      <tr key={i} className="border-t border-[var(--ai-border)]">
                        <td className="py-2 pr-4 font-medium text-[var(--ai-text)]">{t.topic}</td>
                        <td className="text-right py-2 px-2 tabular-nums">{t.mention_count}</td>
                        <td className="py-2 pl-2 text-[var(--ai-muted)] max-w-md truncate" title={(t.sample_titles || []).join(" | ")}>{(t.sample_titles || []).slice(0, 2).join(" • ")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        )}

        {!error && sourceEntries.length > 0 && (
          <section className="mb-6 rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-4">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-[var(--ai-muted)] mb-3">By source</h2>
            <div className="flex flex-wrap gap-3">
              {sourceEntries.map(([domain, n]) => (
                <span
                  key={domain}
                  className="inline-flex items-center gap-2 rounded-full border border-[var(--ai-border)] bg-[var(--ai-bg-elevated)] px-3 py-1.5 text-sm"
                >
                  <span className="text-[var(--ai-text-secondary)] truncate max-w-[140px]" title={domain}>{domain}</span>
                  <span className="font-medium tabular-nums text-[var(--ai-accent)]">{n}</span>
                </span>
              ))}
            </div>
          </section>
        )}

        <section className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] overflow-hidden">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-[var(--ai-muted)] px-4 py-3 border-b border-[var(--ai-border)]">
            Recent forum mentions
          </h2>
          {loading ? (
            <div className="p-8 text-center text-[var(--ai-muted)]">Loading…</div>
          ) : mentions.length === 0 ? (
            <div className="p-8 text-center text-[var(--ai-muted)]">
              No forum mentions in the last 14 days. Run forum ingestion and entity-mentions pipeline to populate.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-[var(--ai-border)]">
                <thead className="bg-[var(--ai-bg-elevated)]">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-[var(--ai-text-secondary)]">Entity</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-[var(--ai-text-secondary)]">Source</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-[var(--ai-text-secondary)]">Title / snippet</th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-[var(--ai-text-secondary)]">Date</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-[var(--ai-text-secondary)]">Link</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--ai-border)]">
                  {mentions.map((m, i) => (
                    <tr key={i} className="hover:bg-[var(--ai-bg-elevated)]/50">
                      <td className="px-4 py-3 text-sm font-medium text-[var(--ai-text)] whitespace-nowrap">{m.entity}</td>
                      <td className="px-4 py-3 text-xs text-[var(--ai-muted)] whitespace-nowrap max-w-[120px] truncate" title={m.source_domain}>{m.source_domain}</td>
                      <td className="px-4 py-3 text-sm text-[var(--ai-text-secondary)] max-w-md">
                        <span className="font-medium text-[var(--ai-text)] line-clamp-1">{m.title || "—"}</span>
                        {m.summary && <p className="mt-0.5 text-xs text-[var(--ai-muted)] line-clamp-2">{m.summary}</p>}
                      </td>
                      <td className="px-4 py-3 text-xs text-[var(--ai-muted)] text-right whitespace-nowrap">
                        {m.published_at ? m.published_at.slice(0, 10) : "—"}
                      </td>
                      <td className="px-4 py-3">
                        {m.url ? (
                          <a href={m.url} target="_blank" rel="noopener noreferrer" className="text-xs text-[var(--ai-accent)] hover:underline truncate max-w-[180px] inline-block">
                            Open
                          </a>
                        ) : (
                          "—"
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
