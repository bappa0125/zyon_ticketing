"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MutableRefObject,
  type ReactNode,
} from "react";
import { usePathname, useRouter } from "next/navigation";
import { activeClientVerticalBundleRef, getApiBase, ZYON_CLIENT_STORAGE_KEY } from "@/lib/api";
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
  slug: string;
  domain: string;
  /** Competitor display names (backward compatible). */
  competitors: string[];
  /** Canonical competitor slugs for comparisons/keys. */
  competitor_slugs: string[];
  vertical: string;
  features: ClientFeatures;
  report_timezone?: string;
};

/** While searchParams lag behind router.replace, avoid reverting context to the old ?client= value. */
export type PendingClientUrl = { target: string; fromUrl: string };

export type ActiveClientContextValue = {
  clients: ClientRow[];
  clientSlug: string | null;
  setClientSlug: (slug: string) => void;
  /** Backward-compat alias: accepts slug. */
  setClientName: (slug: string) => void;
  /** Display name of active client (non-canonical). */
  clientName: string | null;
  activeClient: ClientRow | null;
  ready: boolean;
  pendingClientUrlRef: MutableRefObject<PendingClientUrl | null>;
};

const ClientContext = createContext<ActiveClientContextValue | null>(null);

function normalizeClient(raw: Record<string, unknown>): ClientRow | null {
  const name = String(raw.name ?? "").trim();
  const slug = String(raw.slug ?? "").trim().toLowerCase();
  if (!name || !slug) return null;
  const f = (raw.features ?? {}) as Record<string, unknown>;
  return {
    name,
    slug,
    domain: String(raw.domain ?? "").trim(),
    competitors: Array.isArray(raw.competitors)
      ? raw.competitors.map((c) => String((c as any)?.name ?? "").trim()).filter(Boolean)
      : [],
    competitor_slugs: Array.isArray(raw.competitors)
      ? raw.competitors.map((c) => String((c as any)?.slug ?? "").trim().toLowerCase()).filter(Boolean)
      : [],
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
  const [clientSlug, setClientSlugState] = useState<string | null>(null);
  const pendingClientUrlRef = useRef<PendingClientUrl | null>(null);
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
    if (!clients.length || clientSlug !== null) return;
    let pick: string;
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      const urlC = params.get("client")?.trim().toLowerCase();
      const urlV = params.get("vertical")?.trim().toLowerCase();
      if (urlC && clients.some((c) => c.slug === urlC)) {
        pick = urlC;
      } else if (!urlC && (urlV === "political" || urlV === "trading")) {
        const row = firstClientForVertical(
          clients,
          urlV === "political" ? "political" : "trading"
        );
        if (row) {
          pick = row.slug;
        } else {
          const stored = localStorage.getItem(ZYON_CLIENT_STORAGE_KEY)?.trim();
          pick =
            stored && clients.some((c) => c.slug === stored) ? stored : clients[0].slug;
        }
      } else {
        const stored = localStorage.getItem(ZYON_CLIENT_STORAGE_KEY)?.trim();
        pick =
          stored && clients.some((c) => c.slug === stored) ? stored : clients[0].slug;
      }
      localStorage.setItem(ZYON_CLIENT_STORAGE_KEY, pick);
    } else {
      pick = clients[0].slug;
    }
    setClientSlugState(pick);
  }, [clients, clientSlug]);

  const setClientSlug = useCallback(
    (slug: string) => {
      const trimmed = slug.trim().toLowerCase();
      const row = clients.find((c) => c.slug === trimmed);
      if (!trimmed || !row) return;
      if (typeof window !== "undefined") {
        const fromUrl =
          new URLSearchParams(window.location.search).get("client")?.trim().toLowerCase() ?? "";
        pendingClientUrlRef.current = { target: trimmed, fromUrl };
      } else {
        pendingClientUrlRef.current = { target: trimmed, fromUrl: "" };
      }
      setClientSlugState(trimmed);
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
    () => clients.find((c) => c.slug === clientSlug) ?? null,
    [clients, clientSlug]
  );

  if (typeof window !== "undefined") {
    activeClientVerticalBundleRef.current = activeClient ? verticalFromClient(activeClient) : null;
  }

  const ready = clients.length > 0 && clientSlug !== null;

  const value = useMemo<ActiveClientContextValue>(
    () => ({
      clients,
      clientSlug,
      setClientSlug,
      setClientName: setClientSlug,
      clientName: activeClient?.name ?? null,
      activeClient,
      ready,
      pendingClientUrlRef,
    }),
    [clients, clientSlug, setClientSlug, activeClient, ready]
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
