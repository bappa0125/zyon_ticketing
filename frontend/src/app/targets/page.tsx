"use client";

import { useEffect, useMemo, useState } from "react";
import { getApiBase, withClientQuery } from "@/lib/api";
import { useActiveClient } from "@/context/ClientContext";

const RANGE_OPTIONS = [
  { value: "24h", label: "24h" },
  { value: "7d", label: "7d" },
  { value: "30d", label: "30d" },
] as const;

type RangeValue = (typeof RANGE_OPTIONS)[number]["value"];

interface TargetsResponse {
  client: string;
  competitors: string[];
  range: string;
  targets: { domain: string; client_mentions: number; competitor_mentions: number; top_competitor: string | null }[];
}

export default function TargetsPage() {
  const { clientName: client, ready: clientReady } = useActiveClient();
  const [range, setRange] = useState<RangeValue>("7d");
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<TargetsResponse | null>(null);

  const downloadUrl = useMemo(() => {
    if (!client?.trim()) return "";
    const params = new URLSearchParams({ client: client.trim(), range });
    return `${getApiBase()}/reports/targets.html?${params.toString()}`;
  }, [client, range]);

  useEffect(() => {
    if (!clientReady || !client?.trim()) {
      setData(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    (async () => {
      try {
        const params = new URLSearchParams({ client: client.trim(), range });
        const res = await fetch(
          withClientQuery(`${getApiBase()}/reports/targets?${params.toString()}`, client)
        );
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = (await res.json()) as TargetsResponse;
        if (!cancelled) setData(json);
      } catch (e) {
        console.error(e);
        if (!cancelled) setData(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [client, range, clientReady]);

  if (!clientReady || !client) {
    return (
      <div className="app-page">
        <div className="max-w-6xl mx-auto p-6">
          <p className="text-sm text-zinc-500">Loading client…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="app-page">
      <div className="max-w-6xl mx-auto p-6">
        <header className="flex flex-wrap items-center justify-between gap-4 py-4 border-b border-zinc-800 mb-6">
          <div>
            <h1 className="text-xl font-semibold text-zinc-100">Publication Targeting</h1>
            <p className="text-sm text-zinc-500 mt-1">
              Client: <strong className="text-zinc-300">{client}</strong> · Find domains covering competitors but not your client.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <select
              value={range}
              onChange={(e) => setRange(e.target.value as RangeValue)}
              className="px-3 py-2 rounded-lg bg-zinc-800 border border-zinc-700 text-zinc-200 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-600"
            >
              {RANGE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
            <a
              href={downloadUrl || "#"}
              onClick={(e) => {
                if (!downloadUrl) e.preventDefault();
              }}
              className={`px-4 py-2 rounded-lg border text-sm ${
                downloadUrl
                  ? "bg-zinc-800 border-zinc-700 text-zinc-200 hover:bg-zinc-700"
                  : "bg-zinc-900/40 border-zinc-800 text-zinc-500 cursor-not-allowed"
              }`}
            >
              Download HTML brief
            </a>
          </div>
        </header>

        {!client?.trim() && (
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-8 text-center text-zinc-500">
            Select a client to view targets.
          </div>
        )}

        {client.trim() && (
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-6">
            <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
              <div>
                <p className="text-sm text-zinc-300">Targets</p>
                <p className="text-xs text-zinc-500">
                  Domains where competitors have coverage but the client has none (in the selected range).
                </p>
              </div>
              <p className="text-xs text-zinc-600">Threshold: competitors ≥ 3, client = 0</p>
            </div>

            {loading ? (
              <div className="text-sm text-zinc-500">Loading…</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-zinc-800">
                  <thead className="bg-zinc-900/50">
                    <tr>
                      <th className="px-3 py-2 text-left text-xs font-medium text-zinc-400 uppercase tracking-wider">
                        Domain
                      </th>
                      <th className="px-3 py-2 text-right text-xs font-medium text-zinc-400 uppercase tracking-wider">
                        Client
                      </th>
                      <th className="px-3 py-2 text-right text-xs font-medium text-zinc-400 uppercase tracking-wider">
                        Competitors
                      </th>
                      <th className="px-3 py-2 text-left text-xs font-medium text-zinc-400 uppercase tracking-wider">
                        Top competitor
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800">
                    {(data?.targets ?? []).length === 0 ? (
                      <tr>
                        <td colSpan={4} className="px-3 py-3 text-sm text-zinc-500">
                          No targets found for this client/range.
                        </td>
                      </tr>
                    ) : (
                      (data?.targets ?? []).map((t) => (
                        <tr key={t.domain} className="hover:bg-zinc-800/30">
                          <td className="px-3 py-2 text-sm text-zinc-200">{t.domain}</td>
                          <td className="px-3 py-2 text-sm text-zinc-400 text-right">{t.client_mentions}</td>
                          <td className="px-3 py-2 text-sm text-zinc-400 text-right">{t.competitor_mentions}</td>
                          <td className="px-3 py-2 text-sm text-zinc-400">{t.top_competitor ?? "—"}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

