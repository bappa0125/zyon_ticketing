"use client";

export interface SentimentSummary {
  entity: string;
  positive: number;
  neutral: number;
  negative: number;
}

interface SentimentChartProps {
  summaries: SentimentSummary[];
  loading?: boolean;
}

export function SentimentChart({ summaries, loading }: SentimentChartProps) {
  if (loading) {
    return (
      <div className="text-center py-12 text-zinc-500">Loading sentiment…</div>
    );
  }

  if (summaries.length === 0) {
    return (
      <div className="text-center py-12 text-zinc-500">
        No sentiment data yet. Run media monitoring and sentiment analysis.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {summaries.map((s, i) => {
        const total = s.positive + s.neutral + s.negative;
        if (total === 0) return null;
        const pctPos = (s.positive / total) * 100;
        const pctNeu = (s.neutral / total) * 100;
        const pctNeg = (s.negative / total) * 100;
        return (
          <div key={i} className="rounded-lg border border-zinc-800 p-4 bg-zinc-900/30">
            <h3 className="text-sm font-medium text-zinc-200 mb-3">{s.entity}</h3>
            <div className="flex items-center gap-2 mb-2">
              <div className="flex-1 h-6 flex rounded overflow-hidden bg-zinc-800">
                {pctPos > 0 && (
                  <div
                    className="h-full bg-emerald-600"
                    style={{ width: `${pctPos}%` }}
                    title={`Positive: ${s.positive}`}
                  />
                )}
                {pctNeu > 0 && (
                  <div
                    className="h-full bg-zinc-500"
                    style={{ width: `${pctNeu}%` }}
                    title={`Neutral: ${s.neutral}`}
                  />
                )}
                {pctNeg > 0 && (
                  <div
                    className="h-full bg-rose-600"
                    style={{ width: `${pctNeg}%` }}
                    title={`Negative: ${s.negative}`}
                  />
                )}
              </div>
              <span className="text-xs text-zinc-400">{total} articles</span>
            </div>
            <div className="flex gap-4 text-xs text-zinc-500">
              <span><span className="text-emerald-500">Positive</span> {s.positive}</span>
              <span><span className="text-zinc-400">Neutral</span> {s.neutral}</span>
              <span><span className="text-rose-500">Negative</span> {s.negative}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
