"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface PRSummaryCardProps {
  client: string;
  range: string;
  prSummary: string;
  loading?: boolean;
}

export function PRSummaryCard({ client, range, prSummary, loading }: PRSummaryCardProps) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-4">
      <h3 className="text-sm font-medium text-zinc-300 mb-2">PR Agency Summary</h3>
      <p className="text-xs text-zinc-500 mb-3">
        Deterministic summary from Coverage by Source. Uses the same filters (period, source, content) as the table.
      </p>

      {loading ? (
        <div className="text-sm text-zinc-500">Loading summary…</div>
      ) : prSummary ? (
        <div className="p-4 rounded-lg bg-zinc-950 border border-zinc-800">
          <p className="text-xs text-zinc-500 mb-2">
            Brief for {client} • {range}
          </p>
          <div className="prose prose-invert prose-sm max-w-none text-zinc-300 [&_h2]:text-zinc-100 [&_h2]:text-base [&_ul]:my-2 [&_li]:my-0.5 [&_p]:my-2">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{prSummary}</ReactMarkdown>
          </div>
        </div>
      ) : (
        <div className="text-sm text-zinc-500">No summary data.</div>
      )}
    </div>
  );
}
