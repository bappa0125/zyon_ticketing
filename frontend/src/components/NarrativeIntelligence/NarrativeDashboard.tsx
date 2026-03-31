"use client";

import { useEffect, useMemo, useState } from "react";
import {
  fetchNarrativesByCategory,
  getApiBase,
  type NarrativeDrilldownItem,
  withClientQuery,
} from "@/lib/api";

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
  why_it_matters?: string;
  /** Broker business consequence (revenue, churn, trust) */
  business_impact?: string;
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
  relevance: "High" | "Medium" | "Low" | string;
  relevance_reason: string;
  market_signal?: string;
  opportunity_line?: string;
  closest_competitor?: { name?: string; reason?: string };
  distribution_strategy?: string[];
  companies: Record<string, { gap?: string; strategy?: string }>;
  founder_mode: FounderMode;
  pr_mode: PRMode;
  evidence?: { url: string; title?: string; snippet?: string; subreddit?: string }[];
  debug: { cluster_size: number; sample_posts: string[]; fallback_low_signal?: boolean };
};

function isFallbackLowSignal(it: NarrativeItem): boolean {
  const low = Boolean(it.debug?.fallback_low_signal);
  return (it.source || "") === "fallback_generated" || low;
}

/** Softer gate for deterministic low-signal week narratives — still blocks obvious garbage. */
function passesRelaxedProductionCard(it: NarrativeItem): boolean {
  const title = (it.title || "").trim();
  const narrative = (it.narrative || "").trim();
  if (!narrative || narrative.length < 28) return false;
  if (GENERIC_BODY_RE.test(narrative) || SUMMARY_START_RE.test(narrative)) return false;
  const wc = titleWordCount(title);
  if (wc < 3 || wc > 8 || !/[a-zA-Z]/.test(title)) return false;
  if (TITLE_JUNK_RE.test(title)) return false;
  const why = (it.why_it_matters || "").trim();
  if (!why || why.length < 20) return false;
  if (WHY_FLUFF_RE.test(why) || GENERIC_BODY_RE.test(why)) return false;
  const wts = sharpenWhatToSay(it);
  if (!wts || wts.length < 10) return false;
  return true;
}

const SUMMARY_START_RE =
  /^\s*(users are|people are|discussion around|discussions around|discussion about|various topics)\b/i;

const GENERIC_BODY_RE =
  /\b(users are|people are|discussion about|discussions about|various topics?|various|empowering users|helping users)\b/i;

const WHY_FLUFF_RE =
  /\b(important|critical(?:ly)?|critical for|helps?\s|helpful|it is important|essential to|valuable insight|clear insights|insights are)\b/i;

/** Slogan-style titles without concrete behavior */
const ABSTRACT_TITLE_RE =
  /\b(rewards?|celebrates?|embraces?|journey|path to|power of|wisdom|conviction|faith|hope|beats|wins|triumph)\b/i;

function isAbstractTitleUi(title: string): boolean {
  const t = (title || "").trim();
  if (t.length < 8) return false;
  return ABSTRACT_TITLE_RE.test(t);
}

/** Keyword / robotic title patterns — reject in UI gate */
const TITLE_JUNK_RE =
  /\b(seek|seeking|identify|identifying|discuss|discussion|discussing|various|frequently|topics?|feedback|portfolios?)\b/i;

function passesInsightTitle(title: string): boolean {
  const t = (title || "").trim();
  if (!isTitleReadable(t)) return false;
  if (TITLE_JUNK_RE.test(t)) return false;
  const wc = titleWordCount(t);
  if (wc < 3 || wc > 6) return false;
  return true;
}

function truncateTitleWords(raw: string, maxWords = 6): string {
  const parts = (raw || "")
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (parts.length <= maxWords) return raw.trim();
  return parts.slice(0, maxWords).join(" ");
}

/** Display title — trust layer uses raw title only */
function cardTitle(it: NarrativeItem): string {
  const w = (it.title || "").trim();
  if (passesInsightTitle(w)) return formatHeadlineTitle(w);
  const trimmed = truncateTitleWords(w.replace(TITLE_JUNK_RE, "").replace(/\s+/g, " ").trim(), 6);
  if (trimmed.length >= 6 && passesInsightTitle(trimmed)) return formatHeadlineTitle(trimmed);
  return formatHeadlineTitle(w);
}

function behaviorLabel(tag: string): string {
  const t = String(tag || "").trim();
  if (!t) return "";
  if (t === "unclassified_behavior") return "Emerging Pattern";
  return t.replace(/_/g, " ").replace(/\b\w/g, (ch) => ch.toUpperCase());
}

function domainLabels(it: NarrativeItem): string[] {
  const doms = Array.isArray(it.domain_tags) ? it.domain_tags : [];
  return doms
    .map((d) => String(d || "").trim())
    .filter(Boolean)
    .slice(0, 2)
    .map((d) => d.replace(/_/g, " ").replace(/\b\w/g, (ch) => ch.toUpperCase()));
}

