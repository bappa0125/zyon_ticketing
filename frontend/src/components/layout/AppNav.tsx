"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, useRef, useEffect } from "react";

type NavLink = { href: string; label: string };
type NavGroup = { label: string; items: NavLink[] };

const NAV_STRUCTURE: (NavLink | NavGroup)[] = [
  { href: "/", label: "Home" },
  { href: "/chat", label: "Chat" },
  {
    label: "Pulse",
    items: [
      { href: "/dashboard", label: "Dashboard" },
      { href: "/topics", label: "Topics" },
      { href: "/reputation", label: "Reputation" },
      { href: "/alerts", label: "Alerts" },
      { href: "/sentiment", label: "Sentiment" },
    ],
  },
  {
    label: "Media",
    items: [
      { href: "/media-intelligence", label: "Media Intel" },
      { href: "/coverage", label: "Coverage" },
      { href: "/media", label: "Media" },
    ],
  },
  {
    label: "Action",
    items: [
      { href: "/targets", label: "Targets" },
      { href: "/opportunities", label: "Opportunities" },
      { href: "/pr-intelligence", label: "PR Intelligence" },
    ],
  },
  { href: "/clients", label: "Clients" },
  {
    label: "Social",
    items: [
      { href: "/social", label: "Social" },
      { href: "/social/narrative-shift", label: "Narrative Shift" },
    ],
  },
];

function isGroup(item: NavLink | NavGroup): item is NavGroup {
  return "items" in item && Array.isArray((item as NavGroup).items);
}

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(href + "/");
}

function isGroupActive(pathname: string, group: NavGroup): boolean {
  return group.items.some((l) => isActive(pathname, l.href));
}

