"use client";

import { useState, useEffect, useCallback } from "react";
import { SocialTable, SocialPost } from "@/components/SocialTable";

import { getApiBase } from "@/lib/api";

// Reddit trending pipeline types (separate from social_posts)
interface RedditTrendingPost {
  subreddit: string;
  title: string;
  body_snippet?: string;
  url: string;
  score: number;
  num_comments: number;
  created_utc?: string;
}

interface RedditTheme {
  label: string;
  description: string;
}

interface SahiSuggestion {
  title: string;
  rationale: string;
}

interface RedditTrendingData {
  posts: RedditTrendingPost[];
  themes: RedditTheme[];
  sahi_suggestions: SahiSuggestion[];
  pipeline?: string;
}

// Sahi strategic brief (1–2 suggestions from themes, mentions, topics, competitors)
interface StrategicSuggestion {
  title: string;
  rationale: string;
  action_type?: string;
}
interface SahiStrategicBrief {
  client: string;
  range: string;
  generated_at?: string;
  suggestions: StrategicSuggestion[];
}

export default function SocialPage() {
  const [posts, setPosts] = useState<SocialPost[]>([]);
  const [loading, setLoading] = useState(true);
  const [entityFilter, setEntityFilter] = useState<string>("");

  const [strategicBrief, setStrategicBrief] = useState<SahiStrategicBrief | null>(null);
  const [strategicLoading, setStrategicLoading] = useState(true);
  const [strategicError, setStrategicError] = useState<string | null>(null);

  const [redditTrending, setRedditTrending] = useState<RedditTrendingData | null>(null);
  const [redditLoading, setRedditLoading] = useState(true);
  const [redditRefreshing, setRedditRefreshing] = useState(false);
  const [redditError, setRedditError] = useState<string | null>(null);

  const fetchRedditTrending = useCallback(async () => {
    setRedditError(null);
    const url = `${getApiBase()}/social/reddit-trending?limit=80`;
    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const contentType = res.headers.get("content-type") ?? "";
      if (!contentType.includes("application/json")) {
        throw new Error("Response was not JSON (check API proxy)");
      }
      const data: RedditTrendingData = await res.json();
      setRedditTrending({
        posts: Array.isArray(data.posts) ? data.posts : [],
        themes: Array.isArray(data.themes) ? data.themes : [],
        sahi_suggestions: Array.isArray(data.sahi_suggestions) ? data.sahi_suggestions : [],
        pipeline: data.pipeline,
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      console.error("fetchRedditTrending failed:", err);
      setRedditError(message);
      setRedditTrending({ posts: [], themes: [], sahi_suggestions: [] });
    } finally {
      setRedditLoading(false);
      setRedditRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchRedditTrending();
  }, [fetchRedditTrending]);

  const fetchStrategicBrief = useCallback(async (bypassCache = false) => {
    setStrategicError(null);
    setStrategicLoading(true);
    try {
      const res = await fetch(
        `${getApiBase()}/social/sahi-strategic-brief?use_cache=${bypassCache ? "false" : "true"}`
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: SahiStrategicBrief = await res.json();
      setStrategicBrief(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      console.error("fetchStrategicBrief failed:", err);
      setStrategicError(message);
      setStrategicBrief(null);
    } finally {
      setStrategicLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStrategicBrief(false);
  }, [fetchStrategicBrief]);

  const handleRefreshRedditTrending = async () => {
    setRedditRefreshing(true);
    try {
      const res = await fetch(`${getApiBase()}/social/reddit-trending/refresh`, { method: "POST" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await fetchRedditTrending();
    } catch (err) {
      console.error("refreshRedditTrending failed:", err);
      setRedditRefreshing(false);
    }
  };

  useEffect(() => {
    async function fetchPosts() {
      try {
        const url = entityFilter
          ? `${getApiBase()}/social/latest?entity=${encodeURIComponent(entityFilter)}`
          : `${getApiBase()}/social/latest`;
        const res = await fetch(url);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        setPosts(data.posts ?? []);
      } catch (err) {
        console.error("fetchPosts failed:", err);
        setPosts([]);
      } finally {
        setLoading(false);
      }
    }
    fetchPosts();
  }, [entityFilter]);

  return (
    <div className="app-page">
      <div className="mx-auto w-full max-w-[var(--ai-max-content)]">
        <h1 className="app-heading mb-2">Social</h1>
        <p className="app-subheading mb-6">
          Reddit trending (India & global investing) and latest entity-based social mentions.
        </p>

        {/* --- Sahi strategic brief (top of page) --- */}
        <section className="mb-8">
          <div className="app-card p-4 md:p-6 border-[var(--ai-accent)]/30">
            <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
              <div>
                <h2 className="text-lg font-semibold text-[var(--ai-text)] mb-1">
                  Strategic suggestions for Sahi
                </h2>
                <p className="text-sm text-[var(--ai-text-secondary)]">
                  Based on Reddit themes, Sahi&apos;s mentions, trending topics, and competitor context (last 7 days).
                </p>
              </div>
              <button
                type="button"
                onClick={() => fetchStrategicBrief(true)}
                disabled={strategicLoading}
                className="app-btn-secondary text-sm py-2 px-3"
              >
                {strategicLoading ? "Loading…" : "Refresh brief"}
              </button>
            </div>
            {strategicLoading ? (
              <div className="text-center py-6 text-[var(--ai-muted)]">Loading strategic brief…</div>
            ) : strategicError ? (
              <div className="rounded-xl border border-[var(--ai-danger)]/50 bg-[var(--ai-danger)]/10 px-4 py-3 text-sm text-[var(--ai-danger)]">
                Could not load: {strategicError}
              </div>
            ) : strategicBrief?.suggestions?.length ? (
              <ul className="space-y-4">
                {strategicBrief.suggestions.map((s, i) => (
                  <li
                    key={i}
                    className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-bg-elevated)] p-4"
                  >
                    <div className="font-medium text-[var(--ai-text)] flex items-center gap-2">
                      <span className="text-[var(--ai-accent)]">{(i + 1)}.</span>
                      {s.title}
                      {s.action_type && (
                        <span className="text-xs px-2 py-0.5 rounded bg-[var(--ai-accent-dim)] text-[var(--ai-accent)]">
                          {s.action_type}
                        </span>
                      )}
                    </div>
                    {s.rationale && (
                      <p className="text-sm text-[var(--ai-muted)] mt-2">{s.rationale}</p>
                    )}
                  </li>
                ))}
              </ul>
            ) : (
              <div className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-bg-elevated)] py-6 text-center text-[var(--ai-muted)]">
                No strategic suggestions yet. Ensure Reddit trending has run and entity data exists.
              </div>
            )}
          </div>
        </section>

        {/* --- Reddit trending (separate pipeline) --- */}
        <section className="mb-10">
          <div className="app-card p-4 md:p-6 mb-4">
            <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
              <h2 className="text-lg font-semibold text-[var(--ai-text)]">
                Trending on Reddit — India & global trading/investing
              </h2>
              <button
                type="button"
                onClick={handleRefreshRedditTrending}
                disabled={redditRefreshing}
                className="app-btn-secondary text-sm py-2 px-3"
              >
                {redditRefreshing ? "Refreshing…" : "Refresh pipeline"}
              </button>
            </div>
            <p className="text-sm text-[var(--ai-text-secondary)] mb-4">
              Hot discussions from r/IndianStreetBets, r/IndiaInvestments, r/stocks, r/investing, and
              more. Themes and Sahi content ideas are generated by AI (free tier).
            </p>

            {redditLoading ? (
              <div className="text-center py-10 text-[var(--ai-muted)]">Loading Reddit trending…</div>
            ) : (
              <>
                {redditError && (
                  <div className="mb-4 rounded-xl border border-[var(--ai-danger)] bg-[var(--ai-danger)]/10 px-4 py-3 text-sm text-[var(--ai-danger)]">
                    Could not load Reddit data: {redditError}. Ensure the backend is running and /api proxies to it.
                  </div>
                )}
                {!redditError && redditTrending && (
                  <p className="mb-4 text-sm text-[var(--ai-text-secondary)]">
                    Loaded: {redditTrending.posts.length} posts, {redditTrending.themes.length} themes, {redditTrending.sahi_suggestions.length} Sahi suggestions.
                  </p>
                )}
                {/* Themes */}
                {(redditTrending?.themes?.length ?? 0) > 0 && (
                  <div className="mb-6">
                    <h3 className="text-sm font-medium text-[var(--ai-text-secondary)] mb-2">
                      Themes in the discussion
                    </h3>
                    <div className="grid gap-3 sm:grid-cols-2">
                      {redditTrending!.themes.map((t, i) => (
                        <div
                          key={i}
                          className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-bg-elevated)] p-3"
                        >
                          <div className="font-medium text-[var(--ai-text)]">{t.label}</div>
                          <div className="text-sm text-[var(--ai-muted)] mt-1">{t.description}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Sahi suggestions */}
                {(redditTrending?.sahi_suggestions?.length ?? 0) > 0 && (
                  <div className="mb-6">
                    <h3 className="text-sm font-medium text-[var(--ai-text-secondary)] mb-2">
                      Topics Sahi should talk about
                    </h3>
                    <div className="grid gap-3 sm:grid-cols-2">
                      {redditTrending!.sahi_suggestions.map((s, i) => (
                        <div
                          key={i}
                          className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-bg-elevated)] p-3"
                        >
                          <div className="font-medium text-[var(--ai-text)]">{s.title}</div>
                          <div className="text-sm text-[var(--ai-muted)] mt-1">{s.rationale}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Trending posts table */}
                <div className="mb-4">
                  <h3 className="text-sm font-medium text-[var(--ai-text-secondary)] mb-2">
                    Recent posts
                  </h3>
                  {(redditTrending?.posts?.length ?? 0) === 0 ? (
                    <div className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-bg-elevated)] py-10 text-center text-[var(--ai-muted)]">
                      No Reddit trending data yet. Click &quot;Refresh pipeline&quot; to run the pipeline.
                    </div>
                  ) : (
                    <div className="overflow-x-auto rounded-xl border border-[var(--ai-border)]">
                      <table className="min-w-full divide-y divide-[var(--ai-border)]">
                        <thead className="bg-[var(--ai-surface)]">
                          <tr>
                            <th className="px-4 py-3 text-left text-xs font-medium text-[var(--ai-text-secondary)]">
                              Subreddit
                            </th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-[var(--ai-text-secondary)]">
                              Title
                            </th>
                            <th className="px-4 py-3 text-right text-xs font-medium text-[var(--ai-text-secondary)]">
                              Score
                            </th>
                            <th className="px-4 py-3 text-right text-xs font-medium text-[var(--ai-text-secondary)]">
                              Comments
                            </th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-[var(--ai-border)] bg-[var(--ai-bg-elevated)]">
                          {redditTrending!.posts.slice(0, 30).map((p, i) => (
                            <tr key={i} className="hover:bg-[var(--ai-surface)]">
                              <td className="px-4 py-3 text-sm text-[var(--ai-text-secondary)]">
                                r/{p.subreddit}
                              </td>
                              <td className="px-4 py-3 max-w-md">
                                {p.url ? (
                                  <a
                                    href={p.url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="text-sm text-[var(--ai-accent)] hover:underline line-clamp-2"
                                  >
                                    {p.title || "—"}
                                  </a>
                                ) : (
                                  <span className="text-sm text-[var(--ai-text)] line-clamp-2">
                                    {p.title || "—"}
                                  </span>
                                )}
                              </td>
                              <td className="px-4 py-3 text-sm text-[var(--ai-text-secondary)] text-right">
                                {p.score ?? "—"}
                              </td>
                              <td className="px-4 py-3 text-sm text-[var(--ai-text-secondary)] text-right">
                                {p.num_comments ?? "—"}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        </section>

        {/* --- Latest social mentions (Apify / social_posts) --- */}
        <section>
          <div className="app-card p-4 md:p-6">
            <h2 className="text-lg font-semibold text-[var(--ai-text)] mb-2">
              Latest social mentions
            </h2>
            <p className="text-sm text-[var(--ai-text-secondary)] mb-4">
              Entity-based mentions (Twitter, YouTube, Reddit via Apify). Filter by entity:
            </p>
            <input
              type="text"
              placeholder="Entity (e.g. Sahi)"
              value={entityFilter}
              onChange={(e) => setEntityFilter(e.target.value)}
              className="app-input mb-4 w-48"
            />
            <SocialTable posts={posts} loading={loading} />
          </div>
        </section>
      </div>
    </div>
  );
}