/** Perception-grade bar; relaxed for low-signal / fallback rows so the UI is never empty. */
function passesTrustVisualCard(it: NarrativeItem): boolean {
  if (isFallbackLowSignal(it)) return passesRelaxedProductionCard(it);
  const title = (it.title || "").trim();
  const narrative = (it.narrative || "").trim();
  if (!narrative || narrative.length < 28) return false;
  if (!passesInsightTitle(title)) return false;
  if (isAbstractTitleUi(title)) {
    const n = narrative.toLowerCase();
    const hasConcrete =
      /mistake|wrong|confus|hesitat|churn|fee|trade|portfolio|reactive|volatil|noise|uncertain|doubt|risk|loss|broker/.test(n);
    if (!hasConcrete) return false;
  }
  if (GENERIC_BODY_RE.test(narrative) || SUMMARY_START_RE.test(narrative)) return false;
  if (!passesEmergingBehaviorInsight(narrative)) return false;
  const why = (it.why_it_matters || "").trim();
  if (why && WHY_FLUFF_RE.test(why)) return false;
  if (why && GENERIC_BODY_RE.test(why)) return false;
  const wts = sharpenWhatToSay(it);
  if (!wts || wts.length < 12 || wts.includes("?")) return false;
  if (/^(need |want |get |try |please |discover )\b/i.test(wts)) return false;
  const emerging = it.signal_strength === "emerging";
  if (emerging && (Number(it.confidence_score) || 0) < 40) return false;
  const bi = (it.business_impact || "").trim();
  if (bi && (WHY_FLUFF_RE.test(bi) || GENERIC_BODY_RE.test(bi))) return false;
  return true;
}

/** Emerging-only: must feel like insight, not abstract filler */
function passesEmergingSharp(it: NarrativeItem): boolean {
  if (it.signal_strength !== "emerging") return true;
  if (isFallbackLowSignal(it)) return passesRelaxedProductionCard(it);
  if (!passesTrustVisualCard(it)) return false;
  const n = (it.narrative || "").toLowerCase();
  if (/\b(trend|landscape|space|ecosystem|journey|paradigm)\b/.test(n) && !/\b(mistake|wrong|overlap|churn|fee|trade|sell|buy)\b/.test(n)) {
    return false;
  }
  return true;
}

function passesEmergingBehaviorInsight(narrative: string): boolean {
  const s = (narrative || "").trim().toLowerCase();
  if (s.length < 38) return false;
  const markers = [
    "confus",
    "hesitat",
    "panic",
    "fomo",
    "regret",
    "worried",
    "validat",
    "portfolio",
    "trade",
    "sell",
    "buy",
    "hold",
    "allocate",
    "overlap",
    "mistake",
    "wrong",
    "assume",
    "duplicate",
    "timing",
    "risk",
    "fee",
    "broker",
    "doubt",
    "second-guess",
    "volatile",
    "volatility",
    "noise",
    "uncertain",
    "headline",
    "reactive",
    "churn",
    "plan",
  ];
  return markers.some((m) => s.includes(m));
}

function narrativeKey(it: Pick<NarrativeItem, "title" | "narrative">): string {
  return `${(it.title || "").slice(0, 80)}|${(it.narrative || "").slice(0, 96)}`;
}

function titleWordCount(title: string): number {
  return title
    .trim()
    .split(/\s+/)
    .filter((w) => w.length > 0).length;
}

/** Readable title: not empty, has letters, 2–14 words */
function isTitleReadable(title: string): boolean {
  const t = title.trim();
  if (!t) return false;
  const n = titleWordCount(t);
  if (n < 2 || n > 14) return false;
  return /[a-zA-Z]/.test(t);
}

/**
 * Pool for “at least two” hydration; trust filter applied again at render.
 */
function relaxedNarrativeGate(it: NarrativeItem): boolean {
  const title = (it.title || "").trim();
  const narrative = (it.narrative || "").trim();
  if (!narrative) return false;
  const strong = it.signal_strength === "strong";
  if (strong) {
    return narrative.length >= 25 && (title.length >= 2 || narrative.length >= 40);
  }
  const conf = Number(it.confidence_score) || 0;
  if (conf < 40) return false;
  if (!passesInsightTitle(title)) return false;
  if (SUMMARY_START_RE.test(narrative)) return false;
  if (GENERIC_BODY_RE.test(narrative)) return false;
  if (/\b(empowering users|helping users|informed decisions)\b/i.test(narrative)) return false;
  if (!passesEmergingBehaviorInsight(narrative)) return false;
  return true;
}

function ensureDisplayList(raw: NarrativeItem[]): NarrativeItem[] {
  return sortNarrativesForUi(raw);
}

function formatHeadlineTitle(raw: string): string {
  const s = (raw || "").trim();
  if (!s) return "";
  const small = new Set(["a", "an", "the", "and", "or", "of", "in", "on", "for", "to", "vs"]);
  return s
    .split(/\s+/)
    .map((w, i) => {
      const lower = w.toLowerCase();
      if (i > 0 && small.has(lower)) return lower;
      return w.charAt(0).toUpperCase() + w.slice(1).toLowerCase();
    })
    .join(" ");
}

function oneLineNarrative(text: string, maxLen = 140): string {
  let t = (text || "").replace(/\s+/g, " ").trim();
  t = t.replace(
    /^(users are|people are|discussion around|discussions around|discussion about|various topics)\s+/i,
    ""
  );
  t = t.replace(/\b(empowering users|helping users|informed decisions)\b/gi, "clear positioning");
  const end = t.search(/[.!?](\s|$)/);
  if (end > 20 && end < 220) t = t.slice(0, end + 1);
  if (t.length > maxLen) t = t.slice(0, maxLen - 1).trim() + "…";
  return t;
}

function getWhyNowLine(it: Pick<NarrativeItem, "why_now">, fallback = "Discussion momentum is increasing across investor communities"): string {
  const raw = String(it.why_now || "").trim();
  if (!raw) return fallback;
  return oneLineNarrative(raw, 130) || fallback;
}

