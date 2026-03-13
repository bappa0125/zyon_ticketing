"use client";

import { useState, useEffect, useCallback } from "react";
import { SocialTable, SocialPost } from "@/components/SocialTable";

import { getApiBase } from "@/lib/api";

/** Animated bar for charts - fills on load */
/** Animated bar for charts - fills on load */
function AnimatedBar({
  value,
  max,
  color = "var(--ai-accent)",
  label,
  delay = 0,
}: {
  value: number;
  max: number;
  color?: string;
  label?: string;
  delay?: number;
}) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div className="flex items-center gap-2">
      {label && <span className="text-sm w-28 shrink-0 truncate text-[var(--ai-text-secondary)]">{label}</span>}
      <div className="flex-1 h-5 rounded-full overflow-hidden bg-[var(--ai-bg-elevated)]">
        <div
          className="h-full rounded-full social-bar-animate"
          style={{
            width: `${Math.max(pct, 4)}%`,
            backgroundColor: color,
            animationDelay: `${delay}ms`,
          }}
        />
      </div>
      <span className="text-xs w-12 text-right text-[var(--ai-muted)]">
        {typeof value === "number" && value >= 1000 ? (value / 1000).toFixed(1) + "k" : value}
      </span>
    </div>
  );
}

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

// YouTube narrative (per-day snapshots from DB)
interface YoutubeNarrativeTheme {
  label: string;
  description: string;
}
interface YoutubeNarrativeSummary {
  date: string;
  narrative: string;
  themes: YoutubeNarrativeTheme[];
  top_channels: string[];
  sentiment_summary: string;
  popularity_score: number;
  generated_at?: string;
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

  const [youtubeNarrative, setYoutubeNarrative] = useState<YoutubeNarrativeSummary[]>([]);
  const [youtubeLoading, setYoutubeLoading] = useState(true);
  const [youtubeRefreshing, setYoutubeRefreshing] = useState(false);
  const [youtubeError, setYoutubeError] = useState<string | null>(null);

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

