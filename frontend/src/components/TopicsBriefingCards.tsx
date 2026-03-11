"use client";

import type { TopicRow } from "./TopicTable";

interface TopicsBriefingCardsProps {
  topics: TopicRow[];
}

export function TopicsBriefingCards({ topics }: TopicsBriefingCardsProps) {
  const talk = topics.filter((t) => t.action === "talk");
  const careful = topics.filter((t) => t.action === "careful");
  const avoid = topics.filter((t) => t.action === "avoid");

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
      <div className="rounded-lg border border-emerald-800/60 bg-emerald-950/30 p-4">
        <h3 className="text-sm font-semibold text-emerald-300 uppercase tracking-wide mb-1">Talk about</h3>
        <p className="text-xs text-zinc-500 mb-3">{talk.length} topic{talk.length !== 1 ? "s" : ""}</p>
        <ul className="space-y-1.5 text-sm text-zinc-300">
          {talk.length === 0 ? (
            <li className="text-zinc-600 italic">None</li>
          ) : (
            talk.slice(0, 6).map((t, i) => (
              <li key={i} className="capitalize">{t.topic}</li>
            ))
          )}
        </ul>
      </div>
      <div className="rounded-lg border border-zinc-700 bg-zinc-900/40 p-4">
        <h3 className="text-sm font-semibold text-zinc-300 uppercase tracking-wide mb-1">Handle carefully</h3>
        <p className="text-xs text-zinc-500 mb-3">{careful.length} topic{careful.length !== 1 ? "s" : ""}</p>
        <ul className="space-y-1.5 text-sm text-zinc-400">
          {careful.length === 0 ? (
            <li className="text-zinc-600 italic">None</li>
          ) : (
            careful.slice(0, 6).map((t, i) => (
              <li key={i} className="capitalize">{t.topic}</li>
            ))
          )}
        </ul>
      </div>
      <div className="rounded-lg border border-amber-800/60 bg-amber-950/30 p-4">
        <h3 className="text-sm font-semibold text-amber-300 uppercase tracking-wide mb-1">Avoid</h3>
        <p className="text-xs text-zinc-500 mb-3">{avoid.length} topic{avoid.length !== 1 ? "s" : ""}</p>
        <ul className="space-y-1.5 text-sm text-zinc-400">
          {avoid.length === 0 ? (
            <li className="text-zinc-600 italic">None</li>
          ) : (
            avoid.slice(0, 6).map((t, i) => (
              <li key={i} className="capitalize">{t.topic}</li>
            ))
          )}
        </ul>
      </div>
    </div>
  );
}
