/**
 * API base URL for client-side fetch. Use this everywhere so deployment works.
 * - Same-origin (Docker + nginx, or Next.js rewrites): use "/api" so requests hit this host and get proxied.
 * - Cross-origin (e.g. frontend on Vercel, backend elsewhere): set NEXT_PUBLIC_API_URL at build time
 *   to the full API base (e.g. https://api.example.com/api) so the browser calls the correct host.
 * NEXT_PUBLIC_* is inlined at build time; for Docker same-origin you don't need to set it.
 */
export function getApiBase(): string {
  const env = process.env.NEXT_PUBLIC_API_URL;
  const base = (env && env.trim()) ? String(env).replace(/\/$/, "") : "/api";
  return base;
}

/** localStorage key — must match ClientContext */
export const ZYON_CLIENT_STORAGE_KEY = "zyon_active_client";

/**
 * Set or replace `client` on a path that may already have a query string.
 * Use for GETs so the active UI client is always sent to the API.
 */
export function withClientQuery(pathWithOptionalQuery: string, client: string | null | undefined): string {
  const trimmed = (client ?? "").trim();
  if (!trimmed) return pathWithOptionalQuery;
  const qIdx = pathWithOptionalQuery.indexOf("?");
  const path = qIdx === -1 ? pathWithOptionalQuery : pathWithOptionalQuery.slice(0, qIdx);
  const raw = qIdx === -1 ? "" : pathWithOptionalQuery.slice(qIdx + 1);
  const params = new URLSearchParams(raw);
  params.set("client", trimmed);
  return `${path}?${params.toString()}`;
}
