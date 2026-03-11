"use client";

export interface CoverageRow {
  entity: string;
  mentions: number;
}

interface ShareOfVoiceChartProps {
  coverage: CoverageRow[];
  loading?: boolean;
  clientName?: string;
}

export function ShareOfVoiceChart({ coverage, loading, clientName }: ShareOfVoiceChartProps) {
  if (loading) {
    return (
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-4 h-40 flex items-center justify-center text-zinc-500 text-sm">
        Loading…
      </div>
    );
  }
  if (!coverage.length) {
    return (
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-4 h-40 flex items-center justify-center text-zinc-500 text-sm">
        No coverage in this period
      </div>
    );
  }

  const total = coverage.reduce((s, c) => s + c.mentions, 0) || 1;
  const isClient = (name: string) =>
    clientName && name.toLowerCase() === clientName.toLowerCase();

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-4">
      <h3 className="text-sm font-medium text-zinc-300 mb-3">Share of voice</h3>
      <div className="space-y-2">
        {coverage.map((c, i) => {
          const pct = total > 0 ? (c.mentions / total) * 100 : 0;
          const isPrimary = isClient(c.entity);
          return (
            <div key={i} className="flex items-center gap-2">
              <span
                className={`text-sm w-28 shrink-0 ${isPrimary ? "text-zinc-100 font-medium" : "text-zinc-400"}`}
              >
                {c.entity}
                {isPrimary && " (client)"}
              </span>
              <div className="flex-1 h-5 rounded bg-zinc-800 overflow-hidden">
                <div
                  className={`h-full rounded ${isPrimary ? "bg-emerald-500" : "bg-zinc-500"}`}
                  style={{ width: `${Math.max(pct, pct > 0 ? 4 : 0)}%` }}
                />
              </div>
              <span className="text-sm text-zinc-400 w-14 text-right">{c.mentions}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
