"use client";

import Link from "next/link";

const HOME_CARDS: { href: string; label: string; description: string }[] = [
  {
    href: "/chat",
    label: "Chat",
    description: "Ask in natural language. Get answers with pipeline steps and optional live search for latest articles.",
  },
  {
    href: "/dashboard",
    label: "Dashboard",
    description: "Executive PR Pulse: mentions, share of voice, timeline, ranked sources, and AI-generated brief. Download HTML or PDF.",
  },
  {
    href: "/topics",
    label: "Topics",
    description: "Topic-level volume, trend %, sentiment, and actions (Talk / Careful / Avoid). Use for messaging and briefing.",
  },
  {
    href: "/reputation",
    label: "Reputation",
    description: "Sentiment breakdown by entity, negative topics, and negative sources. Use for risk and response planning.",
  },
  {
    href: "/alerts",
    label: "Alerts",
    description: "Spike detection over a sliding window. Use for early warning and campaign tracking.",
  },
  {
    href: "/targets",
    label: "Targets",
    description: "Outlets where client and competitors appear. Use to prioritise outreach and pitch lists.",
  },
  {
    href: "/media-intelligence",
    label: "Media Intel",
    description: "Dashboard-style feed and filters for coverage discovery.",
  },
  {
    href: "/sentiment",
    label: "Sentiment",
    description: "Sentiment summaries and mention-level drill-down.",
  },
  {
    href: "/coverage",
    label: "Coverage",
    description: "Coverage comparison and timeline by entity and range.",
  },
  {
    href: "/clients",
    label: "Clients",
    description: "Configured clients used across Dashboard, Topics, and reports.",
  },
  {
    href: "/media",
    label: "Media",
    description: "Media pipeline status and latest ingested content.",
  },
  {
    href: "/opportunities",
    label: "Opportunities",
    description: "Actionable opportunities from media and social signals.",
  },
  {
    href: "/social",
    label: "Social",
    description: "Latest social posts and related context. Cross-reference with Alerts when volume spikes.",
  },
];

export default function HomePage() {
  return (
    <div className="app-page">
      {/* Hero: staggered entrance */}
      <section
        className="text-center py-12 md:py-16 animate-ai-fade-in"
        style={{ animationDelay: "0s" }}
      >
        <h1 className="text-3xl font-bold tracking-tight text-[var(--ai-text)] md:text-4xl lg:text-5xl">
          Zyon{" "}
          <span className="bg-gradient-to-r from-[var(--ai-accent)] to-[var(--ai-gradient-end)] bg-clip-text text-transparent">
            AI
          </span>
        </h1>
        <p className="mt-3 text-lg text-[var(--ai-text-secondary)] md:text-xl max-w-2xl mx-auto">
          Media intelligence and PR pulse for your clients. One place for dashboards, alerts, reputation, and briefs.
        </p>
      </section>

      {/* Cards grid: stagger animation + hover */}
      <section className="pt-4 pb-12 md:pt-6" aria-label="Explore">
        <h2 className="text-sm font-medium text-[var(--ai-muted)] uppercase tracking-wider mb-6 text-center">
          Where to go
        </h2>
        <ul className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 list-none p-0 m-0">
          {HOME_CARDS.map((card, index) => (
            <li
              key={card.href}
              className="opacity-0"
              style={{
                animation: "ai-fade-in 0.45s ease-out forwards",
                animationDelay: `${0.05 + index * 0.04}s`,
              }}
            >
              <Link
                href={card.href}
                className="app-card block p-5 md:p-6 h-full transition-all duration-300 hover:scale-[1.02] hover:shadow-lg hover:shadow-[var(--ai-accent-glow)]/10 hover:border-[var(--ai-accent)]/30 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ai-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--ai-bg)]"
              >
                <span className="text-base font-semibold text-[var(--ai-text)]">{card.label}</span>
                <p className="mt-2 text-sm text-[var(--ai-text-secondary)] leading-relaxed">
                  {card.description}
                </p>
                <span className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-[var(--ai-accent)]">
                  Open
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                  </svg>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