function getWhyItMattersLine(it: NarrativeItem, maxLen = 120): string {
  const w = (it.why_it_matters || "").trim();
  if (w && !WHY_FLUFF_RE.test(w) && !GENERIC_BODY_RE.test(w)) return oneLineNarrative(w, maxLen);
  const rel = (it.relevance_reason || "").trim();
  if (
    rel.length >= 40 &&
    !GENERIC_BODY_RE.test(rel) &&
    !WHY_FLUFF_RE.test(rel) &&
    !/^\s*(this is|communicators should|positioning)\b/i.test(rel)
  ) {
    return oneLineNarrative(rel, maxLen);
  }
  return "";
}

function priorityWhyLine(it: NarrativeItem): string {
  const core = getWhyItMattersLine(it, 155);
  if (!core) return "";
  return core;
}

function getBusinessImpactLine(it: NarrativeItem, maxLen = 140): string {
  const s = (it.business_impact || "").trim();
  if (!s || WHY_FLUFF_RE.test(s) || GENERIC_BODY_RE.test(s)) return "";
  return oneLineNarrative(s, maxLen);
}

/** Declarative, founder-like — not a generic question CTA */
function sharpenWhatToSay(it: NarrativeItem): string {
  const raw = (it.what_to_say || it.founder_mode?.what_to_say || "").trim();
  const lines = raw.split("\n").map((s) => s.trim()).filter(Boolean);
  let line = lines[0] || "";
  line = line.replace(/^(users are|people are)\s+/i, "").trim();
  if (line.endsWith("?")) {
    const alt = lines.find((s) => s && !s.endsWith("?"));
    if (alt) line = alt;
    else line = line.replace(/\?$/, ".").trim();
  }
  if (/^(do |does |is |are |can |could |would |should |need |want )/i.test(line) && lines[1]) {
    line = lines[1];
  }
  return line;
}

function strengthRank(s: NarrativeItem["signal_strength"]): number {
  return s === "strong" ? 0 : 1;
}

function clusterSize(it: NarrativeItem): number {
  return Number((it.debug || {}).cluster_size) || 0;
}

function sortNarrativesForUi(list: NarrativeItem[]): NarrativeItem[] {
  return [...list].sort((a, b) => {
    const sr = strengthRank(a.signal_strength) - strengthRank(b.signal_strength);
    if (sr !== 0) return sr;
    const c = (Number(b.confidence_score) || 0) - (Number(a.confidence_score) || 0);
    if (c !== 0) return c;
    return clusterSize(b) - clusterSize(a);
  });
}

function companyStatusIcon(meta?: { gap?: string }) {
  const gap = String(meta?.gap || "").trim();
  if (!gap) return { icon: "❌", label: "Not owning" };
  if (gap === "none") return { icon: "✅", label: "Strongly aligned" };
  if (gap === "white_space_opportunity") return { icon: "❌", label: "Not owning" };
  return { icon: "⚠", label: "Partially owning" };
}

function companyInsightLine(it: NarrativeItem, companies: string[]): string {
  if (!companies.length) return "";
  const icons = companies.map((co) => companyStatusIcon(it.companies?.[co]).icon);
  if (icons.every((i) => i === "❌")) {
    const opp = String(it.opportunity_line || "").trim();
    if (opp) return opp;
    return "";
  }
  return "Crowded narrative — hard to differentiate";
}

function closestCompetitorLine(it: { closest_competitor?: { name?: string; reason?: string } }): string {
  const cc = it?.closest_competitor || {};
  const name = String(cc?.name || "").trim();
  const reason = String(cc?.reason || "").trim();
  if (!name) return "";
  return reason ? `Closest competitor: ${name} (${reason})` : `Closest competitor: ${name}`;
}

function distributionBullets(it: { distribution_strategy?: string[] }): string[] {
  const xs = Array.isArray(it.distribution_strategy) ? it.distribution_strategy : [];
  return xs.map((s) => String(s || "").trim()).filter(Boolean).slice(0, 3);
}

function strengthBadge(strength: NarrativeItem["signal_strength"]) {
  if (strength === "strong") return "bg-emerald-500/15 text-emerald-300 ring-1 ring-emerald-500/30";
  return "bg-yellow-500/15 text-yellow-200 ring-1 ring-yellow-500/30";
}

/** Card spec: show confidence only when ≥ 50 */
function showConfidence(score: number): boolean {
  const n = Number(score) || 0;
  return n >= 50;
}

function heatDotColor(str: "green" | "yellow" | "red") {
  if (str === "red") return "text-red-400";
  if (str === "yellow") return "text-yellow-300";
  return "text-emerald-300";
}

type HeatWorst = "green" | "yellow" | "red" | "purple";

function heatDotColorV2(str: HeatWorst) {
  if (str === "purple") return "text-violet-300";
  return heatDotColor(str);
}

function heatmapCellWorst(
  narrativesInCategory: NarrativeItem[],
  company: string
): { worst: HeatWorst; titles: string[] } {
  const titles = Array.from(
    new Set(
      narrativesInCategory.map((n) => formatHeadlineTitle(n.title || "").trim() || n.narrative.slice(0, 60))
    )
  );
  if (narrativesInCategory.length === 0) {
    return { worst: "green", titles: [] };
  }
  const isWhiteSpace = (it: NarrativeItem): boolean => {
    const comps = it.companies || {};
    const keys = Object.keys(comps);
    if (keys.length === 0) return false;
    return keys.every((k) => String(comps?.[k]?.gap || "").trim() !== "none");
  };
  let worst: HeatWorst = "green";
  for (const n of narrativesInCategory) {
    const { icon } = companyStatusIcon(n.companies?.[company]);
    const strong = n.signal_strength === "strong";
    const emerging = n.signal_strength === "emerging";
    if (isWhiteSpace(n)) {
      worst = "purple";
    } else if (strong && icon !== "✅") {
      worst = "red";
    } else if (emerging && icon !== "✅" && worst !== "red") {
      worst = "yellow";
    }
  }
  return { worst, titles };
}

