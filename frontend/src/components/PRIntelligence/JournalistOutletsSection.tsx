"use client";

interface JournalistOutletsSectionProps {
  data: unknown;
  loading: boolean;
}

export function JournalistOutletsSection({ data, loading }: JournalistOutletsSectionProps) {
  if (loading) {
    return (
      <div className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-8 text-center text-[var(--ai-muted)]">
        Loading journalist-outlet index…
      </div>
    );
  }

  const journalists = (data && typeof data === "object" && "journalists" in data && Array.isArray((data as { journalists: { author: string; outlets: string[]; article_count: number }[] }).journalists))
    ? (data as { journalists: { author: string; outlets: string[]; article_count: number }[] }).journalists
    : [];
  if (!journalists.length) {
    return (
      <div className="rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-8 text-center text-[var(--ai-muted)]">
        No journalist-outlet mappings. Authors are populated from article_documents and entity_mentions.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)]">
      <table className="min-w-full divide-y divide-[var(--ai-border)]">
        <thead className="bg-[var(--ai-bg-elevated)]">
          <tr>
            <th className="px-4 py-3 text-left text-xs font-medium text-[var(--ai-muted)] uppercase">Journalist</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-[var(--ai-muted)] uppercase">Outlets</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-[var(--ai-muted)] uppercase">Articles</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[var(--ai-border)]">
          {journalists.map((j, i) => (
            <tr key={i} className="hover:bg-[var(--ai-surface-hover)]">
              <td className="px-4 py-3 text-sm font-medium text-[var(--ai-text)]">{j.author}</td>
              <td className="px-4 py-3 text-sm text-[var(--ai-text-secondary)]">
                {(j.outlets ?? []).join(", ") || "—"}
              </td>
              <td className="px-4 py-3 text-sm text-[var(--ai-muted)]">{j.article_count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
