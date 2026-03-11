"use client";

import { getEntityHex } from "@/lib/entityColors";

export interface CoverageRow {
  entity: string;
  mentions: number;
}

interface CoverageChartProps {
  coverage: CoverageRow[];
  loading?: boolean;
}

export function CoverageChart({ coverage, loading }: CoverageChartProps) {
  if (loading) {
    return (
      <div className="text-center py-12 text-zinc-500">Loading coverage…</div>
    );
  }

  if (coverage.length === 0) {
    return (
      <div className="text-center py-12 text-zinc-500">
        No coverage data yet. Select a client or run media monitoring.
      </div>
    );
  }

  const maxMentions = Math.max(...coverage.map((c) => c.mentions), 1);

  return (
    <div className="space-y-4">
      {coverage.map((c, i) => {
        const pct = maxMentions > 0 ? (c.mentions / maxMentions) * 100 : 0;
        const colorHex = getEntityHex(c.entity);
        return (
          <div key={i} className="rounded-lg border border-zinc-800 p-4 bg-zinc-900/30">
            <div className="flex items-center justify-between gap-4 mb-2">
              <div className="flex items-center gap-2">
                <span
                  className="w-2 h-2 rounded-full shrink-0"
                  style={{ backgroundColor: colorHex }}
                />
                <span className="text-sm font-medium text-zinc-200">{c.entity}</span>
              </div>
              <span className="text-sm text-zinc-400">{c.mentions} mentions</span>
            </div>
            <div className="h-4 rounded bg-zinc-800 overflow-hidden">
              <div
                className="h-full rounded"
                style={{ width: `${pct}%`, minWidth: c.mentions > 0 ? "4px" : 0, backgroundColor: colorHex }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
