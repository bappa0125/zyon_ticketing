"use client";

import { useEffect, useMemo, useState } from "react";
import { getApiBase, withClientQuery } from "@/lib/api";

type FounderMode = { what_to_say: string; channels: string[]; example_post: string };
type PRMode = {
  core_message: string;
  angle: string;
  content_examples: { news_article?: string; social_post?: string; forum_response?: string };
};

export type NarrativeItem = {
  title: string;
  narrative: string;
  belief: string;
  why_now: string;
  confidence_score: number;
  signal_strength: "strong" | "emerging";
  vertical: string;
  categories: string[];
  relevance: "High" | "Medium" | "Low" | string;
  relevance_reason: string;
  market_signal?: string;
  companies: Record<string, { gap?: string; strategy?: string }>;
  founder_mode: FounderMode;
  pr_mode: PRMode;
  evidence?: { url: string; title?: string; snippet?: string; subreddit?: string }[];
  debug: { cluster_size: number; sample_posts: string[] };
};

function strengthBadge(strength: NarrativeItem["signal_strength"]) {
  if (strength === "strong") return "bg-emerald-500/15 text-emerald-300 ring-1 ring-emerald-500/30";
  return "bg-yellow-500/15 text-yellow-200 ring-1 ring-yellow-500/30";
}

function companyStatusIcon(meta?: { gap?: string }) {
  const gap = String(meta?.gap || "").trim();
  if (!gap) return { icon: "❌", label: "Not owning" };
  if (gap === "none") return { icon: "✅", label: "Strongly aligned" };
  if (gap === "white_space_opportunity") return { icon: "❌", label: "Not owning" };
  return { icon: "⚠", label: "Partially owning" };
}

function heatDotColor(str: "green" | "yellow" | "red") {
  if (str === "red") return "text-red-400";
  if (str === "yellow") return "text-yellow-300";
  return "text-emerald-300";
}

