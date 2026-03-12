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

const th = "px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-[var(--ai-muted)]";
const td = "px-4 py-3 text-sm text-[var(--ai-text-secondary)]";
const border = "border-[var(--ai-border)]";

export function TopicTable({ topics, loading, clientName }: TopicTableProps) {
  const [expandedRow, setExpandedRow] = useState<number | null>(null);

  if (loading) {
    return (
      <div className="text-center py-12 text-[var(--ai-muted)]">Loading topics…</div>
    );
  }

  if (topics.length === 0) {
    return (
      <div className="text-center py-12 text-[var(--ai-muted)]">
        No topics yet. Select a client and run article topics extraction.
      </div>
    );
  }

  return (
    <div className={"overflow-x-auto rounded-2xl border border-[var(--ai-border)] bg-[var(--ai-surface)] " + border}>
      <table className={"min-w-full divide-y " + border}>
        <thead className="bg-[var(--ai-bg-elevated)]">
          <tr>
            <th className={th}>Topic</th>
            <th className={th}>Vol</th>
            <th className={th}>Trend</th>
            <th className={th}>Sentiment</th>
            {clientName != null && clientName !== "" ? (
              <>
                <th className={th}>Client</th>
                <th className={th}>Competitors</th>
              </>
            ) : null}
            <th className={th}>Act</th>
            <th className="px-4 py-3 w-8" />
          </tr>
        </thead>
        <tbody className={"divide-y bg-[var(--ai-surface)] " + border}>
          {topics.map((t, i) => (
            <Fragment key={i}>
              <tr
                className="hover:bg-[var(--ai-surface-hover)] cursor-pointer select-none"
                onClick={() => setExpandedRow(expandedRow === i ? null : i)}
              >
                <td className={td + " font-medium text-[var(--ai-text)]"}>{t.topic || "—"}</td>
                <td className={td}>{t.mentions}</td>
                <td className={td}>
                  {t.trend_pct != null ? (
                    <span
                      className={
                        t.trend_pct > 0 ? "text-emerald-400" : t.trend_pct < 0 ? "text-amber-400" : "text-[var(--ai-muted)]"
                      }
                    >
                      {t.trend_pct > 0 ? "↑" : t.trend_pct < 0 ? "↓" : "→"} {t.trend_pct}%
                    </span>
                  ) : (
                    <span className="text-[var(--ai-muted)]">—</span>
                  )}
                </td>
                <td className={td}>{t.sentiment_summary ?? "—"}</td>
                {clientName != null && clientName !== "" ? (
                  <>
                    <td className={td}>{t.client_mentions ?? "—"}</td>
                    <td className={td}>{t.competitor_mentions ?? "—"}</td>
                  </>
                ) : null}
                <td className={td}>
                  <span
                    className={
                      t.action === "talk" ? "text-emerald-400 font-medium" : t.action === "avoid" ? "text-amber-400 font-medium" : "text-[var(--ai-text-secondary)]"
                    }
                  >
                    {t.action === "talk" ? "TALK" : t.action === "avoid" ? "AVOID" : "CAREFUL"}
                  </span>
                </td>
                <td className="px-2 py-2 text-[var(--ai-muted)]">
                  {(t.sample_headlines?.length ?? 0) > 0 ? (expandedRow === i ? "▼" : "▶") : ""}
                </td>
              </tr>
              {expandedRow === i && (t.sample_headlines?.length ?? 0) > 0 ? (
                <tr className="bg-[var(--ai-bg-elevated)]">
                  <td colSpan={clientName ? 8 : 6} className="px-4 py-3">
                    <div className={"text-xs text-[var(--ai-text-secondary)] border-l-2 border-[var(--ai-accent)] pl-4"}>
                      <p className="font-medium text-[var(--ai-text)] mb-2">Sample headlines</p>
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
