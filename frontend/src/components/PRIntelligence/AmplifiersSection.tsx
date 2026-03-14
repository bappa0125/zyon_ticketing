"use client";

export interface AmplifiersSectionProps {
  data: unknown;
  loading: boolean;
}

export function AmplifiersSection({ data, loading }: AmplifiersSectionProps) {
  if (loading) {
    return (
      <div className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-8 text-center text-[var(--ai-muted)]">
        Loading amplifiers…
      </div>
    );
  }

  const d = data && typeof data === "object" && "topic" in data ? (data as {
    topic: string;
    first_mention?: { title: string; url: string; author: string | null; source_domain: string; published_at: string } | null;
    amplifiers_by_author?: { author: string; count: number; sample_articles: { title: string; url: string; published_at: string }[] }[];
    amplifiers_by_outlet?: { outlet: string; count: number }[];
  }) : null;
  if (!d) {
    return (
      <div className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-8 text-center text-[var(--ai-muted)]">
        Select a topic and click Analyze to view amplifiers (articles published after the first mention).
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {d.first_mention && (
        <div className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-4">
          <h4 className="text-xs font-medium text-[var(--ai-muted)] uppercase tracking-wider mb-2">First mention</h4>
          <a
            href={d.first_mention.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm text-[var(--ai-accent)] hover:underline"
          >
            {d.first_mention.title || "Untitled"}
          </a>
          <div className="text-xs text-[var(--ai-muted)] mt-1">
            {d.first_mention.source_domain}
            {d.first_mention.author && ` · ${d.first_mention.author}`}
            {` · ${d.first_mention.published_at?.slice(0, 10) ?? ""}`}
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] overflow-hidden">
          <div className="px-4 py-3 border-b border-[var(--ai-border)]">
            <h4 className="font-medium text-[var(--ai-text)]">By author</h4>
            <p className="text-xs text-[var(--ai-muted)]">Amplifiers grouped by journalist</p>
          </div>
          <ul className="divide-y divide-[var(--ai-border)] max-h-[300px] overflow-y-auto">
            {(d.amplifiers_by_author ?? []).map((a, i) => (
              <li key={i} className="px-4 py-2.5">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-[var(--ai-text)]">{a.author}</span>
                  <span className="text-xs text-[var(--ai-muted)]">{a.count} articles</span>
                </div>
                {a.sample_articles?.slice(0, 2).map((s, j) => (
                  <a
                    key={j}
                    href={s.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block text-xs text-[var(--ai-accent)] hover:underline mt-1 truncate"
                  >
                    {s.title}
                  </a>
                ))}
              </li>
            ))}
          </ul>
          {(!d.amplifiers_by_author?.length) && (
            <p className="px-4 py-6 text-sm text-[var(--ai-muted)]">No amplifiers by author</p>
          )}
        </div>

        <div className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] overflow-hidden">
          <div className="px-4 py-3 border-b border-[var(--ai-border)]">
            <h4 className="font-medium text-[var(--ai-text)]">By outlet</h4>
            <p className="text-xs text-[var(--ai-muted)]">Amplifiers grouped by publication</p>
          </div>
          <ul className="divide-y divide-[var(--ai-border)] max-h-[300px] overflow-y-auto">
            {(d.amplifiers_by_outlet ?? []).map((o, i) => (
              <li key={i} className="px-4 py-2.5 flex items-center justify-between">
                <span className="text-sm text-[var(--ai-text)]">{o.outlet}</span>
                <span className="text-xs text-[var(--ai-muted)]">{o.count}</span>
              </li>
            ))}
          </ul>
          {(!d.amplifiers_by_outlet?.length) && (
            <p className="px-4 py-6 text-sm text-[var(--ai-muted)]">No amplifiers by outlet</p>
          )}
        </div>
      </div>
    </div>
  );
}
