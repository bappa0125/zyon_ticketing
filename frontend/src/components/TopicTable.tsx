"use client";

import { Fragment, useState } from "react";

export interface TopicRow {
  topic: string;
  mentions: number;
  client_mentions?: number;
  competitor_mentions?: number;
  trend_pct?: number | null;
  sentiment?: { positive: number; neutral: number; negative: number };
  sentiment_summary?: string;
  by_entity?: Record<string, number>;
  sample_headlines?: string[];
  action?: "talk" | "careful" | "avoid";
}

interface TopicTableProps {
  topics: TopicRow[];
  loading?: boolean;
  clientName?: string | null;
  onExport?: () => void;
}

export function TopicTable({ topics, loading, clientName }: TopicTableProps) {
  const [expandedRow, setExpandedRow] = useState<number | null>(null);

  if (loading) {
    return (
      <div className="text-center py-12 text-zinc-500">Loading topics…</div>
    );
  }

  if (topics.length === 0) {
    return (
      <div className="text-center py-12 text-zinc-500">
        No topics yet. Select a client and run article topics extraction.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-zinc-800">
      <table className="min-w-full divide-y divide-zinc-800">
        <thead className="bg-zinc-900/50">
          <tr>
            <th className="px-4 py-3 text-left text-sm font-medium text-zinc-300">Topic</th>
            <th className="px-4 py-3 text-left text-sm font-medium text-zinc-300">Vol</th>
            <th className="px-4 py-3 text-left text-sm font-medium text-zinc-300">Trend</th>
            <th className="px-4 py-3 text-left text-sm font-medium text-zinc-300">Sentiment</th>
            {clientName != null && clientName !== "" ? (
              <>
                <th className="px-4 py-3 text-left text-sm font-medium text-zinc-300">Client</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-zinc-300">Competitors</th>
              </>
            ) : null}
            <th className="px-4 py-3 text-left text-sm font-medium text-zinc-300">Act</th>
            <th className="px-4 py-3 w-8" />
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-800 bg-zinc-900/30">
          {topics.map((t, i) => (
            <Fragment key={i}>
              <tr
                className="hover:bg-zinc-800/30 cursor-pointer select-none"
                onClick={() => setExpandedRow(expandedRow === i ? null : i)}
              >
                <td className="px-4 py-3 text-sm text-zinc-200">{t.topic || "—"}</td>
                <td className="px-4 py-3 text-sm text-zinc-400">{t.mentions}</td>
                <td className="px-4 py-3 text-sm">
                  {t.trend_pct != null ? (
                    <span
                      className={
                        t.trend_pct > 0 ? "text-emerald-400" : t.trend_pct < 0 ? "text-amber-400" : "text-zinc-500"
                      }
                    >
                      {t.trend_pct > 0 ? "↑" : t.trend_pct < 0 ? "↓" : "→"} {t.trend_pct}%
                    </span>
                  ) : (
                    <span className="text-zinc-500">—</span>
                  )}
                </td>
                <td className="px-4 py-3 text-sm text-zinc-400">{t.sentiment_summary ?? "—"}</td>
                {clientName != null && clientName !== "" ? (
                  <>
                    <td className="px-4 py-3 text-sm text-zinc-400">{t.client_mentions ?? "—"}</td>
                    <td className="px-4 py-3 text-sm text-zinc-400">{t.competitor_mentions ?? "—"}</td>
                  </>
                ) : null}
                <td className="px-4 py-3">
                  <span
                    className={
                      t.action === "talk" ? "text-emerald-400" : t.action === "avoid" ? "text-amber-500" : "text-zinc-400"
                    }
                  >
                    {t.action === "talk" ? "TALK" : t.action === "avoid" ? "AVOID" : "CAREFUL"}
                  </span>
                </td>
                <td className="px-2 py-2 text-zinc-500">
                  {(t.sample_headlines?.length ?? 0) > 0 ? (expandedRow === i ? "▼" : "▶") : ""}
                </td>
              </tr>
              {expandedRow === i && (t.sample_headlines?.length ?? 0) > 0 ? (
                <tr className="bg-zinc-950/80">
                  <td colSpan={clientName ? 8 : 6} className="px-4 py-3">
                    <div className="text-xs text-zinc-400 border-l-2 border-zinc-700 pl-4">
                      <p className="font-medium text-zinc-300 mb-2">Sample headlines</p>
                      <ul className="space-y-1">
                        {(t.sample_headlines ?? []).map((h, j) => (
                          <li key={j}>• {h}</li>
                        ))}
                      </ul>
                    </div>
                  </td>
                </tr>
              ) : null}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}
