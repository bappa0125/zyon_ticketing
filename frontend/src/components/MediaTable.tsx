"use client";

export interface MediaArticle {
  title: string;
  source: string;
  url: string;
  entity: string;
  date?: string;
  snippet?: string;
}

interface MediaTableProps {
  articles: MediaArticle[];
  loading?: boolean;
}

export function MediaTable({ articles, loading }: MediaTableProps) {
  if (loading) {
    return (
      <div className="text-center py-12 text-zinc-500">Loading articles…</div>
    );
  }

  if (articles.length === 0) {
    return (
      <div className="text-center py-12 text-zinc-500">
        No articles yet. Run media monitoring to collect news mentions.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-zinc-800">
      <table className="min-w-full divide-y divide-zinc-800">
        <thead className="bg-zinc-900/50">
          <tr>
            <th className="px-4 py-3 text-left text-sm font-medium text-zinc-300">
              Title
            </th>
            <th className="px-4 py-3 text-left text-sm font-medium text-zinc-300">
              Source
            </th>
            <th className="px-4 py-3 text-left text-sm font-medium text-zinc-300">
              Date
            </th>
            <th className="px-4 py-3 text-left text-sm font-medium text-zinc-300">
              Entity
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-800 bg-zinc-900/30">
          {articles.map((a, i) => (
            <tr key={i} className="hover:bg-zinc-800/30">
              <td className="px-4 py-3">
                {a.url ? (
                  <a
                    href={a.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-zinc-200 hover:text-zinc-100 hover:underline"
                  >
                    {a.title || "—"}
                  </a>
                ) : (
                  <span className="text-sm text-zinc-400">{a.title || "—"}</span>
                )}
              </td>
              <td className="px-4 py-3 text-sm text-zinc-400">{a.source || "—"}</td>
              <td className="px-4 py-3 text-sm text-zinc-400">
                {a.date ? new Date(a.date).toLocaleDateString() : "—"}
              </td>
              <td className="px-4 py-3 text-sm text-zinc-400">{a.entity || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