function NarrativeCard(props: {
  it: NarrativeItem;
  companies: string[];
  onSelect: (it: NarrativeItem) => void;
}) {
  const { it, companies, onSelect } = props;
  if (!passesTrustVisualCard(it)) return null;
  const isStrong = it.signal_strength === "strong";
  const wts = sharpenWhatToSay(it);
  const wim = getWhyItMattersLine(it);
  const wn = getWhyNowLine(it);
  const biz = getBusinessImpactLine(it);
  if (!wim) return null;
  return (
    <button
      type="button"
      onClick={() => onSelect(it)}
      className="w-full text-left rounded-2xl bg-zinc-900/40 ring-1 ring-zinc-800 px-4 py-4 shadow-sm transition hover:bg-zinc-900/60 hover:ring-zinc-700"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="text-lg font-bold text-zinc-100 leading-snug">{cardTitle(it)}</div>
          <div className="mt-1 text-sm text-zinc-300 line-clamp-2">{oneLineNarrative(it.narrative)}</div>
          {wn ? (
            <div className="mt-2 text-sm text-zinc-200">
              <span className="text-zinc-500 text-xs font-semibold uppercase tracking-wide">Why now</span>
              <span className="sr-only">: </span>
              <span className="block mt-0.5 text-zinc-200">{wn}</span>
            </div>
          ) : null}
          {wim ? (
            <div className="mt-2 text-sm text-amber-100/90">
              <span className="text-zinc-500 text-xs font-semibold uppercase tracking-wide">Why it matters</span>
              <span className="sr-only">: </span>
              <span className="block mt-0.5 text-zinc-200">{wim}</span>
            </div>
          ) : null}
          {biz ? (
            <div className="mt-2 text-sm text-sky-100/90">
              <span className="text-zinc-500 text-xs font-semibold uppercase tracking-wide">Business impact</span>
              <span className="block mt-0.5 text-zinc-200">{biz}</span>
            </div>
          ) : null}
          {wts ? (
            <div className="mt-2 text-sm text-zinc-200">
              <span className="text-emerald-400/90 font-semibold">👉 What to say:</span>{" "}
              <span className="text-zinc-50 font-semibold">{wts}</span>
            </div>
          ) : null}
        </div>
        <div className="flex flex-col items-end gap-2 shrink-0">
          <div className="flex flex-col items-end gap-1">
            <span className={`px-2 py-1 rounded-lg text-xs font-medium ${strengthBadge(it.signal_strength)}`}>
              {isStrong ? "strong" : "emerging"}
            </span>
            {!isStrong ? (
              <span className="text-[10px] uppercase tracking-wide text-amber-400/90">Early signal</span>
            ) : null}
          </div>
          {showConfidence(it.confidence_score) ? (
            <div className="text-xs text-zinc-300">
              <span className="text-zinc-400">confidence</span>{" "}
              <span className="tabular-nums text-zinc-100">{it.confidence_score}</span>
            </div>
          ) : null}
          {String(it.signal_reason || "").trim() ? (
            <div className="text-[10px] text-zinc-500 text-right max-w-[14rem] leading-snug">
              <span className="text-zinc-400">Signal:</span>{" "}
              <span className="text-zinc-500">{oneLineNarrative(String(it.signal_reason || ""), 90)}</span>
            </div>
          ) : (
            <div className="text-[10px] text-zinc-500">
              <span className="text-zinc-400">Signal:</span>{" "}
              <span className="text-zinc-500">
                {isStrong ? `Strong (cluster_size=${Number(it.debug?.cluster_size) || 0})` : "Early signal forming"}
              </span>
            </div>
          )}
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
      {closestCompetitorLine(it) ? (
        <p className="mt-2 text-xs text-zinc-400">{closestCompetitorLine(it)}</p>
      ) : null}
      {companies.length > 0 && companyInsightLine(it, companies) ? (
        <p className="mt-2 text-xs text-zinc-500 border-t border-zinc-800/80 pt-2">
          👉 {companyInsightLine(it, companies)}
        </p>
      ) : null}
    </button>
  );
}

