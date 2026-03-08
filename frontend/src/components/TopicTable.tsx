"use client";

export interface TopicRow {
  topic: string;
  mentions: number;
}

interface TopicTableProps {
  topics: TopicRow[];
  loading?: boolean;
}

export function TopicTable({ topics, loading }: TopicTableProps) {
  if (loading) {
    return (
      <div className="text-center py-12 text-zinc-500">Loading topics…</div>
    );
  }

  if (topics.length === 0) {
    return (
      <div className="text-center py-12 text-zinc-500">
        No topics yet. Run media monitoring and topic detection.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-zinc-800">
      <table className="min-w-full divide-y divide-zinc-800">
        <thead className="bg-zinc-900/50">
          <tr>
            <th className="px-4 py-3 text-left text-sm font-medium text-zinc-300">
              Topic
            </th>
            <th className="px-4 py-3 text-left text-sm font-medium text-zinc-300">
              Mentions
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-800 bg-zinc-900/30">
          {topics.map((t, i) => (
            <tr key={i} className="hover:bg-zinc-800/30">
              <td className="px-4 py-3 text-sm text-zinc-200">{t.topic || "—"}</td>
              <td className="px-4 py-3 text-sm text-zinc-400">{t.mentions}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
