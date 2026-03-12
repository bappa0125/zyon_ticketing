"use client";

import { useState, useEffect } from "react";
import { ClientTable } from "@/components/ClientTable";
import Link from "next/link";
import { getApiBase } from "@/lib/api";

export default function ClientsPage() {
  const [clients, setClients] = useState<
    { name: string; domain: string; competitors: string[] }[]
  >([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchClients() {
      try {
        const res = await fetch(`${getApiBase()}/clients`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        setClients(data.clients ?? []);
      } catch (err) {
        console.error("fetchClients failed:", err);
        setClients([]);
      } finally {
        setLoading(false);
      }
    }
    fetchClients();
  }, []);

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
        </div>
        <h1 className="text-xl font-semibold mb-4 text-zinc-100">
          Monitored Clients
        </h1>
        <ClientTable clients={clients} loading={loading} />
      </div>
    </div>
  );
}
