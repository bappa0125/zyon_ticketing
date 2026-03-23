"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { usePathname, useRouter } from "next/navigation";
import { getApiBase, ZYON_CLIENT_STORAGE_KEY } from "@/lib/api";
import { firstClientForVertical, verticalFromClient } from "@/lib/clientVerticals";

export type ClientFeatures = {
  forums: boolean;
  youtube: boolean;
  reddit: boolean;
  twitter: boolean;
  twitter_schema: string;
};

export type ClientRow = {
  name: string;
  domain: string;
  competitors: string[];
  vertical: string;
  features: ClientFeatures;
  report_timezone?: string;
};

export type ActiveClientContextValue = {
  clients: ClientRow[];
  clientName: string | null;
  setClientName: (name: string) => void;
  activeClient: ClientRow | null;
  ready: boolean;
};

const ClientContext = createContext<ActiveClientContextValue | null>(null);

function normalizeClient(raw: Record<string, unknown>): ClientRow | null {
  const name = String(raw.name ?? "").trim();
  if (!name) return null;
  const f = (raw.features ?? {}) as Record<string, unknown>;
  return {
    name,
    domain: String(raw.domain ?? "").trim(),
    competitors: Array.isArray(raw.competitors) ? raw.competitors.map(String) : [],
    vertical: String(raw.vertical ?? "corporate_pr"),
    features: {
      forums: f.forums !== false,
      youtube: f.youtube !== false,
      reddit: f.reddit !== false,
      twitter: f.twitter !== false,
      twitter_schema: String(f.twitter_schema ?? "legacy"),
    },
    report_timezone: raw.report_timezone ? String(raw.report_timezone) : undefined,
  };
}

export function ClientProvider({ children }: { children: ReactNode }) {
  const [clients, setClients] = useState<ClientRow[]>([]);
  const [clientName, setClientNameState] = useState<string | null>(null);
  const router = useRouter();
  const pathname = usePathname() || "/";

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${getApiBase()}/clients`);
        if (!res.ok || cancelled) return;
        const data = await res.json();
        const list = (data.clients ?? [])
          .map((c: Record<string, unknown>) => normalizeClient(c))
          .filter((c: ClientRow | null): c is ClientRow => c !== null);
        if (!cancelled) setClients(list);
      } catch {
        if (!cancelled) setClients([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!clients.length || clientName !== null) return;
    let pick: string;
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      const urlC = params.get("client")?.trim();
      const urlV = params.get("vertical")?.trim().toLowerCase();
      if (urlC && clients.some((c) => c.name === urlC)) {
        pick = urlC;
      } else if (!urlC && (urlV === "political" || urlV === "trading")) {
        const row = firstClientForVertical(
          clients,
          urlV === "political" ? "political" : "trading"
        );
        if (row) {
          pick = row.name;
        } else {
          const stored = localStorage.getItem(ZYON_CLIENT_STORAGE_KEY)?.trim();
          pick =
            stored && clients.some((c) => c.name === stored) ? stored : clients[0].name;
        }
      } else {
        const stored = localStorage.getItem(ZYON_CLIENT_STORAGE_KEY)?.trim();
        pick =
          stored && clients.some((c) => c.name === stored) ? stored : clients[0].name;
      }
      localStorage.setItem(ZYON_CLIENT_STORAGE_KEY, pick);
    } else {
      pick = clients[0].name;
    }
    setClientNameState(pick);
  }, [clients, clientName]);

  const setClientName = useCallback(
    (name: string) => {
      const trimmed = name.trim();
      const row = clients.find((c) => c.name === trimmed);
      if (!trimmed || !row) return;
      setClientNameState(trimmed);
      if (typeof window !== "undefined") {
        localStorage.setItem(ZYON_CLIENT_STORAGE_KEY, trimmed);
        const params = new URLSearchParams(window.location.search);
        params.set("client", trimmed);
        params.set("vertical", verticalFromClient(row));
        const qs = params.toString();
        router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
      }
    },
    [clients, router, pathname]
  );

  const activeClient = useMemo(
    () => clients.find((c) => c.name === clientName) ?? null,
    [clients, clientName]
  );

  const ready = clients.length > 0 && clientName !== null;

  const value = useMemo<ActiveClientContextValue>(
    () => ({
      clients,
      clientName,
      setClientName,
      activeClient,
      ready,
    }),
    [clients, clientName, setClientName, activeClient, ready]
  );

  return <ClientContext.Provider value={value}>{children}</ClientContext.Provider>;
}

export function useActiveClient(): ActiveClientContextValue {
  const ctx = useContext(ClientContext);
  if (!ctx) {
    throw new Error("useActiveClient must be used within ClientProvider");
  }
  return ctx;
}
