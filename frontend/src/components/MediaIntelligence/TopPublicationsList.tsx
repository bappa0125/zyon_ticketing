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
  const panelClass = "rounded-2xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-4 text-sm text-[var(--ai-muted)]";
  if (loading) return <div className={panelClass}>Loading…</div>;
  if (!items.length) return <div className={panelClass}>No publications in this period</div>;

  return (
    <div className="rounded-2xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-4">
      <h3 className="text-sm font-semibold text-[var(--ai-text)] mb-3">Top publications</h3>
      <ul className="space-y-2">
        {items.map((p, i) => (
          <li key={i} className="flex justify-between text-sm">
            <span className="text-[var(--ai-text)] truncate pr-2">{p.source || "Unknown"}</span>
            <span className="text-[var(--ai-muted)] shrink-0">{p.mentions} mentions</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
