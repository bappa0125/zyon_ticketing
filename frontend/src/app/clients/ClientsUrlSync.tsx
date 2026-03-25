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
  const { clients, clientName, setClientName, ready, activeClient, pendingClientUrlRef } =
    useActiveClient();

  useEffect(() => {
    if (!ready || pathname !== "/clients") return;
    const q = searchParams.get("client")?.trim();
    const pend = pendingClientUrlRef.current;
    if (q && pend?.target === q && q === clientName) {
      pendingClientUrlRef.current = null;
    }
    if (!q || !clients.some((c) => c.name === q) || q === clientName) return;
    /* useSearchParams() can still show the previous ?client= until replace applies. */
    if (pend && pend.target === clientName && q === pend.fromUrl) return;
    setClientName(q);
  }, [pathname, searchParams, clients, clientName, setClientName, ready, pendingClientUrlRef]);

  useEffect(() => {
    if (!ready || pathname !== "/clients") return;
    const q = searchParams.get("client")?.trim();
    if (q) return;
    const v = searchParams.get("vertical")?.trim().toLowerCase();
    if (v !== "political" && v !== "trading") return;
    const pick = firstClientForVertical(clients, v);
    if (pick && pick.name !== clientName) setClientName(pick.name);
  }, [pathname, searchParams, clients, clientName, setClientName, ready]);

  /* Only patch vertical when client param already matches context (avoids a second replace during URL lag). */
  useEffect(() => {
    if (!ready || !clientName || pathname !== "/clients" || !activeClient) return;
    const q = searchParams.get("client")?.trim();
    if (q !== clientName) return;
    const v = verticalFromClient(activeClient);
    const currentVertical = searchParams.get("vertical")?.trim().toLowerCase();
    if (currentVertical === v) return;
    const p = new URLSearchParams(searchParams.toString());
    p.set("vertical", v);
    router.replace(`/clients?${p.toString()}`, { scroll: false });
  }, [ready, clientName, pathname, searchParams, router, activeClient]);

  return null;
}
