"use client";

import { useState, useEffect } from "react";
import { MediaTable } from "@/components/MediaTable";
import { CoverageByDomain, type DomainRow } from "@/components/MediaIntelligence/CoverageByDomain";
import Link from "next/link";

function getApiUrl(): string {
  if (typeof window === "undefined")
    return process.env.NEXT_PUBLIC_API_URL || "http://localhost/api";
  return "/api";
}

export default function MediaPage() {
  const [articles, setArticles] = useState<
    { title: string; source: string; url: string; entity: string; date?: string; snippet?: string }[]
  >([]);
  const [loading, setLoading] = useState(true);
  const [clientFilter, setClientFilter] = useState<string>("");
  const [clients, setClients] = useState<{ name: string }[]>([]);
  const [loadingClients, setLoadingClients] = useState(true);
  const [byDomain, setByDomain] = useState<DomainRow[]>([]);
  const [dashboardClient, setDashboardClient] = useState<string>("");
  const [dashboardCompetitors, setDashboardCompetitors] = useState<string[]>([]);
  const [loadingCoverage, setLoadingCoverage] = useState(false);

  useEffect(() => {
    async function fetchClients() {
      try {
        const res = await fetch(`${getApiUrl()}/clients`);
        if (!res.ok) throw new Error("Failed to load clients");
        const json = await res.json();
        setClients(json.clients ?? []);
      } catch {
        setClients([]);
      } finally {
        setLoadingClients(false);
      }
    }
    fetchClients();
  }, []);

  useEffect(() => {
    async function fetchArticles() {
      try {
        const url = clientFilter
          ? `${getApiUrl()}/media/latest?client=${encodeURIComponent(clientFilter)}`
          : `${getApiUrl()}/media/latest`;
        const res = await fetch(url);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        setArticles(data.articles ?? []);
      } catch (err) {
        console.error("fetchArticles failed:", err);
        setArticles([]);
      } finally {
        setLoading(false);
      }
    }
    fetchArticles();
  }, [clientFilter]);

  useEffect(() => {
    if (!clientFilter.trim()) {
      setByDomain([]);
      setDashboardClient("");
      setDashboardCompetitors([]);
      setLoadingCoverage(false);
      return;
    }
    let cancelled = false;
    setLoadingCoverage(true);
    (async () => {
      try {
        const res = await fetch(
          `${getApiUrl()}/media-intelligence/dashboard?client=${encodeURIComponent(clientFilter)}&range=7d`
        );
        if (!res.ok) throw new Error("Dashboard failed");
        const json = await res.json();
        if (!cancelled) {
          setByDomain(json.by_domain ?? []);
          setDashboardClient(json.client ?? clientFilter);
          setDashboardCompetitors(json.competitors ?? []);
        }
      } catch {
        if (!cancelled) {
          setByDomain([]);
          setDashboardClient(clientFilter);
          setDashboardCompetitors([]);
        }
      } finally {
        if (!cancelled) setLoadingCoverage(false);
      }
    })();
    return () => { cancelled = true; };
  }, [clientFilter]);

  const entities = dashboardClient ? [dashboardClient, ...dashboardCompetitors] : [];

  return (
    <div className="min-h-screen bg-[var(--background)] p-6">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center gap-4 mb-6">
          <Link
            href="/"
            className="text-sm text-zinc-400 hover:text-zinc-200"
          >
            ← Chat
          </Link>
          <Link
            href="/clients"
            className="text-sm text-zinc-400 hover:text-zinc-200"
          >
            Clients
          </Link>
          <Link
            href="/media-intelligence"
            className="text-sm text-zinc-400 hover:text-zinc-200"
          >
            Media Intelligence
          </Link>
        </div>
        <h1 className="text-xl font-semibold mb-4 text-zinc-100">
          Media Monitoring
        </h1>
        <p className="text-sm text-zinc-500 mb-4">
          Latest news mentions of monitored clients and competitors. Filter by client:
        </p>
        <div className="mb-6 flex flex-wrap items-center gap-4">
          {loadingClients ? (
            <span className="text-sm text-zinc-500">Loading clients…</span>
          ) : (
            <select
              value={clientFilter}
              onChange={(e) => setClientFilter(e.target.value)}
              className="px-3 py-2 rounded-lg bg-zinc-800 border border-zinc-700 text-zinc-200 focus:outline-none focus:ring-2 focus:ring-zinc-600 min-w-[160px]"
            >
              <option value="">All clients</option>
              {clients.map((c) => (
                <option key={c.name} value={c.name}>
                  {c.name}
                </option>
              ))}
            </select>
          )}
        </div>

        {clientFilter.trim() && (
          <section className="mb-6">
            <h2 className="text-lg font-medium text-zinc-200 mb-3">Coverage by source</h2>
            <CoverageByDomain
              byDomain={byDomain}
              entities={entities}
              clientName={dashboardClient}
              competitors={dashboardCompetitors}
              loading={loadingCoverage}
            />
          </section>
        )}

        <section>
          <h2 className="text-lg font-medium text-zinc-200 mb-3">Latest articles</h2>
          <MediaTable articles={articles} loading={loading} />
        </section>
      </div>
    </div>
  );
}
