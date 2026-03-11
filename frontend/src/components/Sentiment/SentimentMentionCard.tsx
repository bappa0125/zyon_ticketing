"use client";

import type { MediaMentionItem } from "@/components/MediaIntelligence/MediaMentionCard";
import { getEntityTailwindBg, getEntityTailwindText } from "@/lib/entityColors";

/** Normalize API item - handle both feed format (headline, link) and possible variants */
function normalizeItem(item: Partial<MediaMentionItem>): {
  headline: string;
  snippet: string;
  publisher: string;
  publishTime: string;
  link: string;
  entity: string;
  sentiment: string;
} {
  const raw = item as Record<string, unknown>;
  return {
    headline: (raw?.headline ?? raw?.title ?? item?.headline ?? "Untitled")?.toString().trim() || "Untitled",
    snippet: (raw?.ai_summary ?? raw?.summary ?? raw?.snippet ?? item?.snippet ?? "")?.toString().trim() || "",
    publisher: (raw?.publisher ?? raw?.source ?? item?.publisher ?? "")?.toString().trim() || "Unknown",
    publishTime: (raw?.publish_time ?? raw?.published_at ?? item?.publish_time ?? "")?.toString() || "",
    link: (raw?.link ?? raw?.url ?? item?.link ?? item?.url_original ?? raw?.url_original ?? "")?.toString().trim() || "",
    entity: (raw?.entity ?? item?.entity ?? "")?.toString().trim() || "",
    sentiment: ((raw?.sentiment ?? item?.sentiment ?? "")?.toString().trim() || "neutral").toLowerCase(),
  };
}

function formatTimeAgo(iso: string): string {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return d.toLocaleDateString();
  } catch {
    return iso.slice(0, 10);
  }
}

const SENTIMENT_STYLES = {
  positive: "bg-emerald-500/20 text-emerald-400 border-emerald-500/40",
  neutral: "bg-zinc-500/20 text-zinc-300 border-zinc-500/40",
  negative: "bg-rose-500/20 text-rose-400 border-rose-500/40",
} as const;

interface SentimentMentionCardProps {
  item: MediaMentionItem;
}

export function SentimentMentionCard({ item }: SentimentMentionCardProps) {
  const n = normalizeItem(item);
  const style = (n.sentiment in SENTIMENT_STYLES
    ? SENTIMENT_STYLES[n.sentiment as keyof typeof SENTIMENT_STYLES]
    : SENTIMENT_STYLES.neutral) as string;
  const hasLink = !!n.link;
  const showMayRedirect = hasLink && /news\.google\.com/i.test(n.link);
  const bodyText = n.snippet || n.headline;

  return (
    <article className="rounded-xl border border-zinc-700/80 bg-zinc-900/60 hover:border-zinc-600 hover:bg-zinc-900/80 transition-all duration-200 overflow-hidden">
      <div className="p-4">
        <div className="flex items-start justify-between gap-3 mb-3">
          <span
            className={`inline-flex items-center px-2.5 py-1 rounded-lg text-xs font-semibold uppercase tracking-wider border ${style}`}
          >
            {n.sentiment}
          </span>
          {n.entity && (
            <span className={`text-xs font-medium px-2 py-0.5 rounded ${getEntityTailwindBg(n.entity)} ${getEntityTailwindText(n.entity)}`}>
              {n.entity}
            </span>
          )}
        </div>
        <h3 className="text-base font-semibold text-zinc-100 mb-2 line-clamp-2 leading-snug">
          {n.headline}
        </h3>
        {bodyText && (
          <p className="text-sm text-zinc-400 line-clamp-2 mb-3">
            {bodyText}
          </p>
        )}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-zinc-500 mb-3">
          <span>{n.publisher}</span>
          {n.publishTime && (
            <>
              <span>·</span>
              <span>{formatTimeAgo(n.publishTime)}</span>
            </>
          )}
        </div>
        {hasLink ? (
          <a
            href={n.link}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-sm font-medium text-zinc-300 hover:text-white transition-colors"
          >
            {showMayRedirect ? "Open (may redirect)" : "Read article"}
            <span className="text-zinc-500">→</span>
          </a>
        ) : (
          <span className="text-xs text-zinc-500">Publisher link unavailable</span>
        )}
      </div>
    </article>
  );
}
