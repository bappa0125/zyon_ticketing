"use client";

import { getEntityTailwindText } from "@/lib/entityColors";

export interface DomainRow {
  domain: string;
  name: string;
  total: number;
  entities: Record<string, number>;
  /** article_documents in range for this domain (any entities); 0 = nothing ingested in window */
  articles_indexed?: number;
}

export interface PipelineMeta {
  unified_mentions_count?: number;
  article_documents_in_window?: number;
  media_sources_count?: number;
  articles_indexed_scan_error?: string | null;
}

interface CoverageByDomainProps {
  byDomain: DomainRow[];
  entities: string[];
  clientName: string;
  /** Competitor names to show as columns (instead of a single "Others" column). */
  competitors?: string[];
  loading?: boolean;
  onSelectDomain?: (domain: string | null) => void;
  selectedDomain?: string | null;
  /** Backend diagnostics: helps separate empty DB / date window vs entity-detection gaps */
  pipelineMeta?: PipelineMeta;
}

export function CoverageByDomain({
  byDomain,
  entities,
  clientName,
  competitors = [],
  loading,
  onSelectDomain,
  selectedDomain,
  pipelineMeta,
}: CoverageByDomainProps) {
  if (loading) {
    return (
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-4">
        <h3 className="text-sm font-medium text-zinc-300 mb-3">Coverage by source</h3>
        <div className="text-sm text-zinc-500">Loading…</div>
      </div>
    );
  }
  if (!byDomain?.length) {
    return (
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-4">
        <h3 className="text-sm font-medium text-zinc-300 mb-3">Coverage by source</h3>
        <div className="text-sm text-zinc-500">No source breakdown yet.</div>
      </div>
    );
  }

  const showCompetitorColumns = competitors.length > 0;

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-4">
      <h3 className="text-sm font-medium text-zinc-300 mb-3">Coverage by source</h3>
      <p className="text-xs text-zinc-500 mb-2">
        <strong>Total</strong> / entity columns = tracked mentions in range. <strong>Indexed</strong> = articles stored
        for that domain in range (even if no broker names detected). Click a row to filter feed.
      </p>
      {pipelineMeta?.articles_indexed_scan_error && (
        <p className="text-xs text-red-400 mb-2 rounded border border-red-900/60 bg-red-950/30 px-2 py-1.5">
          Indexed scan failed (backend): {pipelineMeta.articles_indexed_scan_error}
        </p>
      )}
      {!loading && pipelineMeta && !pipelineMeta.articles_indexed_scan_error && (
        <p className="text-xs text-zinc-400 mb-2 tabular-nums">
          Pipeline (selected range):{" "}
          <span className="text-zinc-300">{pipelineMeta.unified_mentions_count ?? "—"}</span> unified mentions ·{" "}
          <span className="text-zinc-300">{pipelineMeta.article_documents_in_window ?? 0}</span> article_documents
          mapped to any listed source · {pipelineMeta.media_sources_count ?? "—"} sources in config
        </p>
      )}
      {!loading &&
        !pipelineMeta?.articles_indexed_scan_error &&
        (pipelineMeta?.article_documents_in_window === 0 || pipelineMeta?.article_documents_in_window === undefined) &&
        (pipelineMeta?.unified_mentions_count === 0 || pipelineMeta?.unified_mentions_count === undefined) &&
        (byDomain?.length ?? 0) > 0 && (
          <p className="text-xs text-amber-200/90 mb-2 rounded border border-amber-900/50 bg-amber-950/25 px-2 py-1.5">
            No mentions and no indexed articles in this date range. Either nothing was ingested into{" "}
            <code className="text-amber-100/90">article_documents</code> recently, or all article dates fall outside the
            range (try <strong>30 days</strong>). Confirm RSS → article fetcher → MongoDB on the server; optional:{" "}
            <code className="text-amber-100/90">python scripts/diagnose_coverage_by_source.py</code> in the backend
            container.
          </p>
        )}
      <div className="overflow-x-auto max-h-64 overflow-y-auto">
        <table className="min-w-full text-sm">
          <thead className="sticky top-0 bg-zinc-900/95">
            <tr>
              <th className="text-left py-2 pr-2 text-zinc-400 font-medium">Source</th>
              <th className="text-right py-2 px-1 text-zinc-400 font-medium" title="article_documents in this date range">
                Indexed
              </th>
              <th className="text-right py-2 px-1 text-zinc-400 font-medium">Total</th>
              <th className={`text-right py-2 px-1 font-medium ${getEntityTailwindText(clientName)}`}>{clientName}</th>
              {showCompetitorColumns
                ? competitors.map((comp) => (
                    <th key={comp} className={`text-right py-2 px-1 font-medium ${getEntityTailwindText(comp)}`}>
                      {comp}
                    </th>
                  ))
                : (
                  <th className="text-right py-2 pl-1 text-zinc-400 font-medium">Others</th>
                )}
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800">
            {byDomain.map((row) => {
              const ent = row.entities || {};
              const entityKey = Object.keys(ent).find((k) => k.toLowerCase() === clientName.toLowerCase());
              const clientCount = (ent[clientName] ?? (entityKey ? ent[entityKey] : undefined)) ?? 0;
              const isSelected = selectedDomain === row.domain;
              return (
                <tr
                  key={row.domain}
                  className={`cursor-pointer hover:bg-zinc-800/50 ${isSelected ? "bg-zinc-700/50" : ""}`}
                  onClick={() => onSelectDomain?.(isSelected ? null : row.domain)}
                >
                  <td className="py-1.5 pr-2 text-zinc-200 truncate max-w-[140px]" title={row.domain}>
                    {row.name || row.domain}
                  </td>
                  <td className="text-right py-1.5 px-1 text-zinc-500 tabular-nums">
                    {row.articles_indexed ?? "—"}
                  </td>
                  <td className="text-right py-1.5 px-1 text-zinc-400">{row.total}</td>
                  <td className={`text-right py-1.5 px-1 ${getEntityTailwindText(clientName)}`}>{clientCount}</td>
                  {showCompetitorColumns
                    ? competitors.map((comp) => {
                        const ck = Object.keys(ent).find((k) => k.toLowerCase() === comp.toLowerCase());
                        const val = ent[comp] ?? (ck ? ent[ck] : undefined);
                        return (
                          <td key={comp} className={`text-right py-1.5 px-1 ${getEntityTailwindText(comp)}`}>
                            {val ?? 0}
                          </td>
                        );
                      })
                    : (
                      <td className="text-right py-1.5 pl-1 text-zinc-400">
                        {row.total - clientCount}
                      </td>
                    )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
