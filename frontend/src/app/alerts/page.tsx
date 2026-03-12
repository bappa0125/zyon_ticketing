"use client";

import { useEffect, useMemo, useState } from "react";
import { getApiBase } from "@/lib/api";

const RANGE_OPTIONS = [
  { value: "24h", label: "24h" },
  { value: "7d", label: "7d" },
  { value: "30d", label: "30d" },
] as const;

type RangeValue = (typeof RANGE_OPTIONS)[number]["value"];

interface AlertsResponse {
  client: string;
  competitors: string[];
  range: string;
  window: { current_start: string; current_end: string; baseline_days: number };
  spikes: { entity: string; current_24h: number; baseline_daily_avg: number; ratio: number | null; delta: number }[];
}

export default function AlertsPage() {
  const [clients, setClients] = useState<{ name: string }[]>([]);
  const [client, setClient] = useState<string>("");
  const [range, setRange] = useState<RangeValue>("7d");
  const [loadingClients, setLoadingClients] = useState(true);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<AlertsResponse | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${getApiBase()}/clients`);
        if (!res.ok) throw new Error("clients failed");
        const json = await res.json();
        const list = json.clients ?? [];
        setClients(list);
        if (list.length > 0 && !client) setClient(list[0].name);
      } catch (e) {
        console.error(e);
        setClients([]);
      } finally {
        setLoadingClients(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const downloadUrl = useMemo(() => {
    if (!client.trim()) return "";
    const params = new URLSearchParams({ client: client.trim(), range });
    return `${getApiBase()}/reports/alerts.html?${params.toString()}`;
  }, [client, range]);

  useEffect(() => {
    if (!client.trim()) {
      setData(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    (async () => {
      try {
        const params = new URLSearchParams({ client: client.trim(), range });
        const res = await fetch(`${getApiBase()}/reports/alerts?${params.toString()}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = (await res.json()) as AlertsResponse;
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
  }, [client, range]);

  return (
    <div className="app-page">
      <div className="max-w-6xl mx-auto p-6">
        <header className="flex flex-wrap items-center justify-between gap-4 py-4 border-b border-zinc-800 mb-6">
          <div>
            <h1 className="text-xl font-semibold text-zinc-100">Alerts & Spike Monitor</h1>
            <p className="text-sm text-zinc-500 mt-1">
              Download a brief showing what’s spiking in the last 24 hours.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <select
              value={client}
              onChange={(e) => setClient(e.target.value)}
              disabled={loadingClients}
              className="px-3 py-2 rounded-lg bg-zinc-800 border border-zinc-700 text-zinc-200 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-600 min-w-[160px]"
            >
              {loadingClients ? (
                <option value="">Loading…</option>
              ) : (
                <>
                  <option value="">Select client</option>
                  {clients.map((c) => (
                    <option key={c.name} value={c.name}>
                      {c.name}
                    </option>
                  ))}
                </>
              )}
            </select>
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

        {!client.trim() && (
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-8 text-center text-zinc-500">
            Select a client to view spikes.
          </div>
        )}

        {client.trim() && (
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-6">
            <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
              <div>
                <p className="text-sm text-zinc-300">Spike window</p>
                <p className="text-xs text-zinc-500">
                  {data?.window?.current_start ?? "—"} → {data?.window?.current_end ?? "—"} • Baseline:{" "}
                  {data?.window?.baseline_days ?? "—"} days (daily avg)
                </p>
              </div>
              <p className="text-xs text-zinc-600">
                Threshold: current ≥ 5 and ≥ 2× baseline
              </p>
            </div>

            {loading ? (
              <div className="text-sm text-zinc-500">Loading…</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-zinc-800">
                  <thead className="bg-zinc-900/50">
                    <tr>
                      <th className="px-3 py-2 text-left text-xs font-medium text-zinc-400 uppercase tracking-wider">
                        Entity
                      </th>
                      <th className="px-3 py-2 text-right text-xs font-medium text-zinc-400 uppercase tracking-wider">
                        Current 24h
                      </th>
                      <th className="px-3 py-2 text-right text-xs font-medium text-zinc-400 uppercase tracking-wider">
                        Baseline/day
                      </th>
                      <th className="px-3 py-2 text-right text-xs font-medium text-zinc-400 uppercase tracking-wider">
                        ×
                      </th>
                      <th className="px-3 py-2 text-right text-xs font-medium text-zinc-400 uppercase tracking-wider">
                        Δ
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800">
                    {(data?.spikes ?? []).length === 0 ? (
                      <tr>
                        <td colSpan={5} className="px-3 py-3 text-sm text-zinc-500">
                          No spikes detected in this window.
                        </td>
                      </tr>
                    ) : (
                      (data?.spikes ?? []).map((s) => (
                        <tr key={s.entity} className="hover:bg-zinc-800/30">
                          <td className="px-3 py-2 text-sm text-zinc-200">{s.entity}</td>
                          <td className="px-3 py-2 text-sm text-zinc-400 text-right">{s.current_24h}</td>
                          <td className="px-3 py-2 text-sm text-zinc-400 text-right">{s.baseline_daily_avg}</td>
                          <td className="px-3 py-2 text-sm text-zinc-400 text-right">{s.ratio ?? "—"}</td>
                          <td className="px-3 py-2 text-sm text-zinc-400 text-right">{s.delta}</td>
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

