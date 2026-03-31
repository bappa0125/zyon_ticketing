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
  /** One sentence: consequence or risk */
  why_it_matters?: string;
  /** Broker business consequence (revenue, churn, trust) */
  business_impact?: string;
  /** Top-line line to say (usable immediately; often mirrors founder intent) */
  what_to_say?: string;
  /** cluster | fallback_generated | stored | ui_fallback */
  source?: string;
  confidence_score: number;
  signal_strength: "strong" | "emerging";
  signal_reason?: string;
  vertical: string;
  /** Mandatory behavior tag; UI maps unclassified_behavior -> Emerging Pattern */
  behavior_tag: string;
  /** 0-2 domain tags used for heatmap */
  domain_tags: string[];
  relevance: string;
  relevance_reason: string;
  market_signal?: string;
  opportunity_line?: string;
  closest_competitor?: { name?: string; reason?: string };
  distribution_strategy?: string[];
  companies: Record<string, { gap?: string; strategy?: string }>;
  founder_mode: { what_to_say: string; channels: string[]; example_post: string };
  pr_mode: {
    core_message: string;
    angle: string;
    content_examples: { news_article?: string; social_post?: string; forum_response?: string };
  };
  evidence?: { url: string; title?: string; snippet?: string; subreddit?: string }[];
  debug: { cluster_size: number; sample_posts: string[]; fallback_low_signal?: boolean };
};

export type NarrativesDashboardMeta = {
  fallback_triggered?: boolean;
  fallback_mode?: boolean;
  clusters_rejected?: number;
  reason_summary?: string[];
};

export type NarrativesDashboardResponse = {
  narratives: NarrativeApiItem[];
  meta: NarrativesDashboardMeta;
};

export type NarrativeDrilldownItem = {
  title: string;
  narrative: string;
  belief: string;
  why_now: string;
  signal_strength: "strong" | "emerging" | string;
  signal_reason?: string;
  confidence_score: number;
  companies: Record<string, { gap?: string; strategy?: string }>;
  what_to_say?: string;
  opportunity_line?: string;
  closest_competitor?: { name?: string; reason?: string };
  distribution_strategy?: string[];
};

export async function fetchNarratives(
  client: string,
  opts?: { limit?: number }
): Promise<NarrativesDashboardResponse> {
  const params = new URLSearchParams();
  params.set("limit", String(opts?.limit ?? 7));
  const url = withClientQuery(`${getApiBase()}/narratives?${params.toString()}`, client);
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  if (Array.isArray(data)) {
    return { narratives: data as NarrativeApiItem[], meta: {} };
  }
  const raw = data as { narratives?: NarrativeApiItem[]; meta?: NarrativesDashboardMeta };
  return {
    narratives: Array.isArray(raw.narratives) ? raw.narratives : [],
    meta: raw.meta && typeof raw.meta === "object" ? raw.meta : {},
  };
}

export async function fetchNarrativesByCategory(
  client: string,
  opts: { category: string; company: string; limit?: number }
): Promise<NarrativeDrilldownItem[]> {
  const params = new URLSearchParams();
  params.set("category", String(opts.category || ""));
  params.set("company", String(opts.company || ""));
  params.set("limit", String(opts.limit ?? 80));
  const url = withClientQuery(`${getApiBase()}/narratives/by-category?${params.toString()}`, client);
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  return Array.isArray(data) ? (data as NarrativeDrilldownItem[]) : [];
}
