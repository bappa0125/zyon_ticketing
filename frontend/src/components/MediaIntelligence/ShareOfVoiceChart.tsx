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

const panel =
  "rounded-2xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-4 shadow-sm";
const muted = "text-[var(--ai-muted)]";
const body = "text-[var(--ai-text-secondary)]";
const primaryText = "text-[var(--ai-text)]";

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
  const spanClass = isPrimary ? primaryText + " font-medium" : body;
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
      <div className="flex-1 h-5 rounded bg-[var(--ai-bg-elevated)] overflow-hidden">
        <div
          className="h-full rounded"
          style={{ width: widthPct + "%", backgroundColor: colorHex }}
        />
      </div>
      <span className={"text-sm w-14 text-right " + body}>{mentions}</span>
    </div>
  );
}

export function ShareOfVoiceChart({ coverage, loading, clientName }: ShareOfVoiceChartProps) {
  if (loading) {
    return (
      <div className={panel + " h-40 flex items-center justify-center text-sm " + muted}>
        Loading…
      </div>
    );
  }
  if (!coverage.length) {
    return (
      <div className={panel + " h-40 flex items-center justify-center text-sm " + muted}>
        No coverage in this period
      </div>
    );
  }

  const total = coverage.reduce((s, c) => s + c.mentions, 0) || 1;

  return (
    <div className={panel}>
      <h3 className={"text-sm font-semibold mb-3 " + primaryText}>Share of voice</h3>
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
