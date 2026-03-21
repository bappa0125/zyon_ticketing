"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/**
 * Second-level tabs for CXO surfaces only (not on `/reports/pr` PR dashboard).
 */
export default function ReportsLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() || "";
  const showCxoTabs =
    pathname === "/reports/executive-report" || pathname.startsWith("/reports/executive-report/")
      ? true
      : pathname === "/reports/narrative-briefing" || pathname.startsWith("/reports/narrative-briefing/");

  return (
    <div>
      {showCxoTabs && (
        <div className="border-b border-[var(--ai-border)] bg-[var(--ai-surface)]">
          <div className="max-w-5xl mx-auto px-6 pt-4 flex flex-wrap items-end justify-between gap-3">
            <p className="text-xs font-medium uppercase tracking-wider text-[var(--ai-muted)] mb-2 w-full sm:w-auto">Executive CXO</p>
            <Link
              href="/reports/pr"
              className="text-xs text-[var(--ai-text-secondary)] hover:text-[var(--ai-accent)] mb-2 sm:mb-0 whitespace-nowrap"
            >
              PR dashboard →
            </Link>
          </div>
          <div className="max-w-5xl mx-auto px-6">
            <nav className="flex gap-2 -mb-px" aria-label="Executive report sections">
              <Link
                href="/reports/executive-report"
                className={`px-4 py-2.5 text-sm font-medium rounded-t-lg border border-b-0 transition-colors ${
                  pathname.includes("executive-report")
                    ? "border-[var(--ai-border)] bg-[var(--ai-bg)] text-[var(--ai-accent)]"
                    : "border-transparent text-[var(--ai-text-secondary)] hover:text-[var(--ai-text)] hover:bg-[var(--ai-bg-elevated)]"
                }`}
              >
                Intelligence tables
              </Link>
              <Link
                href="/reports/narrative-briefing"
                className={`px-4 py-2.5 text-sm font-medium rounded-t-lg border border-b-0 transition-colors ${
                  pathname.includes("narrative-briefing")
                    ? "border-[var(--ai-border)] bg-[var(--ai-bg)] text-[var(--ai-accent)]"
                    : "border-transparent text-[var(--ai-text-secondary)] hover:text-[var(--ai-text)] hover:bg-[var(--ai-bg-elevated)]"
                }`}
              >
                Narrative briefing
              </Link>
            </nav>
          </div>
        </div>
      )}
      {children}
    </div>
  );
}
