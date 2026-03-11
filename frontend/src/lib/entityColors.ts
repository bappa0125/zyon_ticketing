/**
 * Consistent entity color mapping across the site.
 * Sahi (client): green; Zerodha: red; Kotak: amber; Dhan: sky; others: distinct.
 */
export const ENTITY_COLORS: Record<string, { hex: string; bg: string; text: string }> = {
  Sahi: { hex: "#10b981", bg: "bg-emerald-500/20", text: "text-emerald-400" },
  Zerodha: { hex: "#f43f5e", bg: "bg-rose-500/20", text: "text-rose-400" },
  "Kotak Securities": { hex: "#f59e0b", bg: "bg-amber-500/20", text: "text-amber-400" },
  Dhan: { hex: "#0ea5e9", bg: "bg-sky-500/20", text: "text-sky-400" },
  Groww: { hex: "#8b5cf6", bg: "bg-violet-500/20", text: "text-violet-400" },
  "Angel One": { hex: "#6366f1", bg: "bg-indigo-500/20", text: "text-indigo-400" },
  Upstox: { hex: "#d946ef", bg: "bg-fuchsia-500/20", text: "text-fuchsia-400" },
  Fyers: { hex: "#14b8a6", bg: "bg-teal-500/20", text: "text-teal-400" },
  "ICICI Direct": { hex: "#38bdf8", bg: "bg-sky-400/20", text: "text-sky-300" },
  "HDFC Securities": { hex: "#84cc16", bg: "bg-lime-500/20", text: "text-lime-400" },
  "5paisa": { hex: "#eab308", bg: "bg-yellow-500/20", text: "text-yellow-400" },
  "Alice Blue": { hex: "#06b6d4", bg: "bg-cyan-500/20", text: "text-cyan-400" },
};

const FALLBACK_COLORS = [
  { hex: "#64748b", bg: "bg-slate-500/20", text: "text-slate-400" },
  { hex: "#a855f7", bg: "bg-purple-500/20", text: "text-purple-400" },
  { hex: "#fb923c", bg: "bg-orange-400/20", text: "text-orange-400" },
  { hex: "#22d3ee", bg: "bg-cyan-400/20", text: "text-cyan-300" },
  { hex: "#4ade80", bg: "bg-green-400/20", text: "text-green-400" },
];

function hash(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h << 5) - h + s.charCodeAt(i) | 0;
  return Math.abs(h);
}

export function getEntityColor(entity: string): { hex: string; bg: string; text: string } {
  const key = Object.keys(ENTITY_COLORS).find((k) => k.toLowerCase() === (entity || "").toLowerCase());
  if (key) return ENTITY_COLORS[key];
  const idx = hash(entity || "other") % FALLBACK_COLORS.length;
  return FALLBACK_COLORS[idx];
}

export function getEntityHex(entity: string): string {
  return getEntityColor(entity).hex;
}

export function getEntityTailwindBg(entity: string): string {
  return getEntityColor(entity).bg;
}

export function getEntityTailwindText(entity: string): string {
  return getEntityColor(entity).text;
}
