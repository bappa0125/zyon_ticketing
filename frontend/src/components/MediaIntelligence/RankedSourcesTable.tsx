"use client";

/** One row from by_domain: domain, name, total, entities: { [entityName]: count } */
export interface RankedSourceRow {
  domain: string;
  name: string;
  total: number;
  entities: Record<string, number>;
}

interface RankedSourcesTableProps {
  rows: RankedSourceRow[];
  clientName: string;
  competitorNames: string[];
  loading?: boolean;
}

export function RankedSourcesTable({
  rows,
  clientName,
  competitorNames,
  loading,
}: RankedSourcesTableProps) {
  const panelClass = "rounded-2xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-4 text-sm text-[var(--ai-muted)]";
  if (loading) return <div className={panelClass}>Loading…</div>;
  if (!rows?.length) return <div className={panelClass}>No sources in this period</div>;

  const allEntities = [clientName, ...competitorNames.filter((c) => c !== clientName)];

  return (
    <div className="rounded-2xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-4">
      <h3 className="text-sm font-semibold text-[var(--ai-text)] mb-3">Ranked sources</h3>
      <p className="text-xs text-[var(--ai-muted)] mb-3">
        Mentions by outlet — client vs competitors.
      </p>
      <div className="overflow-x-auto rounded-xl border border-[var(--ai-border)]">
        <table className="min-w-full divide-y divide-[var(--ai-border)] text-sm">
          <thead className="bg-[var(--ai-bg-elevated)]">
            <tr>
              <th className="px-3 py-2 text-left text-xs font-medium text-[var(--ai-muted)] uppercase tracking-wider w-8">
                #
              </th>
              <th className="px-3 py-2 text-left text-xs font-medium text-[var(--ai-muted)] uppercase tracking-wider">
                Source
              </th>
              <th className="px-3 py-2 text-right text-xs font-medium text-[var(--ai-muted)] uppercase tracking-wider w-16">
                Total
              </th>
              {allEntities.map((e) => (
                <th
                  key={e}
                  className="px-3 py-2 text-right text-xs font-medium text-[var(--ai-muted)] uppercase tracking-wider w-20"
                >
                  {e === clientName ? `${e} (client)` : e}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--ai-border)]">
            {rows.map((row, idx) => (
              <tr key={row.domain || idx} className="hover:bg-[var(--ai-surface-hover)]">
                <td className="px-3 py-2 text-[var(--ai-muted)]">{idx + 1}</td>
                <td className="px-3 py-2 text-[var(--ai-text)]">
                  <span title={row.domain}>{row.name || row.domain || "—"}</span>
                </td>
                <td className="px-3 py-2 text-right text-[var(--ai-text)] font-medium">{row.total}</td>
                {allEntities.map((entity) => (
                  <td key={entity} className="px-3 py-2 text-right text-[var(--ai-text-secondary)]">
                    {row.entities?.[entity] ?? 0}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
