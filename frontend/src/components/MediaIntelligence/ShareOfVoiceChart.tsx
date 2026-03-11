"use client";

import { getEntityHex } from "@/lib/entityColors";

export interface CoverageRow {
  entity: string;
  mentions: number;
}

interface ShareOfVoiceChartProps {
  coverage: CoverageRow[];
  loading?: boolean;
  clientName?: string;
}

function isClientMatch(name: string, clientName: string | undefined): boolean {
  if (!clientName) return false;
  return name.toLowerCase() === clientName.toLowerCase();
}

function BarItem({
  entity,
  mentions,
  total,
  clientName,
}: {
  entity: string;
  mentions: number;
  total: number;
  clientName?: string;
}) {
  const pct = total > 0 ? (mentions / total) * 100 : 0;
  const widthPct = pct > 0 ? Math.max(pct, 4) : 0;
  const isPrimary = isClientMatch(entity, clientName);
  const colorHex = getEntityHex(entity);
  const spanClass = isPrimary ? "text-zinc-100 font-medium" : "text-zinc-400";
  return (
    <div className="flex items-center gap-2">
      <span
        className="w-2 h-2 rounded-full shrink-0"
        style={{ backgroundColor: colorHex }}
      />
      <span className={"text-sm w-28 shrink-0 " + spanClass}>
        {entity}
        {isPrimary ? " (client)" : ""}
      </span>
      <div className="flex-1 h-5 rounded bg-zinc-800 overflow-hidden">
        <div
          className="h-full rounded"
          style={{ width: widthPct + "%", backgroundColor: colorHex }}
        />
      </div>
      <span className="text-sm text-zinc-400 w-14 text-right">{mentions}</span>
    </div>
  );
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

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-4">
      <h3 className="text-sm font-medium text-zinc-300 mb-3">Share of voice</h3>
      <div className="space-y-2">
        {coverage.map((c, i) => (
          <BarItem
            key={i}
            entity={c.entity}
            mentions={c.mentions}
            total={total}
            clientName={clientName}
          />
        ))}
      </div>
    </div>
  );
}