  const fetchYoutubeNarrative = useCallback(async () => {
    setYoutubeError(null);
    try {
      const res = await fetch(`${getApiBase()}/social/youtube-narrative?limit=30`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setYoutubeNarrative(Array.isArray(data.summaries) ? data.summaries : []);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setYoutubeError(message);
      setYoutubeNarrative([]);
    } finally {
      setYoutubeLoading(false);
      setYoutubeRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchYoutubeNarrative();
  }, [fetchYoutubeNarrative]);

  const handleRefreshYoutubeNarrative = async () => {
    setYoutubeRefreshing(true);
    try {
      const res = await fetch(`${getApiBase()}/social/youtube-narrative/refresh`, { method: "POST" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await fetchYoutubeNarrative();
    } catch (err) {
      console.error("refreshYoutubeNarrative failed:", err);
      setYoutubeRefreshing(false);
    }
  };

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

  const suggestions = strategicBrief?.suggestions ?? [];

  return (
    <div className="app-page">
      <div className="mx-auto w-full max-w-[var(--ai-max-content)]">
        <h1 className="app-heading mb-2">Social</h1>
        <p className="app-subheading mb-6">
          Reddit trending, YouTube narrative, entity mentions. AI-powered insights.
        </p>

        <div className="space-y-8 social-stagger">
        {/* --- Sahi strategic brief --- */}
        <section>
          <div
            className={`app-card p-4 md:p-6 border-[var(--ai-accent)]/30 transition-all duration-500 ${
              suggestions.length && !strategicLoading ? "social-ai-glow" : ""
            }`}
          >
            <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
              <div>
                <h2 className="text-lg font-semibold text-[var(--ai-text)] flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-[var(--ai-accent)] animate-pulse" />
                  Strategic suggestions
                </h2>
                <p className="text-xs text-[var(--ai-muted)]">Reddit + themes + competitors (7d)</p>
              </div>
              <button
                type="button"
                onClick={() => fetchStrategicBrief(true)}
                disabled={strategicLoading}
                className="app-btn-secondary text-sm py-2 px-3"
              >
                {strategicLoading ? "Loading…" : "Refresh"}
              </button>
            </div>
            {strategicLoading ? (
              <div className="grid gap-3 sm:grid-cols-2">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="h-20 rounded-xl social-shimmer-loading" />
                ))}
              </div>
            ) : strategicError ? (
              <div className="rounded-xl border border-[var(--ai-danger)]/50 bg-[var(--ai-danger)]/10 px-4 py-3 text-sm text-[var(--ai-danger)]">
                {strategicError}
              </div>
            ) : suggestions.length ? (
              <ul className="space-y-3 social-stagger">
                {suggestions.map((s, i) => (
                  <li
                    key={i}
                    className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-bg-elevated)] p-3 hover:border-[var(--ai-accent)]/30 transition-colors"
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-[var(--ai-accent)] text-sm font-medium">{i + 1}</span>
                      <span className="font-medium text-[var(--ai-text)] line-clamp-1">{s.title}</span>
                      {s.action_type && (
                        <span className="text-xs px-2 py-0.5 rounded-full bg-[var(--ai-accent-dim)] text-[var(--ai-accent)] shrink-0">
                          {s.action_type}
                        </span>
                      )}
                    </div>
                    {s.rationale && (
                      <p className="text-xs text-[var(--ai-muted)] mt-1.5 line-clamp-2">{s.rationale}</p>
                    )}
                    <div className="mt-2 h-1 rounded-full overflow-hidden bg-[var(--ai-bg)]">
                      <div
                        className="h-full rounded-full social-bar-animate"
                        style={{
                          width: `${Math.max(20, 100 - i * 15)}%`,
                          backgroundColor: "var(--ai-accent)",
                          animationDelay: `${i * 80}ms`,
                        }}
                      />
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-bg-elevated)] py-8 text-center text-sm text-[var(--ai-muted)]">
                No suggestions yet. Run Reddit pipeline.
              </div>
            )}
          </div>
        </section>

        {/* --- Reddit trending --- */}
        <section>
          <div className="app-card p-4 md:p-6 mb-4">
            <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
              <h2 className="text-lg font-semibold text-[var(--ai-text)] flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-[#ff4500]" />
                Reddit trending
              </h2>
              <button
                type="button"
                onClick={handleRefreshRedditTrending}
                disabled={redditRefreshing}
                className="app-btn-secondary text-sm py-2 px-3"
              >
                {redditRefreshing ? "Refreshing…" : "Refresh"}
              </button>
            </div>

            {redditLoading ? (
              <div className="space-y-4">
                <div className="h-32 rounded-xl social-shimmer-loading" />
                <div className="h-48 rounded-xl social-shimmer-loading" />
              </div>
            ) : (
              <>
                {redditError && (
                  <div className="mb-4 rounded-xl border border-[var(--ai-danger)] bg-[var(--ai-danger)]/10 px-4 py-3 text-sm text-[var(--ai-danger)]">
                    {redditError}
                  </div>
                )}
                {!redditError && redditTrending && (
                  <>
                    {/* Themes bar chart */}
                    {(redditTrending.themes?.length ?? 0) > 0 && (
                      <div className="mb-6">
                        <h3 className="text-xs font-medium text-[var(--ai-muted)] uppercase tracking-wider mb-3">
                          Themes
                        </h3>
                        <div className="space-y-2">
                          {redditTrending.themes.map((t, i) => (
                            <AnimatedBar
                              key={i}
                              value={10 - i}
                              max={10}
                              color="#ff4500"
                              label={t.label}
                              delay={i * 60}
                            />
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Sahi topics - compact with bars */}
                    {(redditTrending.sahi_suggestions?.length ?? 0) > 0 && (
                      <div className="mb-6">
                        <h3 className="text-xs font-medium text-[var(--ai-muted)] uppercase tracking-wider mb-3">
                          Sahi topics
                        </h3>
                        <div className="space-y-2">
                          {redditTrending.sahi_suggestions.map((s, i) => (
                            <div
                              key={i}
                              className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-bg-elevated)] p-2.5 hover:border-[var(--ai-accent)]/20 transition-colors"
                            >
                              <div className="flex items-center gap-2">
                                <span className="font-medium text-sm text-[var(--ai-text)] line-clamp-1 flex-1">
                                  {s.title}
                                </span>
                              </div>
                              <p className="text-xs text-[var(--ai-muted)] line-clamp-1 mt-0.5">{s.rationale}</p>
                              <div className="mt-1.5 h-1 rounded-full overflow-hidden bg-[var(--ai-bg)]">
                                <div
                                  className="h-full rounded-full social-bar-animate"
                                  style={{
                                    width: `${70 + (i % 3) * 10}%`,
                                    backgroundColor: "var(--ai-accent)",
                                    animationDelay: `${(i + 3) * 50}ms`,
                                  }}
                                />
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Posts table */}
                    <div className="mb-4">
                      <h3 className="text-xs font-medium text-[var(--ai-muted)] uppercase tracking-wider mb-3">
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
              </>
            )}
          </div>
        </section>

        {/* --- YouTube narrative --- */}
        <section>
          <div className="app-card p-4 md:p-6">
            <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
              <h2 className="text-lg font-semibold text-[var(--ai-text)] flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-[#ff0000]" />
                YouTube narrative
              </h2>
              <button
                type="button"
                onClick={handleRefreshYoutubeNarrative}
                disabled={youtubeRefreshing}
                className="app-btn-secondary text-sm py-2 px-3"
              >
                {youtubeRefreshing ? "Running…" : "Refresh"}
              </button>
            </div>

            {youtubeLoading ? (
              <div className="space-y-3">
                <div className="h-24 rounded-xl social-shimmer-loading" />
                <div className="h-40 rounded-xl social-shimmer-loading" />
              </div>
            ) : (
              <>
                {youtubeError && (
                  <div className="mb-4 rounded-xl border border-[var(--ai-danger)] bg-[var(--ai-danger)]/10 px-4 py-3 text-sm text-[var(--ai-danger)]">
                    Could not load: {youtubeError}. Set YOUTUBE_API_KEY and run pipeline.
                  </div>
                )}
                {!youtubeError && youtubeNarrative.length === 0 && (
                  <div className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-bg-elevated)] py-10 text-center text-sm text-[var(--ai-muted)]">
                    No data yet. Run refresh (YOUTUBE_API_KEY).
                  </div>
                )}
                {!youtubeError && youtubeNarrative.length > 0 && (
                  <div className="space-y-4">
                    {/* Popularity bar chart */}
                    <div>
                      <h3 className="text-xs font-medium text-[var(--ai-muted)] uppercase tracking-wider mb-3">
                        Daily popularity
                      </h3>
                      <div className="space-y-2 mb-4">
                        {youtubeNarrative.slice(0, 7).map((row, i) => {
                          const maxPop = Math.max(...youtubeNarrative.map((r) => r.popularity_score ?? 0), 0.01);
                          const pct = ((row.popularity_score ?? 0) / maxPop) * 100;
                          return (
                            <AnimatedBar
                              key={row.date}
                              value={Math.round((row.popularity_score ?? 0) * 100) / 100}
                              max={maxPop}
                              color="#ff0000"
                              label={row.date}
                              delay={i * 70}
                            />
                          );
                        })}
                      </div>
                    </div>
                    <div className="overflow-x-auto rounded-xl border border-[var(--ai-border)]">
                    <table className="min-w-full divide-y divide-[var(--ai-border)]">
                      <thead className="bg-[var(--ai-surface)]">
                        <tr>
                          <th className="px-4 py-3 text-left text-xs font-medium text-[var(--ai-text-secondary)]">
                            Date
                          </th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-[var(--ai-text-secondary)]">
                            Narrative
                          </th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-[var(--ai-text-secondary)]">
                            Sentiment
                          </th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-[var(--ai-text-secondary)]">
                            Themes
                          </th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-[var(--ai-text-secondary)]">
                            Top channels
                          </th>
                          <th className="px-4 py-3 text-right text-xs font-medium text-[var(--ai-text-secondary)]">
                            Popularity
                          </th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[var(--ai-border)] bg-[var(--ai-bg-elevated)]">
                        {youtubeNarrative.map((row) => (
                          <tr key={row.date} className="hover:bg-[var(--ai-surface)]">
                            <td className="px-4 py-3 text-sm font-medium text-[var(--ai-text)] whitespace-nowrap">
                              {row.date}
                            </td>
                            <td className="px-4 py-3 text-sm text-[var(--ai-text)] max-w-xs">
                              <span className="line-clamp-3">{row.narrative || "—"}</span>
                            </td>
                            <td className="px-4 py-3 text-sm text-[var(--ai-muted)] max-w-[180px]">
                              <span className="line-clamp-2">{row.sentiment_summary || "—"}</span>
                            </td>
                            <td className="px-4 py-3 text-sm text-[var(--ai-text)] max-w-[200px]">
                              {row.themes?.length ? (
                                <span className="line-clamp-3">
                                  {row.themes.map((t) => t.label).join(", ")}
                                </span>
                              ) : (
                                "—"
                              )}
                            </td>
                            <td className="px-4 py-3 text-sm text-[var(--ai-muted)] max-w-[160px]">
                              {row.top_channels?.length ? (
                                <span className="line-clamp-2">
                                  {row.top_channels.slice(0, 3).join(", ")}
                                  {row.top_channels.length > 3 ? "…" : ""}
                                </span>
                              ) : (
                                "—"
                              )}
                            </td>
                            <td className="px-4 py-3 text-sm text-[var(--ai-text-secondary)] text-right whitespace-nowrap">
                              {row.popularity_score != null
                                ? row.popularity_score.toFixed(2)
                                : "—"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </section>

        {/* --- Latest social mentions --- */}
        <section>
          <div className="app-card p-4 md:p-6">
            <div className="flex flex-wrap items-center gap-3 mb-4">
              <h2 className="text-lg font-semibold text-[var(--ai-text)] flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-[var(--ai-accent)]" />
                Social mentions
              </h2>
              <input
                type="text"
                placeholder="Filter by entity"
                value={entityFilter}
                onChange={(e) => setEntityFilter(e.target.value)}
                className="app-input w-36 text-sm py-2"
              />
            </div>
            {loading ? (
              <div className="h-48 rounded-xl social-shimmer-loading" />
            ) : (
              <SocialTable posts={posts} loading={false} />
            )}
          </div>
        </section>
        </div>
      </div>
    </div>
  );
}
