"use client";

export interface TopicRow {
  topic: string;
  mentions: number;
}

interface TopicsListProps {
  topics: TopicRow[];
  loading?: boolean;
}

export function TopicsList({ topics, loading }: TopicsListProps) {
  if (loading) {
    return (
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-4 text-zinc-500 text-sm">
        Loading…
      </div>
    );
  }
  if (!topics.length) {
    return (
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-4 text-zinc-500 text-sm">
        No topics in this period
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-4">
      <h3 className="text-sm font-medium text-zinc-300 mb-3">Topics / keywords</h3>
      <div className="flex flex-wrap gap-2">
        {topics.map((t, i) => (
          <span
            key={i}
            className="text-xs px-2 py-1 rounded bg-zinc-700/50 text-zinc-300"
            title={`${t.mentions} mentions`}
          >
            {t.topic}
          </span>
        ))}
      </div>
    </div>
  );
}
