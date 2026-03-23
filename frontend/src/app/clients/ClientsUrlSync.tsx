"use client";

import { useEffect } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useActiveClient } from "@/context/ClientContext";
import { firstClientForVertical, verticalFromClient } from "@/lib/clientVerticals";

/**
 * Keeps /clients?client= and ?vertical= in sync with the active client (and applies URL → context).
 */
export function ClientsUrlSync() {
  const pathname = usePathname() || "";
  const router = useRouter();
  const searchParams = useSearchParams();
  const { clients, clientName, setClientName, ready, activeClient } = useActiveClient();

  useEffect(() => {
    if (!ready || pathname !== "/clients") return;
    const q = searchParams.get("client")?.trim();
    if (q && clients.some((c) => c.name === q) && q !== clientName) {
      setClientName(q);
    }
  }, [pathname, searchParams, clients, clientName, setClientName, ready]);

  useEffect(() => {
    if (!ready || pathname !== "/clients") return;
    const q = searchParams.get("client")?.trim();
    if (q) return;
    const v = searchParams.get("vertical")?.trim().toLowerCase();
    if (v !== "political" && v !== "trading") return;
    const pick = firstClientForVertical(clients, v);
    if (pick && pick.name !== clientName) setClientName(pick.name);
  }, [pathname, searchParams, clients, clientName, setClientName, ready]);

  useEffect(() => {
    if (!ready || !clientName || pathname !== "/clients" || !activeClient) return;
    const currentClient = searchParams.get("client")?.trim();
    const v = verticalFromClient(activeClient);
    const currentVertical = searchParams.get("vertical")?.trim().toLowerCase();
    if (currentClient === clientName && currentVertical === v) return;
    const p = new URLSearchParams(searchParams.toString());
    p.set("client", clientName);
    p.set("vertical", v);
    router.replace(`/clients?${p.toString()}`, { scroll: false });
  }, [ready, clientName, pathname, searchParams, router, activeClient]);

  return null;
}
