"use client";

interface FirstMention {
  topic: string;
  entity: string;
  first_published_at: string;
  first_title: string;
  first_url: string;
  first_author: string | null;
  first_source_domain: string;
}

interface FirstMentionsSectionProps {
  data: unknown;
  loading: boolean;
}

export function FirstMentionsSection({ data, loading }: FirstMentionsSectionProps) {
  if (loading) {
    return (
      <div className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-8 text-center text-[var(--ai-muted)]">
        Loading first mentions…
      </div>
    );
  }

  const firstMentions = (data && typeof data === "object" && "first_mentions" in data && Array.isArray((data as { first_mentions: FirstMention[] }).first_mentions))
    ? (data as { first_mentions: FirstMention[] }).first_mentions
    : [];
  if (!firstMentions.length) {
    return (
      <div className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-8 text-center text-[var(--ai-muted)]">
        No first mentions found for this period. Ensure topics and entity mentions exist.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)]">
      <table className="min-w-full divide-y divide-[var(--ai-border)]">
        <thead className="bg-[var(--ai-bg-elevated)]">
          <tr>
            <th className="px-4 py-3 text-left text-xs font-medium text-[var(--ai-muted)] uppercase">Topic</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-[var(--ai-muted)] uppercase">Entity</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-[var(--ai-muted)] uppercase">First article</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-[var(--ai-muted)] uppercase">Author</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-[var(--ai-muted)] uppercase">Date</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[var(--ai-border)]">
          {firstMentions.map((m, i) => (
            <tr key={i} className="hover:bg-[var(--ai-surface-hover)]">
              <td className="px-4 py-3 text-sm text-[var(--ai-text)]">{m.topic}</td>
              <td className="px-4 py-3 text-sm text-[var(--ai-text-secondary)]">{m.entity}</td>
              <td className="px-4 py-3">
                <a
                  href={m.first_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm text-[var(--ai-accent)] hover:underline max-w-[280px] truncate block"
                  title={m.first_title}
                >
                  {m.first_title || "Untitled"}
                </a>
                {m.first_source_domain && (
                  <span className="text-xs text-[var(--ai-muted)]">{m.first_source_domain}</span>
                )}
              </td>
              <td className="px-4 py-3 text-sm text-[var(--ai-text-secondary)]">{m.first_author || "—"}</td>
              <td className="px-4 py-3 text-sm text-[var(--ai-muted)]">{m.first_published_at?.slice(0, 10) ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
