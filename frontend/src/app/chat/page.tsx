"use client";

import { useState, useEffect, useRef, useMemo } from "react";
import { ChatSidebar } from "@/components/ChatSidebar";
import { ChatMessage } from "@/components/ChatMessage";
import { ChatInput } from "@/components/ChatInput";
import { getApiBase } from "@/lib/api";

export type HintType = "mentions" | "coverage" | "narrative" | "sentiment";

export interface SuggestedHint {
  text: string;
  hint_type: HintType;
}

const STEP_PREFIX = "[STEP]";
const LIVE_SEARCH_PENDING = "[LIVE_SEARCH_PENDING]";
const LIVE_SEARCH_DONE = "[LIVE_SEARCH_DONE]";
const LIVE_SEARCH_AVAILABLE = "[LIVE_SEARCH_AVAILABLE]";

export interface PipelineStep {
  label: string;
  detail: string;
}

function parseStepLine(line: string): PipelineStep | null {
  const trimmed = line.trim();
  if (!trimmed.startsWith(STEP_PREFIX)) return null;
  try {
    const json = trimmed.slice(STEP_PREFIX.length);
    const obj = JSON.parse(json) as { label?: string; detail?: string };
    if (obj && typeof obj.label === "string") {
      return { label: obj.label, detail: typeof obj.detail === "string" ? obj.detail : "" };
    }
  } catch {
    // ignore malformed
  }
  return null;
}

function buildSuggestedHints(clients: { name: string; competitors?: string[] }[]): SuggestedHint[] {
  const hints: SuggestedHint[] = [];
  const first = clients[0];
  if (!first?.name) return [];
  const clientName = first.name.trim();
  const competitors = first.competitors ?? [];
  const entities = [clientName, ...competitors].filter(Boolean).slice(0, 3);

  if (entities[0]) {
    hints.push({ text: `Latest articles about ${entities[0]}`, hint_type: "mentions" });
  }
  if (entities[1]) {
    hints.push({ text: `Recent mentions of ${entities[1]}`, hint_type: "mentions" });
  }
  if (entities[2]) {
    hints.push({ text: `Find articles about ${entities[2]}`, hint_type: "mentions" });
  }
  hints.push({ text: `Competitor coverage for ${clientName}`, hint_type: "coverage" });
  hints.push({ text: `Narrative positioning for ${clientName}`, hint_type: "narrative" });
  hints.push({ text: `Sentiment for ${clientName}`, hint_type: "sentiment" });
  return hints.slice(0, 6);
}

