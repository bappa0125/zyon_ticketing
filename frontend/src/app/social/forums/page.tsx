"use client";

import { useState, useEffect, useCallback } from "react";
import { getApiBase } from "@/lib/api";

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

export default function ForumMentionsPage() {
  const [mentions, setMentions] = useState<ForumMention[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [entityFilter, setEntityFilter] = useState<string>("");
  const [count, setCount] = useState(0);
  const [topicsTraction, setTopicsTraction] = useState<ForumTopicTraction[]>([]);
  const [topicsLoading, setTopicsLoading] = useState(true);

  const fetchTopicsTraction = useCallback(async () => {
    setTopicsLoading(true);
    try {
      const params = new URLSearchParams({ range_days: "14", top_n: "15" });
      if (entityFilter.trim()) params.set("client", entityFilter.trim());
      const res = await fetch(`${getApiBase()}/social/forum-mentions/topics?${params}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: { topics?: ForumTopicTraction[] } = await res.json();
      setTopicsTraction(Array.isArray(data.topics) ? data.topics : []);
    } catch {
      setTopicsTraction([]);
    } finally {
      setTopicsLoading(false);
    }
  }, [entityFilter]);

  const fetchMentions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ limit: "80", range_days: "14" });
      if (entityFilter.trim()) params.set("entity", entityFilter.trim());
      const res = await fetch(`${getApiBase()}/social/forum-mentions?${params}`);
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
  }, [entityFilter]);

  useEffect(() => {
    fetchMentions();
  }, [fetchMentions]);
  useEffect(() => {
    fetchTopicsTraction();
  }, [fetchTopicsTraction]);

  const bySource = mentions.reduce<Record<string, number>>((acc, m) => {
    const s = m.source_domain || "—";
    acc[s] = (acc[s] || 0) + 1;
    return acc;
  }, {});
  const sourceEntries = Object.entries(bySource).sort((a, b) => b[1] - a[1]).slice(0, 8);

  return (
    <div className="app-page">
      <div className="mx-auto w-full max-w-[var(--ai-max-content)]">
        <h1 className="app-heading mb-2">Forum mentions</h1>
        <p className="app-subheading mb-6">
          Mentions from monitored forums (Traderji, TradingQnA, ValuePickr, etc.). Entity detection runs on ingested forum threads.
        </p>

        <div className="flex flex-wrap items-center gap-4 mb-6">
          <label className="flex items-center gap-2 text-sm text-[var(--ai-text-secondary)]">
            <span>Entity filter</span>
            <input
              type="text"
              value={entityFilter}
              onChange={(e) => setEntityFilter(e.target.value)}
              placeholder="e.g. Zerodha, Sahi"
              className="rounded-lg border border-[var(--ai-border)] bg-[var(--ai-bg)] px-3 py-2 text-sm text-[var(--ai-text)] w-40"
            />
          </label>
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
