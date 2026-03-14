"use client";

interface Article {
  url: string;
  title: string;
  published_at: string;
  entity: string;
  author: string | null;
  source_domain: string;
}

interface TopicRow {
  topic: string;
  article_count: number;
  articles: Article[];
}

interface TopicArticlesSectionProps {
  data: unknown;
  loading: boolean;
}

export function TopicArticlesSection({ data, loading }: TopicArticlesSectionProps) {
  if (loading) {
    return (
      <div className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-8 text-center text-[var(--ai-muted)]">
        Loading topic-article mapping…
      </div>
    );
  }

  const topics = (data && typeof data === "object" && "topics" in data && Array.isArray((data as { topics: TopicRow[] }).topics))
    ? (data as { topics: TopicRow[] }).topics
    : [];
  if (!topics.length) {
    return (
      <div className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-8 text-center text-[var(--ai-muted)]">
        No topics with articles found. Ensure topics are populated (article_topics worker) and mentions exist.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {topics.map((row) => (
        <div
          key={row.topic}
          className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] overflow-hidden"
        >
          <div className="px-4 py-3 border-b border-[var(--ai-border)] flex items-center justify-between">
            <h3 className="font-medium text-[var(--ai-text)]">{row.topic}</h3>
            <span className="text-sm text-[var(--ai-muted)]">{row.article_count} articles</span>
          </div>
          <ul className="divide-y divide-[var(--ai-border)] max-h-[320px] overflow-y-auto">
            {(row.articles ?? []).map((a, i) => (
              <li key={i} className="px-4 py-2.5 hover:bg-[var(--ai-surface-hover)]">
                <a
                  href={a.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm text-[var(--ai-accent)] hover:underline"
                >
                  {a.title || "Untitled"}
                </a>
                <div className="text-xs text-[var(--ai-muted)] mt-0.5 flex flex-wrap gap-x-3 gap-y-0.5">
                  <span>{a.entity}</span>
                  {a.source_domain && <span>{a.source_domain}</span>}
                  {a.author && <span>by {a.author}</span>}
                  {a.published_at && <span>{a.published_at.slice(0, 10)}</span>}
                </div>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
