"use client";

import { getEntityHex } from "@/lib/entityColors";

/** One row: { date: "YYYY-MM-DD", [entityName: number] } */
export interface TimelineRow {
  date: string;
  [entity: string]: string | number | undefined;
}

interface MentionsPerDayChartProps {
  timeline: TimelineRow[];
  entities: string[];
  clientName?: string;
  loading?: boolean;
}

function isClientMatch(name: string, clientName: string | undefined): boolean {
  if (!clientName) return false;
  return name.toLowerCase() === clientName.toLowerCase();
}

export function MentionsPerDayChart({
  timeline,
  entities,
  clientName,
  loading,
}: MentionsPerDayChartProps) {
  const panelClass = "rounded-2xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-4 h-64 flex items-center justify-center text-sm text-[var(--ai-muted)]";
  if (loading) {
    return <div className={panelClass}>Loading…</div>;
  }
  if (!timeline?.length || !entities?.length) {
    return <div className={panelClass}>No timeline data in this period</div>;
  }

  const maxDayTotal = Math.max(
    ...timeline.map((row) => {
      let s = 0;
      for (const e of entities) {
        const v = row[e];
        s += typeof v === "number" ? v : 0;
      }
      return s;
    }),
    1
  );

  return (
    <div className="rounded-2xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-4">
      <h3 className="text-sm font-semibold text-[var(--ai-text)] mb-3">Mentions per day</h3>
      <div className="flex gap-1 items-end h-40">
        {timeline.map((row, i) => {
          const dayTotal = entities.reduce(
            (sum, e) => sum + (typeof row[e] === "number" ? (row[e] as number) : 0),
            0
          );
          const label = row.date ? String(row.date).slice(5) : "";
          return (
            <div key={i} className="flex-1 flex flex-col items-center min-w-0 group">
              <div
                className="w-full flex flex-col-reverse rounded-t gap-0.5 min-h-[4px]"
                style={{ height: "140px" }}
                title={`${row.date}: ${dayTotal} mentions`}
              >
                {entities.map((entity) => {
                  const count = typeof row[entity] === "number" ? (row[entity] as number) : 0;
                  const h = dayTotal > 0 && maxDayTotal > 0 ? (count / maxDayTotal) * 100 : 0;
                  const color = getEntityHex(entity);
                  return (
                    <div
                      key={entity}
                      className="rounded-sm opacity-90 hover:opacity-100 transition-opacity"
                      style={{
                        height: `${Math.max(h, 0)}%`,
                        minHeight: count > 0 ? "4px" : "0",
                        backgroundColor: color,
                      }}
                      title={`${entity}: ${count}`}
                    />
                  );
                })}
              </div>
              <span className="text-[10px] text-[var(--ai-muted)] mt-1 truncate w-full text-center">
                {label}
              </span>
            </div>
          );
        })}
      </div>
      <div className="flex flex-wrap gap-3 mt-3 pt-3 border-t border-[var(--ai-border)]">
        {entities.map((e) => (
          <span key={e} className="flex items-center gap-1.5 text-xs">
            <span
              className="w-2 h-2 rounded-full shrink-0"
              style={{ backgroundColor: getEntityHex(e) }}
            />
            <span className={isClientMatch(e, clientName) ? "text-[var(--ai-text)] font-medium" : "text-[var(--ai-text-secondary)]"}>
              {e}
              {isClientMatch(e, clientName) ? " (client)" : ""}
            </span>
          </span>
        ))}
      </div>
    </div>
  );
}
