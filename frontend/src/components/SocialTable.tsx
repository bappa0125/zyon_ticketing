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
      <div className="text-center py-12 text-zinc-500">Loading social mentions…</div>
    );
  }

  if (posts.length === 0) {
    return (
      <div className="text-center py-12 text-zinc-500">
        No social mentions yet. Set APIFY_API_KEY and run social monitoring.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-zinc-800">
      <table className="min-w-full divide-y divide-zinc-800">
        <thead className="bg-zinc-900/50">
          <tr>
            <th className="px-4 py-3 text-left text-sm font-medium text-zinc-300">
              Platform
            </th>
            <th className="px-4 py-3 text-left text-sm font-medium text-zinc-300">
              Entity
            </th>
            <th className="px-4 py-3 text-left text-sm font-medium text-zinc-300">
              Text
            </th>
            <th className="px-4 py-3 text-left text-sm font-medium text-zinc-300">
              Engagement
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-800 bg-zinc-900/30">
          {posts.map((p, i) => (
            <tr key={i} className="hover:bg-zinc-800/30">
              <td className="px-4 py-3 text-sm text-zinc-400">{p.platform || "—"}</td>
              <td className="px-4 py-3 text-sm text-zinc-400">{p.entity || "—"}</td>
              <td className="px-4 py-3 max-w-md">
                {p.url ? (
                  <a
                    href={p.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-zinc-200 hover:text-zinc-100 hover:underline line-clamp-2"
                  >
                    {p.text || "—"}
                  </a>
                ) : (
                  <span className="text-sm text-zinc-300 line-clamp-2">{p.text || "—"}</span>
                )}
              </td>
              <td className="px-4 py-3 text-sm text-zinc-400">
                {formatEngagement(p.engagement)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
