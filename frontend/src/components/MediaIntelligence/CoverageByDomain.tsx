"use client";

export interface DomainRow {
  domain: string;
  name: string;
  total: number;
  entities: Record<string, number>;
}

interface CoverageByDomainProps {
  byDomain: DomainRow[];
  entities: string[];
  clientName: string;
  loading?: boolean;
  onSelectDomain?: (domain: string | null) => void;
  selectedDomain?: string | null;
}

export function CoverageByDomain({
  byDomain,
  entities,
  clientName,
  loading,
  onSelectDomain,
  selectedDomain,
}: CoverageByDomainProps) {
  if (loading) {
    return (
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-4">
        <h3 className="text-sm font-medium text-zinc-300 mb-3">Coverage by source</h3>
        <div className="text-sm text-zinc-500">Loading…</div>
      </div>
    );
  }
  if (!byDomain?.length) {
    return (
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-4">
        <h3 className="text-sm font-medium text-zinc-300 mb-3">Coverage by source</h3>
        <div className="text-sm text-zinc-500">No source breakdown yet.</div>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-4">
      <h3 className="text-sm font-medium text-zinc-300 mb-3">Coverage by source</h3>
      <p className="text-xs text-zinc-500 mb-2">Articles per domain (from media sources). Click to filter feed.</p>
      <div className="overflow-x-auto max-h-64 overflow-y-auto">
        <table className="min-w-full text-sm">
          <thead className="sticky top-0 bg-zinc-900/95">
            <tr>
              <th className="text-left py-2 pr-2 text-zinc-400 font-medium">Source</th>
              <th className="text-right py-2 px-1 text-zinc-400 font-medium">Total</th>
              <th className="text-right py-2 px-1 text-zinc-400 font-medium">{clientName}</th>
              <th className="text-right py-2 pl-1 text-zinc-400 font-medium">Others</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800">
            {byDomain.map((row) => {
              const clientCount = row.entities[clientName] ?? 0;
              const othersCount = row.total - clientCount;
              const isSelected = selectedDomain === row.domain;
              return (
                <tr
                  key={row.domain}
                  className={`cursor-pointer hover:bg-zinc-800/50 ${isSelected ? "bg-zinc-700/50" : ""}`}
                  onClick={() => onSelectDomain?.(isSelected ? null : row.domain)}
                >
                  <td className="py-1.5 pr-2 text-zinc-200 truncate max-w-[140px]" title={row.domain}>
                    {row.name || row.domain}
                  </td>
                  <td className="text-right py-1.5 px-1 text-zinc-400">{row.total}</td>
                  <td className="text-right py-1.5 px-1 text-emerald-400">{clientCount}</td>
                  <td className="text-right py-1.5 pl-1 text-zinc-400">{othersCount}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