export function NarrativeDashboard(props: {
  client: string | null | undefined;
  companies: string[];
}) {
  const { client, companies } = props;
  const [items, setItems] = useState<NarrativeItem[]>([]);
  const [dashboardMeta, setDashboardMeta] = useState<{
    fallback_mode?: boolean;
    fallback_triggered?: boolean;
  }>({});
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string>("");

  const [selected, setSelected] = useState<NarrativeItem | null>(null);

  const [drilldown, setDrilldown] = useState<{
    open: boolean;
    category: string;
    company: string;
    loading: boolean;
    error: string;
    items: NarrativeDrilldownItem[];
  }>({ open: false, category: "", company: "", loading: false, error: "", items: [] });

  const [strengthFilter, setStrengthFilter] = useState<"all" | "strong" | "emerging">("all");
  const [minConfidence, setMinConfidence] = useState<number>(0);
  const [domainFilter, setDomainFilter] = useState<string>("");

  const openDrilldown = (category: string, company: string) => {
    const cat = String(category || "").trim();
    const co = String(company || "").trim();
    if (!client?.trim() || !cat || !co) return;
    setSelected(null);
    setDrilldown({ open: true, category: cat, company: co, loading: true, error: "", items: [] });
    fetchNarrativesByCategory(client.trim(), { category: cat, company: co, limit: 80 })
      .then((rows) => setDrilldown((d) => ({ ...d, loading: false, items: Array.isArray(rows) ? rows : [] })))
      .catch((e) =>
        setDrilldown((d) => ({ ...d, loading: false, error: String(e?.message || "Failed to load drilldown") }))
      );
  };

  useEffect(() => {
    if (!client?.trim()) {
      setItems([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    setDashboardMeta({});
    const url = withClientQuery(`${getApiBase()}/narratives?limit=24`, client);
    fetch(url)
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(`HTTP ${res.status}`))))
      .then((data: NarrativeItem[] | { narratives?: NarrativeItem[]; meta?: Record<string, unknown> }) => {
        if (Array.isArray(data)) {
          setItems(data);
          return;
        }
        const rows = Array.isArray(data?.narratives) ? data.narratives : [];
        setItems(rows);
        const m = data?.meta && typeof data.meta === "object" ? data.meta : {};
        setDashboardMeta({
          fallback_mode: Boolean(m.fallback_mode),
          fallback_triggered: Boolean(m.fallback_triggered),
        });
      })
      .catch((e) => {
        setItems([]);
        setError(String(e?.message || "Failed to load narratives"));
      })
      .finally(() => setLoading(false));
  }, [client]);

  const displayNarratives = useMemo(() => ensureDisplayList(items), [items]);

  const sortedDisplay = useMemo(() => sortNarrativesForUi(displayNarratives), [displayNarratives]);

  const allDomains = useMemo(() => {
    const seen = new Set<string>();
    for (const it of displayNarratives) {
      for (const d of it.domain_tags || []) {
        if (d) seen.add(d);
      }
    }
    return Array.from(seen);
  }, [displayNarratives]);

  const filtered = useMemo(() => {
    return sortedDisplay.filter((it) => {
      if (strengthFilter !== "all" && it.signal_strength !== strengthFilter) return false;
      if (minConfidence > 0 && (Number(it.confidence_score) || 0) < minConfidence) return false;
      if (domainFilter && !(it.domain_tags || []).includes(domainFilter)) return false;
      return true;
    });
  }, [sortedDisplay, strengthFilter, minConfidence, domainFilter]);

  const strongNarratives = useMemo(() => filtered.filter((it) => it.signal_strength === "strong"), [filtered]);
  const emergingNarratives = useMemo(() => filtered.filter((it) => it.signal_strength === "emerging"), [filtered]);

  const priorityNarrative = useMemo(() => {
    const strongs = filtered
      .filter((it) => it.signal_strength === "strong")
      .filter((it) => passesTrustVisualCard(it));
    if (strongs.length > 0) return sortNarrativesForUi(strongs)[0];
    const em = sortNarrativesForUi(
      filtered.filter((it) => it.signal_strength === "emerging").filter((it) => passesEmergingSharp(it))
    );
    return em[0] ?? null;
  }, [filtered]);

  const strongNarrativesWithoutPriority = useMemo(() => {
    if (!priorityNarrative) return strongNarratives;
    const pk = narrativeKey(priorityNarrative);
    return strongNarratives.filter((it) => narrativeKey(it) !== pk);
  }, [strongNarratives, priorityNarrative]);

  const strongSectionList = useMemo(() => {
    const trusted = strongNarrativesWithoutPriority.filter((it) => passesTrustVisualCard(it));
    if (trusted.length > 0) return trusted;
    const em = sortNarrativesForUi(
      filtered.filter((e) => e.signal_strength === "emerging").filter((it) => passesEmergingSharp(it))
    );
    const pk = priorityNarrative ? narrativeKey(priorityNarrative) : "";
    return em.filter((it) => narrativeKey(it) !== pk);
  }, [strongNarrativesWithoutPriority, filtered, priorityNarrative]);

  const showStrongSection = strongSectionList.length > 0;

  const emergingNarrativesEnsured = useMemo(() => {
    let base = emergingNarratives
      .filter((it) => (Number(it.confidence_score) || 0) >= 40)
      .filter((it) => passesEmergingSharp(it));
    if (priorityNarrative && priorityNarrative.signal_strength === "emerging") {
      const pk = narrativeKey(priorityNarrative);
      base = base.filter((it) => narrativeKey(it) !== pk);
    }
    return base;
  }, [emergingNarratives, priorityNarrative]);

  const heatmap = useMemo(() => {
    const map: Record<string, Record<string, { worst: HeatWorst; titles: string[] }>> = {};
    for (const dom of allDomains) {
      map[dom] = {};
      const inDom = displayNarratives.filter((it) => (it.domain_tags || []).includes(dom));
      for (const co of companies) {
        map[dom][co] = heatmapCellWorst(inDom, co);
      }
    }
    return map;
  }, [displayNarratives, allDomains, companies]);

  const hasHeatmapSignals = useMemo(() => {
    return allDomains.some((dom) =>
      displayNarratives.some((it) => (it.domain_tags || []).includes(dom))
    );
  }, [allDomains, displayNarratives]);

  const strongSectionHasSource = strongNarratives.length > 0;
  const strongTrustCount = strongSectionList.length;
  const showLowSignalBanner =
    Boolean(dashboardMeta.fallback_mode || dashboardMeta.fallback_triggered) && !loading && !error;
  // Spec: hide empty sections completely (after load). Loading/error can still render the container.
  const showEmergingSection = Boolean(error) || loading || emergingNarrativesEnsured.length > 0;

  return (
    <section
      data-testid="narrative-intelligence-dashboard"
      className="mb-8 rounded-2xl border border-emerald-500/35 bg-zinc-900/60 p-4 shadow-lg shadow-black/20 ring-1 ring-emerald-500/15 md:p-5"
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-emerald-400/90">Narrative intelligence</p>
          <h2 className="mt-1 text-xl font-semibold text-zinc-100">Narrative decision engine</h2>
          <p className="mt-1 text-sm text-zinc-400">
            What matters, why it matters, what to say — insight-led, not dashboard noise.
          </p>
          {showLowSignalBanner ? (
            <p className="mt-3 rounded-lg border border-amber-500/35 bg-amber-950/25 px-3 py-2 text-sm text-amber-100/95">
              Low signal week — early narratives emerging
            </p>
          ) : null}
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
                value={domainFilter}
                onChange={(e) => setDomainFilter(e.target.value)}
              >
                <option value="">All</option>
                {allDomains.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-1 lg:grid-cols-12 gap-4">
        <div className="lg:col-span-7 space-y-4">
          {priorityNarrative && !loading && !error ? (
            <div className="rounded-2xl bg-gradient-to-br from-emerald-950/50 to-zinc-950/90 ring-2 ring-emerald-400/45 shadow-lg shadow-emerald-950/30 p-5">
              <div className="text-xs font-semibold uppercase tracking-wide text-emerald-200">🔥 Priority right now</div>
              <button
                type="button"
                onClick={() => setSelected(priorityNarrative)}
                className="mt-2 w-full text-left rounded-xl bg-zinc-950/70 ring-1 ring-emerald-500/20 px-4 py-4 hover:bg-zinc-900/75 transition"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    {Boolean(String(priorityNarrative.behavior_tag || "").trim()) ? (
                      <span className="inline-block mb-1 rounded-md bg-zinc-800/80 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-zinc-300">
                      {behaviorLabel(priorityNarrative.behavior_tag)}
                      </span>
                    ) : null}
                    <div className="text-xl font-bold text-zinc-50 leading-snug">{cardTitle(priorityNarrative)}</div>
                  </div>
                  <div className="shrink-0 text-right">
                    <div className="text-xl font-bold tabular-nums text-emerald-100">
                      {priorityNarrative.confidence_score}
                    </div>
                    <div className="text-[10px] uppercase tracking-wide text-zinc-500">confidence</div>
                  </div>
                </div>
                {priorityWhyLine(priorityNarrative) ? (
                  <p className="mt-3 text-base font-medium text-amber-50/95 leading-snug">{priorityWhyLine(priorityNarrative)}</p>
                ) : null}
                {getBusinessImpactLine(priorityNarrative, 160) ? (
                  <p className="mt-2 text-sm font-medium text-sky-100/95 leading-snug">
                    <span className="text-zinc-500 text-xs font-semibold uppercase tracking-wide">Business impact</span>{" "}
                    {getBusinessImpactLine(priorityNarrative, 160)}
                  </p>
                ) : null}
                {sharpenWhatToSay(priorityNarrative) ? (
                  <p className="mt-3 text-base text-emerald-50/95">
                    <span className="text-emerald-300 font-semibold">👉 What to say:</span>{" "}
                    <span className="font-semibold text-white">{sharpenWhatToSay(priorityNarrative)}</span>
                  </p>
                ) : null}
                {companies.length > 0 ? (
                  companyInsightLine(priorityNarrative, companies) ? (
                    <p className="mt-3 text-xs text-zinc-400">👉 {companyInsightLine(priorityNarrative, companies)}</p>
                  ) : null
                ) : null}
              </button>
            </div>
          ) : null}

          {showStrongSection ? (
            <div className="rounded-2xl bg-zinc-950/60 ring-1 ring-zinc-800 shadow-sm">
              <div className="px-4 py-3 border-b border-zinc-800">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-emerald-300/95">🔥 Strong narratives</h3>
                  <div className="text-xs text-zinc-400">
                    {loading
                      ? "Loading…"
                      : `${strongTrustCount} shown${strongSectionHasSource ? ` · ${strongNarratives.length} marked strong` : " · promoted from emerging"}`}
                  </div>
                </div>
              </div>
              <div className="p-4 space-y-3">
                {error ? <div className="text-sm text-red-300">{error}</div> : null}
                {strongSectionList.map((it, idx) => (
                  <NarrativeCard key={`s-${narrativeKey(it)}-${idx}`} it={it} companies={companies} onSelect={setSelected} />
                ))}
              </div>
            </div>
          ) : null}

          {showEmergingSection ? (
            <div className="rounded-2xl bg-zinc-950/60 ring-1 ring-zinc-800 shadow-sm">
              <div className="px-4 py-3 border-b border-zinc-800">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-amber-200/95">⚡ Emerging signals</h3>
                  <div className="text-xs text-zinc-400">
                    {loading ? "Loading…" : `${emergingNarrativesEnsured.length} shown`}
                    {!loading && items.length > 0 ? (
                      <span className="text-zinc-500"> · total {filtered.length} after filters</span>
                    ) : null}
                  </div>
                </div>
              </div>
              <div className="p-4 space-y-3">
                {emergingNarrativesEnsured.map((it, idx) => (
                  <NarrativeCard key={`e-${narrativeKey(it)}-${idx}`} it={it} companies={companies} onSelect={setSelected} />
                ))}
              </div>
            </div>
          ) : null}
        </div>

        <div className="lg:col-span-5">
          <div className="rounded-2xl bg-zinc-950/60 ring-1 ring-zinc-800 shadow-sm">
            <div className="px-4 py-3 border-b border-zinc-800">
              <h3 className="text-sm font-semibold text-zinc-100">Domain heatmap</h3>
              <p className="mt-1 text-xs text-zinc-400">
                ⭐ White Space (nobody owns) · 🔴 Strong + unowned · 🟡 Emerging + unowned · 🟢 Owned or no signal
              </p>
            </div>
            <div className="p-4 overflow-auto">
              {!hasHeatmapSignals && !loading ? (
                <div className="text-sm text-zinc-400">No domain signals yet — narratives are still emerging.</div>
              ) : allDomains.length === 0 ? (
                <div className="text-sm text-zinc-400">No domain signals yet — narratives are still emerging.</div>
              ) : (
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-left text-zinc-400">
                      <th className="py-2 pr-3 font-medium">Domain</th>
                      {companies.map((co) => (
                        <th key={co} className="py-2 pr-3 font-medium whitespace-nowrap">
                          {co}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {allDomains.map((dom) => (
                      <tr key={dom} className="border-t border-zinc-800/60">
                        <td className="py-2 pr-3 text-zinc-200 whitespace-nowrap">{dom}</td>
                        {companies.map((co) => {
                          const cell = heatmap?.[dom]?.[co];
                          const worst = cell?.worst || "green";
                          const titles = (cell?.titles || []).slice(0, 8);
                          const tooltip =
                            titles.length > 0
                              ? `Narratives: ${titles.join(" · ")}`
                              : "No narratives mapped to this domain yet";
                          const dot = worst === "purple" ? "⭐" : worst === "red" ? "🔴" : worst === "yellow" ? "🟡" : "🟢";
                          return (
                            <td key={co} className="py-2 pr-3" title={tooltip}>
                              <button
                                type="button"
                                onClick={() => openDrilldown(dom, co)}
                                className={[
                                  "inline-flex items-center gap-2 rounded-lg px-2 py-1 transition",
                                  "hover:bg-zinc-900/70 ring-1 ring-transparent hover:ring-zinc-700",
                                ].join(" ")}
                                aria-label={`Drilldown ${dom} / ${co}`}
                              >
                                <span className={heatDotColorV2(worst)}>{dot}</span>
                                <span className="text-[10px] text-zinc-500">view</span>
                              </button>
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

      {drilldown.open ? (
        <div className="fixed inset-0 z-50">
          <div className="absolute inset-0 bg-black/60" onClick={() => setDrilldown((d) => ({ ...d, open: false }))} />
          <div className="absolute right-0 top-0 h-full w-full max-w-2xl bg-zinc-950 ring-1 ring-zinc-800 shadow-2xl overflow-auto">
            <div className="p-5 border-b border-zinc-800 flex items-start justify-between gap-4">
              <div className="min-w-0">
                <div className="text-xs font-semibold uppercase tracking-wide text-zinc-400">Heatmap drilldown</div>
                <div className="mt-1 text-xl font-semibold text-zinc-100 break-words">
                  {drilldown.category} <span className="text-zinc-500">/</span> {drilldown.company}
                </div>
                <p className="mt-1 text-sm text-zinc-400">
                  Sorted by strength, then confidence. Shows narratives mapped to this domain.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setDrilldown((d) => ({ ...d, open: false }))}
                className="rounded-xl bg-zinc-900/60 ring-1 ring-zinc-800 px-3 py-2 text-xs text-zinc-200 hover:bg-zinc-900"
              >
                Close
              </button>
            </div>

            <div className="p-5 space-y-4">
              {drilldown.loading ? (
                <div className="text-sm text-zinc-300">Loading…</div>
              ) : drilldown.error ? (
                <div className="text-sm text-red-300">{drilldown.error}</div>
              ) : drilldown.items.length === 0 ? (
                <div className="rounded-2xl bg-zinc-900/40 ring-1 ring-zinc-800 p-4 text-sm text-zinc-300">
                  No strong narratives in this category yet
                </div>
              ) : (
                drilldown.items.map((it, idx) => {
                  const wts = String(it.what_to_say || "").trim();
                  const opp = String(it.opportunity_line || "").trim();
                  const wn = oneLineNarrative(String(it.why_now || "").trim(), 130) || "Discussion momentum is increasing across investor communities";
                  const dist = distributionBullets(it as any);
                  return (
                    <div key={`${it.title}-${idx}`} className="rounded-2xl bg-zinc-900/40 ring-1 ring-zinc-800 p-4">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="text-lg font-bold text-zinc-100 leading-snug break-words">
                            {formatHeadlineTitle(it.title || "Narrative")}
                          </div>
                          <div className="mt-1 text-sm text-zinc-300">{oneLineNarrative(it.narrative, 420)}</div>
                        </div>
                        <div className="shrink-0 text-right">
                          <div className="text-xs text-zinc-400">{String(it.signal_strength || "").toLowerCase()}</div>
                          <div className="text-xs text-zinc-300">
                            <span className="text-zinc-500">conf</span>{" "}
                            <span className="tabular-nums text-zinc-100">{Number(it.confidence_score) || 0}</span>
                          </div>
                        </div>
                      </div>

                      {opp ? (
                        <div className="mt-3 text-sm text-zinc-200">
                          <span className="text-violet-300/90 font-semibold">👉 Opportunity:</span>{" "}
                          <span className="text-zinc-50 font-semibold">{opp}</span>
                        </div>
                      ) : null}

                      {dist.length > 0 ? (
                        <div className="mt-3">
                          <div className="text-xs font-semibold uppercase tracking-wide text-zinc-300">👉 Where to push</div>
                          <ul className="mt-2 space-y-1 text-sm text-zinc-200 list-disc pl-5">
                            {dist.map((b, i) => (
                              <li key={`${b}-${i}`}>{b}</li>
                            ))}
                          </ul>
                        </div>
                      ) : null}

                      <div className="mt-3">
                        <div className="text-xs font-semibold text-zinc-300">Why now</div>
                        <div className="mt-1 text-sm text-zinc-200">{wn}</div>
                      </div>

                      {wts ? (
                        <div className="mt-3 text-sm text-zinc-200">
                          <span className="text-emerald-400/90 font-semibold">👉 What to say:</span>{" "}
                          <span className="text-zinc-50 font-semibold">{wts}</span>
                        </div>
                      ) : null}

                      {closestCompetitorLine(it as any) ? (
                        <div className="mt-3 text-sm text-zinc-200">
                          <span className="text-zinc-400">{closestCompetitorLine(it as any)}</span>
                        </div>
                      ) : null}

                      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-2 text-xs text-zinc-300 border-t border-zinc-800/80 pt-3">
                        {companies.map((co) => {
                          const st = companyStatusIcon((it.companies || {})[co]);
                          return (
                            <div key={co} className="flex items-center gap-1" title={`${co}: ${st.label}`}>
                              <span className="text-zinc-400">{co}:</span> <span>{st.icon}</span>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>
      ) : null}

      {selected ? (
        <div className="fixed inset-0 z-50">
          <div className="absolute inset-0 bg-black/60" onClick={() => setSelected(null)} />
          <div className="absolute right-0 top-0 h-full w-full max-w-xl bg-zinc-950 ring-1 ring-zinc-800 shadow-2xl overflow-auto">
            <div className="p-5 border-b border-zinc-800 flex items-start justify-between gap-4">
              <div className="min-w-0">
                <div className="text-xl font-semibold text-zinc-100">{cardTitle(selected)}</div>
                <div className="mt-1 text-sm text-zinc-300">{oneLineNarrative(selected.narrative, 400)}</div>
                <div className="mt-2 flex items-center gap-3 text-xs text-zinc-400 flex-wrap">
                  <span className={`px-2 py-1 rounded-lg ${strengthBadge(selected.signal_strength)}`}>
                    {selected.signal_strength}
                  </span>
                  {selected.signal_strength === "emerging" ? (
                    <span className="text-[10px] uppercase tracking-wide text-amber-400/90">Early signal</span>
                  ) : null}
                  {showConfidence(selected.confidence_score) ? (
                    <span>
                      confidence <span className="text-zinc-100 tabular-nums">{selected.confidence_score}</span>
                    </span>
                  ) : null}
                </div>
                {companies.length > 0 ? (
                  companyInsightLine(selected, companies) ? (
                    <p className="mt-2 text-xs text-zinc-500">👉 {companyInsightLine(selected, companies)}</p>
                  ) : null
                ) : null}
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
              {distributionBullets(selected).length > 0 ? (
                <div className="rounded-2xl bg-zinc-900/40 ring-1 ring-zinc-800 p-4">
                  <div className="text-xs font-semibold uppercase tracking-wide text-zinc-300">👉 Where to push</div>
                  <ul className="mt-2 space-y-1 text-sm text-zinc-200 list-disc pl-5">
                    {distributionBullets(selected).map((b, i) => (
                      <li key={`${b}-${i}`}>{b}</li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {(selected.what_to_say || selected.founder_mode?.what_to_say)?.trim() ? (
                <div className="rounded-2xl bg-emerald-950/40 ring-1 ring-emerald-500/25 p-4">
                  <div className="text-xs font-semibold uppercase tracking-wide text-emerald-300/90">What you should say</div>
                  <div className="mt-2 text-base font-medium text-zinc-50 leading-snug">
                    {sharpenWhatToSay(selected)}
                  </div>
                </div>
              ) : null}

              <div>
                <div className="text-xs font-semibold text-zinc-300">Belief</div>
                <div className="mt-1 text-sm text-zinc-200">{selected.belief}</div>
              </div>
              <div>
                <div className="text-xs font-semibold text-zinc-300">Why now</div>
                <div className="mt-1 text-sm text-zinc-200">{selected.why_now}</div>
              </div>
              {getWhyItMattersLine(selected) ? (
                <div>
                  <div className="text-xs font-semibold text-zinc-300">Why it matters</div>
                  <div className="mt-1 text-sm text-zinc-200">{getWhyItMattersLine(selected)}</div>
                </div>
              ) : null}
              {getBusinessImpactLine(selected, 220) ? (
                <div>
                  <div className="text-xs font-semibold text-zinc-300">Business impact</div>
                  <div className="mt-1 text-sm text-sky-100/95">{getBusinessImpactLine(selected, 220)}</div>
                </div>
              ) : null}

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