export function NarrativeDashboard(props: {
  client: string | null | undefined;
  companies: string[];
}) {
  const { client, companies } = props;
  const [items, setItems] = useState<NarrativeItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string>("");

  const [selected, setSelected] = useState<NarrativeItem | null>(null);

  // Optional filters
  const [strengthFilter, setStrengthFilter] = useState<"all" | "strong" | "emerging">("all");
  const [minConfidence, setMinConfidence] = useState<number>(0);
  const [categoryFilter, setCategoryFilter] = useState<string>("");

  useEffect(() => {
    if (!client?.trim()) {
      setItems([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    const url = withClientQuery(`${getApiBase()}/narratives?limit=7`, client);
    fetch(url)
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(`HTTP ${res.status}`))))
      .then((data) => setItems((Array.isArray(data) ? data : []) as NarrativeItem[]))
      .catch((e) => {
        setItems([]);
        setError(String(e?.message || "Failed to load narratives"));
      })
      .finally(() => setLoading(false));
  }, [client]);

  const allCategories = useMemo(() => {
    const seen = new Set<string>();
    for (const it of items) {
      for (const c of it.categories || []) {
        if (c) seen.add(c);
      }
    }
    // UI-friendly baseline order (extend with what backend returns)
    const baseline = ["pricing_charges", "platform_ux_stability", "trust_safety", "onboarding", "education", "execution_reliability"];
    const out = [...baseline.filter((b) => seen.has(b)), ...Array.from(seen).filter((c) => !baseline.includes(c))];
    return out;
  }, [items]);

  const filtered = useMemo(() => {
    return items.filter((it) => {
      if (strengthFilter !== "all" && it.signal_strength !== strengthFilter) return false;
      if ((it.confidence_score || 0) < minConfidence) return false;
      if (categoryFilter && !(it.categories || []).includes(categoryFilter)) return false;
      return true;
    });
  }, [items, strengthFilter, minConfidence, categoryFilter]);

  const heatmap = useMemo(() => {
    // Build per (category, company) list of narrative titles, weighted by strength
    const map: Record<string, Record<string, { titles: string[]; worst: "green" | "yellow" | "red" }>> = {};
    for (const cat of allCategories) {
      map[cat] = {};
      for (const co of companies) {
        map[cat][co] = { titles: [], worst: "green" };
      }
    }
    for (const it of items) {
      const cats = it.categories || [];
      for (const cat of cats) {
        if (!map[cat]) continue;
        for (const co of companies) {
          const meta = it.companies?.[co];
          const st = companyStatusIcon(meta).icon;
          if (st === "❌") continue; // narrative not owned/covered by that company
          map[cat][co].titles.push(it.title || it.narrative);
          // 🔴 if strong narrative exists, 🟡 if only emerging, 🟢 if none
          if (it.signal_strength === "strong") map[cat][co].worst = "red";
          else if (map[cat][co].worst === "green") map[cat][co].worst = "yellow";
        }
      }
    }
    return map;
  }, [items, allCategories, companies]);

  return (
    <section
      data-testid="narrative-intelligence-dashboard"
      className="mb-8 rounded-2xl border border-emerald-500/35 bg-zinc-900/60 p-4 shadow-lg shadow-black/20 ring-1 ring-emerald-500/15 md:p-5"
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-emerald-400/90">Narrative intelligence</p>
          <h2 className="mt-1 text-xl font-semibold text-zinc-100">Live positioning narratives</h2>
          <p className="mt-1 text-sm text-zinc-400">
            What matters now — open a card for founder + PR guidance. Category heatmap below the list.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="rounded-xl bg-zinc-900/60 ring-1 ring-zinc-800 px-3 py-2">
            <div className="flex items-center gap-2 text-xs text-zinc-300">
              <span className="text-zinc-400">Strength</span>
              {(["all", "strong", "emerging"] as const).map((k) => (
                <button
                  key={k}
                  className={[
                    "rounded-lg px-2 py-1 transition",
                    strengthFilter === k ? "bg-zinc-700 text-zinc-100" : "bg-zinc-800/40 text-zinc-300 hover:bg-zinc-800",
                  ].join(" ")}
                  onClick={() => setStrengthFilter(k)}
                  type="button"
                >
                  {k}
                </button>
              ))}
            </div>
          </div>
          <div className="rounded-xl bg-zinc-900/60 ring-1 ring-zinc-800 px-3 py-2">
            <div className="flex items-center gap-2 text-xs text-zinc-300">
              <span className="text-zinc-400">Confidence</span>
              <input
                className="w-20 accent-emerald-500"
                type="range"
                min={0}
                max={100}
                value={minConfidence}
                onChange={(e) => setMinConfidence(Number(e.target.value || 0))}
              />
              <span className="tabular-nums text-zinc-200">{minConfidence}+</span>
            </div>
          </div>
          <div className="rounded-xl bg-zinc-900/60 ring-1 ring-zinc-800 px-3 py-2">
            <div className="flex items-center gap-2 text-xs text-zinc-300">
              <span className="text-zinc-400">Category</span>
              <select
                className="bg-zinc-900 text-zinc-200 text-xs rounded-lg ring-1 ring-zinc-800 px-2 py-1"
                value={categoryFilter}
                onChange={(e) => setCategoryFilter(e.target.value)}
              >
                <option value="">All</option>
                {allCategories.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Section 1: Live Narratives */}
        <div className="lg:col-span-7">
          <div className="rounded-2xl bg-zinc-950/60 ring-1 ring-zinc-800 shadow-sm">
            <div className="px-4 py-3 border-b border-zinc-800">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-zinc-100">Live Narratives</h3>
                <div className="text-xs text-zinc-400">
                  {loading ? "Loading…" : `${filtered.length} shown`}
                </div>
              </div>
            </div>
            <div className="p-4 space-y-3">
              {error ? <div className="text-sm text-red-300">{error}</div> : null}
              {!loading && !error && items.length === 0 ? (
                <div className="rounded-xl border border-zinc-700/80 bg-zinc-950/40 p-4 text-sm text-zinc-300">
                  <p className="font-medium text-zinc-200">No narrative clusters yet</p>
                  <p className="mt-1 text-zinc-400">
                    Run the Narrative Positioning engine (or ensure Mongo has <code className="text-emerald-300/90">narrative_strategy_clusters</code> with{" "}
                    <code className="text-emerald-300/90">schema_version: 7</code>). The API must receive bundle vertical <code className="text-emerald-300/90">trading</code> mapped to{" "}
                    <code className="text-emerald-300/90">broker</code>.
                  </p>
                </div>
              ) : null}
              {!loading && items.length > 0 && filtered.length === 0 ? (
                <div className="text-sm text-zinc-400">No narratives match your filters.</div>
              ) : null}
              {filtered.map((it, idx) => (
                <button
                  key={`${it.title}-${idx}`}
                  type="button"
                  onClick={() => setSelected(it)}
                  className="w-full text-left rounded-2xl bg-zinc-900/40 ring-1 ring-zinc-800 px-4 py-4 shadow-sm transition hover:bg-zinc-900/60 hover:ring-zinc-700"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-lg font-semibold text-zinc-100 leading-snug">{it.title}</div>
                      <div className="mt-1 text-sm text-zinc-300 truncate">{it.narrative}</div>
                    </div>
                    <div className="flex flex-col items-end gap-2 shrink-0">
                      <span className={`px-2 py-1 rounded-lg text-xs font-medium ${strengthBadge(it.signal_strength)}`}>
                        {it.signal_strength}
                      </span>
                      <div className="text-xs text-zinc-300">
                        <span className="text-zinc-400">confidence</span>{" "}
                        <span className="tabular-nums text-zinc-100">{it.confidence_score}</span>
                      </div>
                    </div>
                  </div>

                  <div className="mt-3 flex flex-wrap gap-x-4 gap-y-2 text-xs text-zinc-300">
                    {companies.map((co) => {
                      const st = companyStatusIcon(it.companies?.[co]);
                      return (
                        <div key={co} className="flex items-center gap-1" title={`${co}: ${st.label}`}>
                          <span className="text-zinc-400">{co}:</span> <span>{st.icon}</span>
                        </div>
                      );
                    })}
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Section 3: Category Heatmap */}
        <div className="lg:col-span-5">
          <div className="rounded-2xl bg-zinc-950/60 ring-1 ring-zinc-800 shadow-sm">
            <div className="px-4 py-3 border-b border-zinc-800">
              <h3 className="text-sm font-semibold text-zinc-100">Category Heatmap</h3>
              <p className="mt-1 text-xs text-zinc-400">Hover cells to see narrative titles.</p>
            </div>
            <div className="p-4 overflow-auto">
              {allCategories.length === 0 ? (
                <div className="text-sm text-zinc-400">No categories returned yet.</div>
              ) : (
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-left text-zinc-400">
                      <th className="py-2 pr-3 font-medium">Category</th>
                      {companies.map((co) => (
                        <th key={co} className="py-2 pr-3 font-medium whitespace-nowrap">
                          {co}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {allCategories.map((cat) => (
                      <tr key={cat} className="border-t border-zinc-800/60">
                        <td className="py-2 pr-3 text-zinc-200 whitespace-nowrap">{cat}</td>
                        {companies.map((co) => {
                          const cell = heatmap?.[cat]?.[co];
                          const worst = cell?.worst || "green";
                          const titles = (cell?.titles || []).slice(0, 6);
                          const tooltip = titles.length ? titles.join(" • ") : "No narratives";
                          const dot = worst === "red" ? "🔴" : worst === "yellow" ? "🟡" : "🟢";
                          return (
                            <td key={co} className="py-2 pr-3" title={tooltip}>
                              <span className={heatDotColor(worst)}>{dot}</span>
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Section 2: Details Drawer */}
      {selected ? (
        <div className="fixed inset-0 z-50">
          <div className="absolute inset-0 bg-black/60" onClick={() => setSelected(null)} />
          <div className="absolute right-0 top-0 h-full w-full max-w-xl bg-zinc-950 ring-1 ring-zinc-800 shadow-2xl overflow-auto">
            <div className="p-5 border-b border-zinc-800 flex items-start justify-between gap-4">
              <div className="min-w-0">
                <div className="text-xl font-semibold text-zinc-100">{selected.title}</div>
                <div className="mt-1 text-sm text-zinc-300">{selected.narrative}</div>
                <div className="mt-2 flex items-center gap-3 text-xs text-zinc-400">
                  <span className={`px-2 py-1 rounded-lg ${strengthBadge(selected.signal_strength)}`}>{selected.signal_strength}</span>
                  <span>
                    confidence <span className="text-zinc-100 tabular-nums">{selected.confidence_score}</span>
                  </span>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setSelected(null)}
                className="rounded-xl bg-zinc-900/60 ring-1 ring-zinc-800 px-3 py-2 text-xs text-zinc-200 hover:bg-zinc-900"
              >
                Close
              </button>
            </div>

            <div className="p-5 space-y-5">
              <div>
                <div className="text-xs font-semibold text-zinc-300">Belief</div>
                <div className="mt-1 text-sm text-zinc-200">{selected.belief}</div>
              </div>
              <div>
                <div className="text-xs font-semibold text-zinc-300">Why now</div>
                <div className="mt-1 text-sm text-zinc-200">{selected.why_now}</div>
              </div>

              <div className="border-t border-zinc-800" />

              <div>
                <div className="text-xs font-semibold text-zinc-300">Founder mode</div>
                <div className="mt-2 space-y-2">
                  <div className="text-sm text-zinc-200">{selected.founder_mode?.what_to_say}</div>
                  <div className="rounded-2xl bg-zinc-900/40 ring-1 ring-zinc-800 p-3 text-sm text-zinc-200 whitespace-pre-wrap">
                    {selected.founder_mode?.example_post}
                  </div>
                </div>
              </div>

              <div className="border-t border-zinc-800" />

              <div>
                <div className="text-xs font-semibold text-zinc-300">PR mode</div>
                <div className="mt-2 space-y-2">
                  <div className="text-sm text-zinc-200">
                    <span className="text-zinc-400">Core message:</span> {selected.pr_mode?.core_message}
                  </div>
                  <div className="text-sm text-zinc-200">
                    <span className="text-zinc-400">Angle:</span> {selected.pr_mode?.angle}
                  </div>
                  <div className="grid grid-cols-1 gap-3 mt-2">
                    {(["news_article", "social_post", "forum_response"] as const).map((k) => (
                      <div key={k} className="rounded-2xl bg-zinc-900/40 ring-1 ring-zinc-800 p-3">
                        <div className="text-xs font-semibold text-zinc-300">{k}</div>
                        <div className="mt-1 text-sm text-zinc-200 whitespace-pre-wrap">{selected.pr_mode?.content_examples?.[k] || ""}</div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              <div className="border-t border-zinc-800" />

              <div>
                <div className="text-xs font-semibold text-zinc-300">Evidence</div>
                <div className="mt-2 space-y-2">
                  {(selected.evidence || []).length === 0 ? (
                    <div className="text-sm text-zinc-400">No evidence URLs available.</div>
                  ) : (
                    (selected.evidence || []).map((e, i) => (
                      <a
                        key={`${e.url}-${i}`}
                        href={e.url}
                        target="_blank"
                        rel="noreferrer"
                        className="block rounded-2xl bg-zinc-900/40 ring-1 ring-zinc-800 p-3 hover:bg-zinc-900/60"
                      >
                        <div className="text-sm text-zinc-200 break-words">{e.title || e.url}</div>
                        <div className="mt-1 text-xs text-zinc-400 break-words">{e.url}</div>
                      </a>
                    ))
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}

