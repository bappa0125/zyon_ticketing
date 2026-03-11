"use client";

export interface MediaMentionItem {
  id?: string;
  publisher: string;
  source_domain?: string;
  headline: string;
  publish_time: string;
  snippet: string;
  summary?: string;
  /** AI-generated one-line summary (preferred when present) */
  ai_summary?: string;
  sentiment?: string | null;
  mention_type: "direct" | "competitor";
  entity: string;
  confidence: "verified" | "unverified" | "snippet match";
  link: string;
  /** Original URL from RSS when resolved link is missing or still a redirect (e.g. news.google.com) */
  url_original?: string;
  url_note?: string;
  /** full_text = full article read; snippet = title/summary only */
  content_quality?: "full_text" | "snippet";
  /** Other entities mentioned in the same article (enterprise: same URL, multiple mentions) */
  also_mentions?: string[];
}

interface MediaMentionCardProps {
  item: MediaMentionItem;
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
    if (diffMins < 60) return `${diffMins} min ago`;
    if (diffHours < 24) return `${diffHours} hours ago`;
    if (diffDays < 7) return `${diffDays} days ago`;
    return d.toLocaleDateString();
  } catch {
    return iso.slice(0, 10);
  }
}

function isUnresolvedRedirect(link: string): boolean {
  return !link || /news\.google\.com/i.test(link);
}

export function MediaMentionCard({ item }: MediaMentionCardProps) {
  const resolvedLink = (item.link || "").trim();
  const originalLink = (item.url_original || "").trim();
  const displayLink = resolvedLink || originalLink;
  const hasLink = !!displayLink;
  const showMayRedirect = hasLink && isUnresolvedRedirect(resolvedLink);
  const confidenceLabel =
    item.confidence === "verified"
      ? "Verified"
      : item.confidence === "snippet match"
        ? "Snippet match"
        : "Unverified";
  const isSnippetOnly = item.content_quality === "snippet";
  const contentQualityLabel = isSnippetOnly ? "Snippet" : "Full article";

  return (
    <article className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4 hover:border-zinc-700 transition-colors">
      <div className="flex flex-wrap items-center gap-2 mb-2">
        <span
          className={`text-xs font-medium px-2 py-0.5 rounded ${
            item.mention_type === "direct"
              ? "bg-emerald-500/20 text-emerald-400"
              : "bg-amber-500/20 text-amber-400"
          }`}
        >
          {item.mention_type === "direct" ? "Direct" : "Competitor"}
        </span>
        <span
          className={`text-xs font-medium px-2 py-0.5 rounded ${
            item.confidence === "verified"
              ? "bg-blue-500/20 text-blue-400"
              : "bg-zinc-600/40 text-zinc-400"
          }`}
          title={item.confidence === "unverified" ? "Headline/snippet only" : undefined}
        >
          {confidenceLabel}
        </span>
        <span
          className={`text-xs font-medium px-2 py-0.5 rounded ${
            isSnippetOnly ? "bg-amber-500/20 text-amber-400" : "bg-sky-500/20 text-sky-400"
          }`}
          title={isSnippetOnly ? "Entity detected from title/summary only" : "Full article text was read"}
        >
          {contentQualityLabel}
        </span>
      </div>
      <p className="text-sm font-medium text-zinc-200 mb-1 line-clamp-2">{item.headline}</p>
      <p className="text-xs text-zinc-500 mb-2">
        {item.publisher} · {formatTimeAgo(item.publish_time)}
      </p>
      {item.also_mentions && item.also_mentions.length > 0 && (
        <p className="text-xs text-zinc-500 mb-2">
          Also mentions: {item.also_mentions.join(", ")}
        </p>
      )}
      {item.sentiment && (
        <span
          className={`text-xs px-2 py-0.5 rounded mr-2 ${
            item.sentiment === "positive"
              ? "bg-emerald-500/20 text-emerald-400"
              : item.sentiment === "negative"
                ? "bg-red-500/20 text-red-400"
                : "bg-zinc-600/40 text-zinc-400"
          }`}
        >
          {item.sentiment}
        </span>
      )}
      {(item.ai_summary || item.summary || item.snippet || item.headline) && (
        <p className="text-sm text-zinc-400 mb-3 line-clamp-2">
          {item.ai_summary || item.summary || item.snippet || item.headline}
        </p>
      )}
      {hasLink ? (
        <a
          href={displayLink}
          target="_blank"
          rel="noopener noreferrer"
          className="text-sm text-zinc-300 hover:text-white hover:underline inline-flex items-center gap-1"
        >
          {showMayRedirect ? "Open (may redirect) →" : "Open Article →"}
        </a>
      ) : (
        <span className="text-xs text-zinc-500">{item.url_note || "Publisher link unavailable"}</span>
      )}
    </article>
  );
}
