"use client";

export interface MediaMentionItem {
  id?: string;
  publisher: string;
  source_domain?: string;
  headline: string;
  publish_time: string;
  snippet: string;
  summary?: string;
  sentiment?: string | null;
  mention_type: "direct" | "competitor";
  entity: string;
  confidence: "verified" | "unverified" | "snippet match";
  link: string;
  url_note?: string;
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

export function MediaMentionCard({ item }: MediaMentionCardProps) {
  const hasLink = !!item.link;
  const confidenceLabel =
    item.confidence === "verified"
      ? "Verified"
      : item.confidence === "snippet match"
        ? "Snippet match"
        : "Unverified";

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
      </div>
      <p className="text-sm font-medium text-zinc-200 mb-1 line-clamp-2">{item.headline}</p>
      <p className="text-xs text-zinc-500 mb-2">
        {item.publisher} · {formatTimeAgo(item.publish_time)}
      </p>
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
      {(item.summary || item.snippet) && (
        <p className="text-sm text-zinc-400 mb-3 line-clamp-2">{item.summary || item.snippet}</p>
      )}
      {hasLink ? (
        <a
          href={item.link}
          target="_blank"
          rel="noopener noreferrer"
          className="text-sm text-zinc-300 hover:text-white hover:underline inline-flex items-center gap-1"
        >
          Open Article →
        </a>
      ) : (
        <span className="text-xs text-zinc-500">{item.url_note || "Publisher link unavailable"}</span>
      )}
    </article>
  );
}
