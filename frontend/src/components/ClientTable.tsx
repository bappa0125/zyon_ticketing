"use client";

export interface ClientRow {
  name: string;
  domain: string;
  competitors: string[];
}

interface ClientTableProps {
  clients: ClientRow[];
  loading?: boolean;
}

export function ClientTable({ clients, loading }: ClientTableProps) {
  if (loading) {
    return (
      <div className="text-center py-12 text-zinc-500">Loading clients…</div>
    );
  }

  if (clients.length === 0) {
    return (
      <div className="text-center py-12 text-zinc-500">
        No clients configured. Add entries to config/clients.yaml.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-zinc-800">
      <table className="min-w-full divide-y divide-zinc-800">
        <thead className="bg-zinc-900/50">
          <tr>
            <th className="px-4 py-3 text-left text-sm font-medium text-zinc-300">
              Client
            </th>
            <th className="px-4 py-3 text-left text-sm font-medium text-zinc-300">
              Domain
            </th>
            <th className="px-4 py-3 text-left text-sm font-medium text-zinc-300">
              Competitors
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-800 bg-zinc-900/30">
          {clients.map((c, i) => (
            <tr key={i} className="hover:bg-zinc-800/30">
              <td className="px-4 py-3 text-sm text-zinc-200">{c.name}</td>
              <td className="px-4 py-3 text-sm text-zinc-400">{c.domain}</td>
              <td className="px-4 py-3 text-sm text-zinc-400">
                {Array.isArray(c.competitors)
                  ? c.competitors.join(", ")
                  : c.competitors ?? ""}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
