"use client";

import { getEntityHex } from "@/lib/entityColors";

export interface TimelineDay {
  date: string;
  [entity: string]: string | number;
}

interface MentionsTrendChartProps {
  timeline: TimelineDay[];
  entities: string[];
  clientName?: string;
  loading?: boolean;
}

const W = 280;
const H = 100;
const PAD = { top: 4, right: 4, bottom: 18, left: 28 };

export function MentionsTrendChart({
  timeline,
  entities,
  clientName,
  loading,
}: MentionsTrendChartProps) {
  if (loading) {
    return (
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-4 h-44 flex items-center justify-center text-zinc-500 text-sm">
        Loading…
      </div>
    );
  }
  if (!timeline.length || !entities.length) {
    return (
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-4 h-44 flex items-center justify-center text-zinc-500 text-sm">
        No trend data
      </div>
    );
  }

  const slice = timeline.slice(-14);
  const maxCount = Math.max(
    ...slice.flatMap((d) => entities.map((e) => Number(d[e] || 0))),
    1
  );
  const chartW = W - PAD.left - PAD.right;
  const chartH = H - PAD.top - PAD.bottom;
  const scaleY = (v: number) => PAD.top + chartH - (v / maxCount) * chartH;
  const scaleX = (i: number) => PAD.left + (i / Math.max(slice.length - 1, 1)) * chartW;

  const pathD = (entity: string) =>
    slice
      .map((day, i) => `${scaleX(i)},${scaleY(Number(day[entity] || 0))}`)
      .reduce((acc, pt, i) => (i === 0 ? `M ${pt}` : `${acc} L ${pt}`), "");

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-4">
      <h3 className="text-sm font-medium text-zinc-300 mb-3">Mentions over time</h3>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full max-w-full h-28" preserveAspectRatio="xMidYMid meet">
        {entities.map((entity) => (
          <path
            key={entity}
            d={pathD(entity)}
            fill="none"
            stroke={getEntityHex(entity)}
            strokeWidth={clientName && entity.toLowerCase() === clientName.toLowerCase() ? 2.5 : 1.5}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        ))}
        {/* X axis labels - first, middle, last */}
        {[0, Math.floor(slice.length / 2), slice.length - 1].map((idx) => {
          const day = slice[idx];
          if (!day) return null;
          const dt = new Date(day.date);
          const label = dt.toLocaleDateString("en-US", { month: "short", day: "numeric" });
          return (
            <text
              key={idx}
              x={scaleX(idx)}
              y={H - 2}
              textAnchor={idx === 0 ? "start" : idx === slice.length - 1 ? "end" : "middle"}
              className="text-[10px] fill-zinc-500"
            >
              {label}
            </text>
          );
        })}
      </svg>
      <div className="flex flex-wrap gap-3 mt-1 pt-2 border-t border-zinc-800">
        {entities.map((e) => {
          const isClient = clientName && e.toLowerCase() === clientName.toLowerCase();
          return (
            <span key={e} className="flex items-center gap-1.5 text-xs text-zinc-400">
              <span
                className="w-2 h-2 rounded-full shrink-0"
                style={{ backgroundColor: getEntityHex(e) }}
              />
              {e}
              {isClient && " (client)"}
            </span>
          );
        })}
      </div>
    </div>
  );
}
