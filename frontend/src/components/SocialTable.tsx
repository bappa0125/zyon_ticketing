"use client";

export interface SocialPost {
  platform: string;
  entity: string;
  text: string;
  engagement?: { likes?: number; retweets?: number; comments?: number };
  url?: string;
  date?: string;
}

interface SocialTableProps {
  posts: SocialPost[];
  loading?: boolean;
}

function formatEngagement(e: SocialPost["engagement"]) {
  if (!e) return "—";
  const parts: string[] = [];
  if (e.likes) parts.push(`❤ ${e.likes}`);
  if (e.retweets) parts.push(`↻ ${e.retweets}`);
  if (e.comments) parts.push(`💬 ${e.comments}`);
  return parts.length ? parts.join(" ") : "—";
}

export function SocialTable({ posts, loading }: SocialTableProps) {
  if (loading) {
    return (
      <div className="text-center py-12 text-[var(--ai-muted)]">Loading social mentions…</div>
    );
  }

  if (posts.length === 0) {
    return (
      <div className="text-center py-12 text-[var(--ai-muted)]">
        No social mentions yet. Set APIFY_API_KEY and run social monitoring.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-[var(--ai-border)]">
      <table className="min-w-full divide-y divide-[var(--ai-border)]">
        <thead className="bg-[var(--ai-surface)]">
          <tr>
            <th className="px-4 py-3 text-left text-sm font-medium text-[var(--ai-text-secondary)]">
              Platform
            </th>
            <th className="px-4 py-3 text-left text-sm font-medium text-[var(--ai-text-secondary)]">
              Entity
            </th>
            <th className="px-4 py-3 text-left text-sm font-medium text-[var(--ai-text-secondary)]">
              Text
            </th>
            <th className="px-4 py-3 text-left text-sm font-medium text-[var(--ai-text-secondary)]">
              Engagement
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[var(--ai-border)] bg-[var(--ai-bg-elevated)]">
          {posts.map((p, i) => (
            <tr key={i} className="hover:bg-[var(--ai-surface)]">
              <td className="px-4 py-3 text-sm text-[var(--ai-text-secondary)]">{p.platform || "—"}</td>
              <td className="px-4 py-3 text-sm text-[var(--ai-text-secondary)]">{p.entity || "—"}</td>
              <td className="px-4 py-3 max-w-md">
                {p.url ? (
                  <a
                    href={p.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-[var(--ai-accent)] hover:underline line-clamp-2"
                  >
                    {p.text || "—"}
                  </a>
                ) : (
                  <span className="text-sm text-[var(--ai-text)] line-clamp-2">{p.text || "—"}</span>
                )}
              </td>
              <td className="px-4 py-3 text-sm text-[var(--ai-text-secondary)]">
                {formatEngagement(p.engagement)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
