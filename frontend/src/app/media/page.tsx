"use client";

import { useState, useEffect } from "react";
import { MediaTable } from "@/components/MediaTable";
import {
  CoverageByDomain,
  type DomainRow,
  type PipelineMeta,
} from "@/components/MediaIntelligence/CoverageByDomain";
import Link from "next/link";
import { getApiBase, withClientQuery } from "@/lib/api";
import { useActiveClient } from "@/context/ClientContext";

export default function MediaPage() {
  const { clientName: clientFilter, ready: clientReady } = useActiveClient();
  const [articles, setArticles] = useState<
    { title: string; source: string; url: string; entity: string; date?: string; snippet?: string }[]
  >([]);
  const [loading, setLoading] = useState(true);
  const [byDomain, setByDomain] = useState<DomainRow[]>([]);
  const [coverageMeta, setCoverageMeta] = useState<PipelineMeta | undefined>(undefined);
  const [dashboardClient, setDashboardClient] = useState<string>("");
  const [dashboardCompetitors, setDashboardCompetitors] = useState<string[]>([]);
  const [loadingCoverage, setLoadingCoverage] = useState(false);

  useEffect(() => {
    async function fetchArticles() {
      if (!clientReady || !clientFilter?.trim()) {
        setArticles([]);
        setLoading(false);
        return;
      }
      setLoading(true);
      try {
        const url = withClientQuery(
          `${getApiBase()}/media/latest?client=${encodeURIComponent(clientFilter)}`,
          clientFilter
        );
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
  }, [clientFilter, clientReady]);

  useEffect(() => {
    if (!clientReady || !clientFilter?.trim()) {
      setByDomain([]);
      setCoverageMeta(undefined);
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
          withClientQuery(
            `${getApiBase()}/media-intelligence/dashboard?client=${encodeURIComponent(clientFilter)}&range=30d`,
            clientFilter
          ),
          { cache: "no-store" }
        );
        if (!res.ok) throw new Error("Dashboard failed");
        const json = await res.json();
        if (!cancelled) {
          setByDomain(json.by_domain ?? []);
          setCoverageMeta(json.meta);
          setDashboardClient(json.client ?? clientFilter);
          setDashboardCompetitors(json.competitors ?? []);
        }
      } catch {
        if (!cancelled) {
          setByDomain([]);
          setCoverageMeta(undefined);
          setDashboardClient(clientFilter);
          setDashboardCompetitors([]);
        }
      } finally {
        if (!cancelled) setLoadingCoverage(false);
      }
    })();
    return () => { cancelled = true; };
  }, [clientFilter, clientReady]);

  const entities = dashboardClient ? [dashboardClient, ...dashboardCompetitors] : [];

  if (!clientReady || !clientFilter) {
    return (
      <div className="app-page p-6">
        <p className="text-sm text-zinc-500">Loading client…</p>
      </div>
    );
  }

  return (
    <div className="app-page p-6">
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
          Latest news for <strong className="text-zinc-300">{clientFilter}</strong> (switch client in the header).
        </p>

        {clientFilter && (
          <section className="mb-6">
            <h2 className="text-lg font-medium text-zinc-200 mb-3">Coverage by source</h2>
            <p className="text-xs text-zinc-500 mb-2">Using last 30 days (same as Media Intel when set to 30d).</p>
            <CoverageByDomain
              byDomain={byDomain}
              entities={entities}
              clientName={dashboardClient}
              competitors={dashboardCompetitors}
              loading={loadingCoverage}
              pipelineMeta={coverageMeta}
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
