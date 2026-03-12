"use client";

import { getEntityHex } from "@/lib/entityColors";

export interface CoverageRow {
  entity: string;
  mentions: number;
}

interface ShareOfVoiceDonutProps {
  coverage: CoverageRow[];
  loading?: boolean;
  clientName?: string;
}

function isClientMatch(name: string, clientName: string | undefined): boolean {
  if (!clientName) return false;
  return name.toLowerCase() === clientName.toLowerCase();
}

export function ShareOfVoiceDonut({ coverage, loading, clientName }: ShareOfVoiceDonutProps) {
  const panelClass = "rounded-2xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-4 h-48 flex items-center justify-center text-sm text-[var(--ai-muted)]";
  if (loading) return <div className={panelClass}>Loading…</div>;
  if (!coverage.length) return <div className={panelClass}>No coverage in this period</div>;

  const total = coverage.reduce((s, c) => s + (c.mentions || 0), 0) || 1;
  const R = 45;
  const r = 22;
  const cx = 50;
  const cy = 50;
  let offset = 0;
  const segments = coverage.map((c) => {
    const pct = (c.mentions / total) * 100;
    const angle = (pct / 100) * 360;
    const segment = { entity: c.entity, mentions: c.mentions, pct, offset, angle };
    offset += angle;
    return segment;
  });

  function polarToCartesian(cx: number, cy: number, radius: number, deg: number) {
    const rad = (deg * Math.PI) / 180;
    return { x: cx + radius * Math.cos(rad - Math.PI / 2), y: cy + radius * Math.sin(rad - Math.PI / 2) };
  }
  function describeDonutSegment(
    cx: number,
    cy: number,
    R: number,
    r: number,
    startDeg: number,
    endDeg: number
  ) {
    const startO = polarToCartesian(cx, cy, R, startDeg);
    const endO = polarToCartesian(cx, cy, R, endDeg);
    const startI = polarToCartesian(cx, cy, r, startDeg);
    const endI = polarToCartesian(cx, cy, r, endDeg);
    const large = endDeg - startDeg > 180 ? 1 : 0;
    return `M ${startO.x} ${startO.y} A ${R} ${R} 0 ${large} 1 ${endO.x} ${endO.y} L ${endI.x} ${endI.y} A ${r} ${r} 0 ${large} 0 ${startI.x} ${startI.y} Z`;
  }

  return (
    <div className="rounded-2xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-4">
      <h3 className="text-sm font-semibold text-[var(--ai-text)] mb-3">Share of voice (%)</h3>
      <div className="flex items-center gap-4">
        <div className="relative shrink-0" style={{ width: "120px", height: "120px" }}>
          <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90">
            {segments.map((seg, i) => {
              const startDeg = (seg.offset / 360) * 360;
              const endDeg = ((seg.offset + seg.angle) / 360) * 360;
              if (seg.angle <= 0) return null;
              return (
                <path
                  key={i}
                  d={describeDonutSegment(cx, cy, R, r, startDeg, endDeg)}
                  fill={getEntityHex(seg.entity)}
                  className="opacity-90 hover:opacity-100 transition-opacity"
                />
              );
            })}
          </svg>
          <div className="absolute inset-0 flex items-center justify-center">
            <span className="text-lg font-semibold text-[var(--ai-text)]">{total}</span>
          </div>
        </div>
        <ul className="space-y-1.5 flex-1 min-w-0">
          {coverage.map((c, i) => {
            const pct = total > 0 ? ((c.mentions / total) * 100).toFixed(1) : "0";
            const isPrimary = isClientMatch(c.entity, clientName);
            return (
              <li key={i} className="flex items-center justify-between gap-2 text-sm">
                <span className="flex items-center gap-2 min-w-0">
                  <span
                    className="w-2 h-2 rounded-full shrink-0"
                    style={{ backgroundColor: getEntityHex(c.entity) }}
                  />
                  <span className={`truncate ${isPrimary ? "text-[var(--ai-text)] font-medium" : "text-[var(--ai-text-secondary)]"}`}>
                    {c.entity}
                    {isPrimary ? " (client)" : ""}
                  </span>
                </span>
                <span className="text-[var(--ai-text-secondary)] shrink-0">
                  {pct}% <span className="text-[var(--ai-muted)]">({c.mentions})</span>
                </span>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
