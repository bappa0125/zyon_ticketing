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
 * API ?vertical= bundle — updated during ClientProvider render (before children) so useEffect
 * fetches see the right config. Browser-only; SSR leaves null (legacy bundle on API).
 */
export const activeClientVerticalBundleRef: {
  current: "political" | "trading" | null;
} = { current: null };

function getActiveClientVerticalBundle(): "political" | "trading" | null {
  return activeClientVerticalBundleRef.current;
}

/**
 * Set or replace `client` on a path that may already have a query string.
 * Use for GETs so the active UI client is always sent to the API.
 */
export function withClientQuery(pathWithOptionalQuery: string, client: string | null | undefined): string {
  const trimmed = (client ?? "").trim();
  const qIdx = pathWithOptionalQuery.indexOf("?");
  const path = qIdx === -1 ? pathWithOptionalQuery : pathWithOptionalQuery.slice(0, qIdx);
  const raw = qIdx === -1 ? "" : pathWithOptionalQuery.slice(qIdx + 1);
  const params = new URLSearchParams(raw);
  if (trimmed) {
    params.set("client", trimmed);
  }
  const vb = getActiveClientVerticalBundle();
  if (vb === "political" || vb === "trading") {
    params.set("vertical", vb);
  }
  const qs = params.toString();
  return qs ? `${path}?${qs}` : path;
}

export type NarrativeApiItem = {
  title: string;
  narrative: string;
  belief: string;
  why_now: string;
  confidence_score: number;
  signal_strength: "strong" | "emerging";
  vertical: string;
  categories: string[];
  relevance: string;
  relevance_reason: string;
  market_signal?: string;
  companies: Record<string, { gap?: string; strategy?: string }>;
  founder_mode: { what_to_say: string; channels: string[]; example_post: string };
  pr_mode: {
    core_message: string;
    angle: string;
    content_examples: { news_article?: string; social_post?: string; forum_response?: string };
  };
  evidence?: { url: string; title?: string; snippet?: string; subreddit?: string }[];
  debug: { cluster_size: number; sample_posts: string[] };
};

export async function fetchNarratives(client: string, opts?: { limit?: number }): Promise<NarrativeApiItem[]> {
  const params = new URLSearchParams();
  params.set("limit", String(opts?.limit ?? 7));
  const url = withClientQuery(`${getApiBase()}/narratives?${params.toString()}`, client);
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  return (Array.isArray(data) ? data : []) as NarrativeApiItem[];
}
