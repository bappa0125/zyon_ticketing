"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

const NAV_LINKS = [
  { href: "/", label: "Chat" },
  { href: "/dashboard", label: "Dashboard" },
  { href: "/topics", label: "Topics" },
  { href: "/reputation", label: "Reputation" },
  { href: "/alerts", label: "Alerts" },
  { href: "/targets", label: "Targets" },
  { href: "/media-intelligence", label: "Media Intel" },
  { href: "/sentiment", label: "Sentiment" },
  { href: "/coverage", label: "Coverage" },
  { href: "/clients", label: "Clients" },
  { href: "/media", label: "Media" },
  { href: "/opportunities", label: "Opportunities" },
  { href: "/social", label: "Social" },
] as const;

export function AppNav() {
  const pathname = usePathname() || "/";
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <header
      className="sticky top-0 z-30 ai-glass border-b border-[var(--ai-border)] transition-shadow duration-300"
      style={{ minHeight: "var(--ai-nav-height)" }}
    >
      <div className="mx-auto flex h-14 max-w-[var(--ai-max-content)] items-center justify-between gap-4 px-4 md:h-[var(--ai-nav-height)] md:px-6">
        <Link
          href="/"
          className="nav-logo shrink-0 text-lg font-bold tracking-tight text-[var(--ai-text)] transition-colors duration-200 hover:text-[var(--ai-accent)]"
        >
          Zyon{" "}
          <span className="bg-gradient-to-r from-[var(--ai-accent)] to-[var(--ai-gradient-end)] bg-clip-text font-semibold text-transparent">
            AI
          </span>
        </Link>

        {/* Desktop: scrollable nav so all items fit */}
        <nav
          className="nav-desktop-scroll hidden flex-1 justify-center overflow-x-auto md:flex"
          aria-label="Main"
        >
          <ul className="flex items-center justify-center gap-0.5 py-2 lg:gap-1">
            {NAV_LINKS.map(({ href, label }) => {
              const active = pathname === href || (href !== "/" && pathname.startsWith(href));
              return (
                <li key={href} className="shrink-0">
                  <Link
                    href={href}
                    className={`nav-link relative rounded-lg px-2.5 py-2 text-sm font-medium transition-all duration-200 lg:px-3 ${
                      active
                        ? "nav-link-active text-[var(--ai-accent)]"
                        : "text-[var(--ai-text-secondary)] hover:bg-[var(--ai-surface)] hover:text-[var(--ai-text)]"
                    }`}
                  >
                    {label}
                    {active && (
                      <span
                        className="absolute bottom-0 left-1/2 h-0.5 w-6 -translate-x-1/2 rounded-full bg-gradient-to-r from-[var(--ai-accent)] to-[var(--ai-gradient-end)]"
                        aria-hidden
                      />
                    )}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>

        {/* Mobile: hamburger with animation */}
        <button
          type="button"
          className="nav-hamburger flex h-10 w-10 shrink-0 flex-col items-center justify-center gap-1.5 rounded-xl border border-[var(--ai-border-strong)] bg-[var(--ai-surface)] transition-colors hover:bg-[var(--ai-surface-hover)] md:hidden"
          onClick={() => setMobileOpen((o) => !o)}
          aria-expanded={mobileOpen}
          aria-controls="mobile-nav"
          aria-label={mobileOpen ? "Close menu" : "Open menu"}
        >
          <span
            className={`h-0.5 w-5 rounded-full bg-[var(--ai-text)] transition-all duration-300 ${
              mobileOpen ? "translate-y-2 rotate-45" : ""
            }`}
          />
          <span
            className={`h-0.5 w-5 rounded-full bg-[var(--ai-text)] transition-all duration-300 ${
              mobileOpen ? "opacity-0 scale-x-0" : ""
            }`}
          />
          <span
            className={`h-0.5 w-5 rounded-full bg-[var(--ai-text)] transition-all duration-300 ${
              mobileOpen ? "-translate-y-2 -rotate-45" : ""
            }`}
          />
        </button>
      </div>

      {/* Mobile menu: slide down with staggered links */}
      <div
        id="mobile-nav"
        className={`grid transition-all duration-300 ease-out md:hidden ${
          mobileOpen ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0"
        }`}
      >
        <div className="overflow-hidden">
          <nav
            className="border-t border-[var(--ai-border)] bg-[var(--ai-bg-elevated)]"
            aria-label="Main mobile"
          >
            <ul
              key={mobileOpen ? "open" : "closed"}
              className="nav-mobile-stagger mx-auto max-w-[var(--ai-max-content)] grid grid-cols-2 gap-2 px-4 py-4 sm:grid-cols-3"
            >
              {NAV_LINKS.map(({ href, label }) => {
                const active = pathname === href || (href !== "/" && pathname.startsWith(href));
                return (
                  <li key={href}>
                    <Link
                      href={href}
                      onClick={() => setMobileOpen(false)}
                      className={`block rounded-xl px-3 py-2.5 text-sm font-medium transition-all duration-200 ${
                        active
                          ? "bg-[var(--ai-accent-dim)] text-[var(--ai-accent)]"
                          : "text-[var(--ai-text-secondary)] hover:bg-[var(--ai-surface)] hover:text-[var(--ai-text)]"
                      }`}
                    >
                      {label}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </nav>
        </div>
      </div>
    </header>
  );
}
