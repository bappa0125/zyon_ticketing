"use client";

export interface OpportunityRow {
  topic: string;
  competitor_mentions: number;
  client_mentions: number;
}

interface OpportunityTableProps {
  opportunities: OpportunityRow[];
  loading?: boolean;
}

export function OpportunityTable({ opportunities, loading }: OpportunityTableProps) {
  if (loading) {
    return (
      <div className="text-center py-12 text-zinc-500">Loading opportunities…</div>
    );
  }

  if (opportunities.length === 0) {
    return (
      <div className="text-center py-12 text-zinc-500">
        No PR opportunities detected. Run media monitoring and topic detection, then select a client.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-zinc-800">
      <table className="min-w-full divide-y divide-zinc-800">
        <thead className="bg-zinc-900/50">
          <tr>
            <th className="px-4 py-3 text-left text-sm font-medium text-zinc-300">
              Topic
            </th>
            <th className="px-4 py-3 text-left text-sm font-medium text-zinc-300">
              Competitor Mentions
            </th>
            <th className="px-4 py-3 text-left text-sm font-medium text-zinc-300">
              Client Mentions
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-800 bg-zinc-900/30">
          {opportunities.map((o, i) => (
            <tr key={i} className="hover:bg-zinc-800/30">
              <td className="px-4 py-3 text-sm text-zinc-200">{o.topic || "—"}</td>
              <td className="px-4 py-3 text-sm text-zinc-400">{o.competitor_mentions}</td>
              <td className="px-4 py-3 text-sm text-zinc-400">{o.client_mentions}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