export default function ChatPage() {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<{ role: string; content: string }[]>([]);
  const [conversations, setConversations] = useState<{ id: string; title: string }[]>([]);
  const [loading, setLoading] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [responseSteps, setResponseSteps] = useState<PipelineStep[]>([]);
  const [liveSearchPending, setLiveSearchPending] = useState(false);
  const liveSearchPendingAtRef = useRef<number | null>(null);
  const [liveSearchAvailableForLastResponse, setLiveSearchAvailableForLastResponse] = useState(false);
  const [liveSearchButtonBusy, setLiveSearchButtonBusy] = useState(false);
  const lastSearchQueryRef = useRef<string>("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [clients, setClients] = useState<{ name: string; competitors?: string[] }[]>([]);

  const suggestedHints = useMemo(() => buildSuggestedHints(clients), [clients]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${getApiBase()}/clients`);
        if (!res.ok || cancelled) return;
        const data = await res.json();
        if (!cancelled && data.clients?.length) {
          setClients(data.clients);
        }
      } catch {
        // keep default empty
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const scrollToBottom = () => messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });

  const createNewChat = async () => {
    try {
      const res = await fetch(`${getApiBase()}/new-chat`, { method: "POST" });
      if (!res.ok) {
        const errText = await res.text();
        throw new Error(errText || `HTTP ${res.status}`);
      }
      const data = await res.json();
      setConversationId(data.conversation_id);
      setMessages([]);
      setConversations((prev) => [{ id: data.conversation_id, title: "New Chat" }, ...prev]);
    } catch (err) {
      console.error("createNewChat failed:", err);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `Setup error: ${err instanceof Error ? err.message : "Could not create conversation."}\n\nPlease use **http://localhost** (not :3000). Ensure Docker is running: \`docker compose ps\`.`,
        },
      ]);
    }
  };

  const loadHistory = async (convId: string) => {
    const res = await fetch(`${getApiBase()}/history/${convId}`);
    const data = await res.json();
    setConversationId(convId);
    setMessages(data.messages.map((m: { role: string; content: string }) => ({ role: m.role, content: m.content })));
  };

  useEffect(() => {
    createNewChat();
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const sendMessage = async (
    text: string,
    triggerLiveSearch: boolean = false,
    options?: { db_only?: boolean; hint_type?: HintType }
  ) => {
    if (!conversationId || !text.trim()) return;

    if (!triggerLiveSearch) {
      const userMsg = { role: "user", content: text };
      setMessages((prev) => [...prev, userMsg]);
    }
    setLoading(true);
    setResponseSteps([]);
    setLiveSearchPending(false);
    liveSearchPendingAtRef.current = null;
    setLiveSearchButtonBusy(!!triggerLiveSearch);
    if (!triggerLiveSearch) {
      lastSearchQueryRef.current = text;
      setLiveSearchAvailableForLastResponse(false);
    }

    try {
      const res = await fetch(`${getApiBase()}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          conversation_id: conversationId,
          message: text,
          live_search: !!triggerLiveSearch,
          db_only: options?.db_only ?? false,
          hint_type: options?.hint_type ?? null,
        }),
      });

      if (!res.ok) {
        const errText = await res.text();
        throw new Error(errText || `Chat request failed (${res.status})`);
      }
      if (!res.body) throw new Error("No response body");

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let fullContent = "";
      let buffer = "";

      setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          const trimmed = line.trim();
          if (trimmed.includes(LIVE_SEARCH_PENDING)) {
            liveSearchPendingAtRef.current = Date.now();
            setLiveSearchPending(true);
          }
          if (trimmed.includes(LIVE_SEARCH_DONE)) {
            const startedAt = liveSearchPendingAtRef.current;
            const elapsed = startedAt ? Date.now() - startedAt : 0;
            const minMs = 1200;
            const wait = Math.max(0, minMs - elapsed);
            window.setTimeout(() => setLiveSearchPending(false), wait);
            setLiveSearchButtonBusy(false);
          }
          if (trimmed.includes(LIVE_SEARCH_AVAILABLE)) {
            setLiveSearchAvailableForLastResponse(true);
          }
          const clean = line
            .replace(LIVE_SEARCH_PENDING, "")
            .replace(LIVE_SEARCH_DONE, "")
            .replace(LIVE_SEARCH_AVAILABLE, "");
          if (clean.trim() === "" && (trimmed.includes(LIVE_SEARCH_PENDING) || trimmed.includes(LIVE_SEARCH_DONE) || trimmed.includes(LIVE_SEARCH_AVAILABLE))) continue;
          const step = parseStepLine(line);
          if (step) {
            setResponseSteps((prev) => [...prev, step]);
          } else {
            fullContent += clean + "\n";
          }
        }
        setLoading(false);
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          if (last.role === "assistant") {
            next[next.length - 1] = { ...last, content: fullContent };
          }
          return next;
        });
      }
      if (buffer) {
        const trimmed = buffer.trim();
        if (trimmed.includes(LIVE_SEARCH_PENDING)) {
          liveSearchPendingAtRef.current = Date.now();
          setLiveSearchPending(true);
        }
        if (trimmed.includes(LIVE_SEARCH_DONE)) {
          const startedAt = liveSearchPendingAtRef.current;
          const elapsed = startedAt ? Date.now() - startedAt : 0;
          const minMs = 1200;
          const wait = Math.max(0, minMs - elapsed);
          window.setTimeout(() => setLiveSearchPending(false), wait);
          setLiveSearchButtonBusy(false);
        }
        if (trimmed.includes(LIVE_SEARCH_AVAILABLE)) {
          setLiveSearchAvailableForLastResponse(true);
        }
        const clean = buffer
          .replace(LIVE_SEARCH_PENDING, "")
          .replace(LIVE_SEARCH_DONE, "")
          .replace(LIVE_SEARCH_AVAILABLE, "");
        if (clean.trim() !== "" || (trimmed !== LIVE_SEARCH_PENDING && trimmed !== LIVE_SEARCH_DONE && trimmed !== LIVE_SEARCH_AVAILABLE)) {
          const step = parseStepLine(buffer);
          if (step) {
            setResponseSteps((prev) => [...prev, step]);
          } else {
            fullContent += clean;
          }
          setMessages((prev) => {
            const next = [...prev];
            const last = next[next.length - 1];
            if (last.role === "assistant") {
              next[next.length - 1] = { ...last, content: fullContent };
            }
            return next;
          });
        }
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `Error: ${err instanceof Error ? err.message : "Unknown error"}` },
      ]);
    } finally {
      setLoading(false);
      setLiveSearchButtonBusy(false);
      window.setTimeout(() => setLiveSearchPending(false), 0);
    }
  };

  return (
    <div className="flex h-[calc(100vh-var(--ai-nav-height)-2rem)] min-h-[400px] rounded-2xl border border-[var(--ai-border)] bg-[var(--ai-surface)] overflow-hidden">
      <ChatSidebar
        conversations={conversations}
        onNewChat={createNewChat}
        onSelectConversation={loadHistory}
        isOpen={sidebarOpen}
        onToggle={() => setSidebarOpen(!sidebarOpen)}
      />

      <main className="flex flex-col flex-1 overflow-hidden">
        <div className="flex-1 overflow-y-auto px-4 pb-4">
          <div className="max-w-3xl mx-auto py-8">
            {messages.length === 0 && (
              <div className="text-center text-[var(--ai-muted)] py-16">
                <h2 className="text-xl font-semibold mb-2 text-[var(--ai-text)]">How can I help you today?</h2>
                <p className="text-sm mb-4">Answers from your monitored sources only. Try one of these:</p>
                <div className="flex flex-wrap justify-center gap-2 max-w-2xl mx-auto">
                  {suggestedHints.map((h, i) => (
                    <button
                      key={i}
                      type="button"
                      onClick={() => sendMessage(h.text, false, { db_only: true, hint_type: h.hint_type })}
                      disabled={loading}
                      className="px-3 py-2 rounded-xl text-sm font-medium border border-[var(--ai-border)] bg-[var(--ai-surface)] text-[var(--ai-text-secondary)] hover:bg-[var(--ai-surface-hover)] hover:text-[var(--ai-text)] hover:border-[var(--ai-accent)]/40 transition-colors disabled:opacity-50"
                    >
                      {h.text}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {messages.slice(0, -1).map((msg, i) => (
              <ChatMessage key={i} role={msg.role} content={msg.content} />
            ))}
            {messages.length > 0 && (() => {
              const last = messages[messages.length - 1];
              const isAssistant = last.role === "assistant";
              const showSteps = isAssistant && responseSteps.length > 0;
              return (
                <>
                  {showSteps && (
                    <div className="rounded-lg border border-amber-500/30 bg-amber-950/20 px-4 py-3 mb-2 text-left">
                      <p className="text-xs font-medium text-amber-400/90 mb-2">Pipeline steps</p>
                      <ol className="list-decimal list-inside space-y-1 text-sm text-[var(--ai-muted)]">
                        {responseSteps.map((s, idx) => (
                          <li key={idx}>
                            <span className="text-[var(--ai-text-secondary)]">{s.label}</span>
                            {s.detail && <span className="text-[var(--ai-muted)]"> — {s.detail}</span>}
                          </li>
                        ))}
                      </ol>
                    </div>
                  )}
                  {liveSearchPending && (
                    <div className="flex items-center gap-2 py-3 px-4 rounded-lg bg-amber-950/30 border border-amber-500/20 text-amber-400 text-sm mb-2">
                      <span>Searching for the latest articles</span>
                      <span className="animate-pulse" aria-hidden>...</span>
                    </div>
                  )}
                  <ChatMessage key={messages.length - 1} role={last.role} content={last.content} />
                  {liveSearchAvailableForLastResponse && last.role === "assistant" && (
                    <div className="mt-3 mb-2 p-4 rounded-lg border border-sky-500/30 bg-sky-950/20">
                      <p className="text-sm text-sky-200/90 mb-2">
                        Search the web for newer results. This may take <strong>30–40 seconds</strong>. Results may include duplicates, but this ensures you don&apos;t miss anything.
                      </p>
                      <button
                        type="button"
                        disabled={loading || liveSearchPending || liveSearchButtonBusy}
                        onClick={() => sendMessage(lastSearchQueryRef.current || "", true)}
                        className="px-4 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 disabled:bg-sky-900/40 disabled:text-sky-200/60 disabled:cursor-not-allowed text-white text-sm font-medium transition-colors"
                      >
                        {loading || liveSearchPending || liveSearchButtonBusy ? "Searching the web…" : "Search the web for newer results"}
                      </button>
                      {(loading || liveSearchPending || liveSearchButtonBusy) && (
                        <p className="text-xs text-sky-200/70 mt-2">
                          Live search is running now. When it finishes, you&apos;ll either see new results or a message that nothing new was found.
                        </p>
                      )}
                    </div>
                  )}
                </>
              );
            })()}
            {loading && messages[messages.length - 1]?.role === "user" && (
              <ChatMessage role="assistant" content="..." />
            )}
            <div ref={messagesEndRef} />
          </div>
        </div>

        <div className="border-t border-[var(--ai-border)] p-4">
          {suggestedHints.length > 0 && (
            <div className="flex flex-wrap gap-2 mb-3">
              {suggestedHints.map((h, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => sendMessage(h.text, false, { db_only: true, hint_type: h.hint_type })}
                  disabled={loading}
                  className="px-2.5 py-1.5 rounded-lg text-xs font-medium border border-[var(--ai-border)] bg-[var(--ai-surface)] text-[var(--ai-text-secondary)] hover:bg-[var(--ai-surface-hover)] hover:text-[var(--ai-text)] transition-colors disabled:opacity-50"
                >
                  {h.text}
                </button>
              ))}
            </div>
          )}
          <ChatInput onSend={(text) => sendMessage(text)} disabled={loading} />
        </div>
      </main>
    </div>
  );
}
