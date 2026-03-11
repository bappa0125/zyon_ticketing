"use client";

export interface PubRow {
  source: string;
  mentions: number;
}

interface TopPublicationsListProps {
  items: PubRow[];
  loading?: boolean;
}

export function TopPublicationsList({ items, loading }: TopPublicationsListProps) {
  if (loading) {
    return (
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-4 text-zinc-500 text-sm">
        Loading…
      </div>
    );
  }
  if (!items.length) {
    return (
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-4 text-zinc-500 text-sm">
        No publications in this period
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-4">
      <h3 className="text-sm font-medium text-zinc-300 mb-3">Top publications</h3>
      <ul className="space-y-2">
        {items.map((p, i) => (
          <li key={i} className="flex justify-between text-sm">
            <span className="text-zinc-300 truncate pr-2">{p.source || "Unknown"}</span>
            <span className="text-zinc-500 shrink-0">{p.mentions} mentions</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