export function AppNav() {
  const pathname = usePathname() || "/";
  const [mobileOpen, setMobileOpen] = useState(false);
  const [openDropdown, setOpenDropdown] = useState<string | null>(null);
  const navRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!mobileOpen) setOpenDropdown(null);
  }, [mobileOpen]);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      const target = e.target as Node;
      if (!openDropdown) return;
      if (navRef.current && !navRef.current.contains(target)) {
        setOpenDropdown(null);
      }
    }
    document.addEventListener("click", handleClickOutside, true);
    return () => document.removeEventListener("click", handleClickOutside, true);
  }, [openDropdown]);

  return (
    <header
      className="sticky top-0 z-30 overflow-visible ai-glass border-b border-[var(--ai-border)] transition-shadow duration-300"
      style={{ minHeight: "var(--ai-nav-height)" }}
    >
      <div className="relative mx-auto flex h-14 max-w-[var(--ai-max-content)] items-center justify-between gap-4 px-4 md:h-[var(--ai-nav-height)] md:px-6">
        <Link
          href="/"
          className="nav-logo shrink-0 text-lg font-bold tracking-tight text-[var(--ai-text)] transition-colors duration-200 hover:text-[var(--ai-accent)]"
        >
          Zyon{" "}
          <span className="bg-gradient-to-r from-[var(--ai-accent)] to-[var(--ai-gradient-end)] bg-clip-text font-semibold text-transparent">
            AI
          </span>
        </Link>

        {/* Desktop: grouped nav with dropdowns */}
        <nav
          ref={navRef}
          className="nav-desktop-scroll hidden flex-1 justify-center overflow-visible md:flex"
          aria-label="Main"
        >
          <ul className="flex items-center justify-center gap-0.5 py-2 lg:gap-1 overflow-visible">
            {NAV_STRUCTURE.map((item) => {
              if (isGroup(item)) {
                const active = isGroupActive(pathname, item);
                const isOpen = openDropdown === item.label;
                return (
                  <li key={item.label} className="relative shrink-0">
                    <button
                      type="button"
                      onClick={() => setOpenDropdown(isOpen ? null : item.label)}
                      className={`nav-link relative flex items-center gap-1 rounded-lg px-2.5 py-2 text-sm font-medium transition-all duration-200 lg:px-3 ${
                        active
                          ? "text-[var(--ai-accent)]"
                          : "text-[var(--ai-text-secondary)] hover:bg-[var(--ai-surface)] hover:text-[var(--ai-text)]"
                      }`}
                      aria-expanded={isOpen}
                      aria-haspopup="true"
                    >
                      {item.label}
                      <svg
                        className={`h-3.5 w-3.5 transition-transform ${isOpen ? "rotate-180" : ""}`}
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                        aria-hidden
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                      </svg>
                      {active && (
                        <span
                          className="absolute bottom-0 left-1/2 h-0.5 w-6 -translate-x-1/2 rounded-full bg-gradient-to-r from-[var(--ai-accent)] to-[var(--ai-gradient-end)]"
                          aria-hidden
                        />
                      )}
                    </button>
                    {isOpen && (
                      <div
                        className="absolute left-1/2 top-full z-[100] mt-1 min-w-[10rem] -translate-x-1/2 rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)] py-1 shadow-xl whitespace-nowrap"
                        role="menu"
                      >
                        {item.items.map((link) => {
                          const linkActive = isActive(pathname, link.href);
                          return (
                            <Link
                              key={link.href}
                              href={link.href}
                              onClick={() => setOpenDropdown(null)}
                              className={`block px-4 py-2.5 text-sm transition-colors ${
                                linkActive
                                  ? "bg-[var(--ai-accent-dim)] text-[var(--ai-accent)]"
                                  : "text-[var(--ai-text-secondary)] hover:bg-[var(--ai-surface-hover)] hover:text-[var(--ai-text)]"
                              }`}
                              role="menuitem"
                            >
                              {link.label}
                            </Link>
                          );
                        })}
                      </div>
                    )}
                  </li>
                );
              }
              const active = isActive(pathname, item.href);
              return (
                <li key={item.href} className="shrink-0">
                  <Link
                    href={item.href}
                    className={`nav-link relative rounded-lg px-2.5 py-2 text-sm font-medium transition-all duration-200 lg:px-3 ${
                      active
                        ? "text-[var(--ai-accent)]"
                        : "text-[var(--ai-text-secondary)] hover:bg-[var(--ai-surface)] hover:text-[var(--ai-text)]"
                    }`}
                  >
                    {item.label}
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

        {/* Mobile: hamburger */}
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

      {/* Mobile menu: grouped sections */}
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
              {NAV_STRUCTURE.map((item) => {
                if (isGroup(item)) {
                  return (
                    <li key={item.label} className="col-span-2 sm:col-span-3 pt-2 first:pt-0">
                      <p className="text-xs font-semibold uppercase tracking-wider text-[var(--ai-muted)] px-2 mb-1.5">
                        {item.label}
                      </p>
                      <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                        {item.items.map((link) => {
                          const active = isActive(pathname, link.href);
                          return (
                            <li key={link.href}>
                              <Link
                                href={link.href}
                                onClick={() => setMobileOpen(false)}
                                className={`block rounded-xl px-3 py-2.5 text-sm font-medium transition-all duration-200 ${
                                  active
                                    ? "bg-[var(--ai-accent-dim)] text-[var(--ai-accent)]"
                                    : "text-[var(--ai-text-secondary)] hover:bg-[var(--ai-surface)] hover:text-[var(--ai-text)]"
                                }`}
                              >
                                {link.label}
                              </Link>
                            </li>
                          );
                        })}
                      </ul>
                    </li>
                  );
                }
                const active = isActive(pathname, item.href);
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      onClick={() => setMobileOpen(false)}
                      className={`block rounded-xl px-3 py-2.5 text-sm font-medium transition-all duration-200 ${
                        active
                          ? "bg-[var(--ai-accent-dim)] text-[var(--ai-accent)]"
                          : "text-[var(--ai-text-secondary)] hover:bg-[var(--ai-surface)] hover:text-[var(--ai-text)]"
                      }`}
                    >
                      {item.label}
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
