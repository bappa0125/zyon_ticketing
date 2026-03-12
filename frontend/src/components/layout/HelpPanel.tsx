"use client";

import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { getPageHelp } from "@/config/pageHelpContent";

export function HelpPanel() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [expandedSection, setExpandedSection] = useState<number | null>(0);
  const help = getPageHelp(pathname || "/");

  useEffect(() => {
    setOpen(false);
    setExpandedSection(0);
  }, [pathname]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (!help) {
    return (
      <>
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="fixed right-4 top-24 z-40 flex h-11 w-11 items-center justify-center rounded-xl border border-[var(--ai-border-strong)] bg-[var(--ai-surface)] text-[var(--ai-muted)] shadow-lg transition-all duration-200 hover:border-[var(--ai-accent)] hover:bg-[var(--ai-surface-hover)] hover:text-[var(--ai-accent)] md:right-6"
          aria-label="Help"
        >
          <span className="text-lg font-semibold">?</span>
        </button>
        {open && (
          <HelpOverlay onClose={() => setOpen(false)}>
            <p className="text-sm text-[var(--ai-text-secondary)]">
              No help for this page yet. Open Dashboard, Topics, Reputation, or Alerts for guided help.
            </p>
          </HelpOverlay>
        )}
      </>
    );
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="fixed right-4 top-24 z-40 flex items-center gap-2 rounded-xl border border-[var(--ai-border-strong)] bg-[var(--ai-surface)] px-3 py-2.5 text-sm font-medium text-[var(--ai-accent)] shadow-lg transition-all duration-200 hover:border-[var(--ai-accent)] hover:bg-[var(--ai-surface-hover)] md:right-6"
        aria-expanded={open}
        aria-controls="app-help-panel"
      >
        <span className="hidden sm:inline">Help</span>
        <span className="text-base font-semibold" aria-hidden>?</span>
      </button>

      <div
        className={`fixed inset-0 z-40 bg-black/50 backdrop-blur-sm transition-opacity duration-300 ${
          open ? "opacity-100 pointer-events-auto" : "opacity-0 pointer-events-none"
        }`}
        aria-hidden={!open}
        onClick={() => setOpen(false)}
      />

      <aside
        id="app-help-panel"
        className={`fixed right-0 top-0 z-50 flex h-full w-full max-w-[var(--ai-help-width)] flex-col border-l border-[var(--ai-border)] bg-[var(--ai-bg-elevated)] shadow-2xl transition-transform duration-300 ease-out sm:max-w-md ${
          open ? "translate-x-0" : "translate-x-full"
        }`}
      >
        <div className="flex shrink-0 items-center justify-between border-b border-[var(--ai-border)] bg-[var(--ai-surface)] px-4 py-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-[var(--ai-accent)]">
              Guide
            </p>
            <h2 className="text-lg font-semibold text-[var(--ai-text)]">{help.title}</h2>
          </div>
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="rounded-lg p-2 text-[var(--ai-muted)] hover:bg-[var(--ai-surface-hover)] hover:text-[var(--ai-text)]"
            aria-label="Close help"
          >
            <span className="text-xl leading-none">&times;</span>
          </button>
        </div>
        <div className="help-panel-scroll flex-1 overflow-y-auto px-4 py-4">
          <p className="mb-5 text-sm leading-relaxed text-[var(--ai-text-secondary)]">
            {help.summary}
          </p>
          {help.sections.map((section, i) => {
            const isExpanded = expandedSection === i;
            return (
              <div
                key={i}
                className="mb-4 overflow-hidden rounded-xl border border-[var(--ai-border)] bg-[var(--ai-surface)]"
              >
                <button
                  type="button"
                  onClick={() => setExpandedSection(isExpanded ? null : i)}
                  className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-semibold text-[var(--ai-text)] hover:bg-[var(--ai-surface-hover)]"
                >
                  <span>{section.sectionTitle}</span>
                  <span className="text-[var(--ai-muted)] transition-transform duration-200" style={{ transform: isExpanded ? "rotate(180deg)" : "rotate(0deg)" }}>
                    ▼
                  </span>
                </button>
                {isExpanded && (
                  <div className="border-t border-[var(--ai-border)] px-4 pb-4 pt-3 animate-ai-fade-in">
                    <div className="space-y-4 text-sm">
                      <div>
                        <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-[var(--ai-muted)]">What it is</h4>
                        <div className="leading-relaxed text-[var(--ai-text-secondary)] [&_strong]:text-[var(--ai-text)]">
                          {section.whatItIs}
                        </div>
                      </div>
                      {section.howToInterpret && (
                        <div>
                          <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-[var(--ai-muted)]">How to interpret</h4>
                          <div className="leading-relaxed text-[var(--ai-text-secondary)] [&_strong]:text-[var(--ai-text)]">
                            {section.howToInterpret}
                          </div>
                        </div>
                      )}
                      {section.controls && section.controls.length > 0 && (
                        <div>
                          <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-[var(--ai-muted)]">Controls</h4>
                          <ul className="space-y-2">
                            {section.controls.map((c, j) => (
                              <li key={j}>
                                <span className="font-medium text-[var(--ai-accent)]">{c.name}</span>
                                <span className="text-[var(--ai-text-secondary)]"> — {c.howToUse}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                      <div>
                        <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-[var(--ai-accent)]">PR agency use</h4>
                        <div className="leading-relaxed text-[var(--ai-text-secondary)] [&_strong]:text-[var(--ai-text)]">
                          {section.prAgencyUse}
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </aside>
    </>
  );
}

function HelpOverlay({
  children,
  onClose,
}: {
  children: React.ReactNode;
  onClose: () => void;
}) {
  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm" aria-hidden onClick={onClose} />
      <div className="fixed right-4 top-1/2 z-50 w-full max-w-sm -translate-y-1/2 rounded-2xl border border-[var(--ai-border)] bg-[var(--ai-surface)] p-4 shadow-xl sm:right-8">
        {children}
        <button type="button" onClick={onClose} className="mt-4 w-full rounded-xl border border-[var(--ai-border-strong)] bg-[var(--ai-surface-hover)] px-4 py-2.5 text-sm font-medium text-[var(--ai-text)]">
          Close
        </button>
      </div>
    </>
  );
}
