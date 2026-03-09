"use client";

import { useState, useEffect, useRef } from "react";
import { ChatSidebar } from "@/components/ChatSidebar";
import { ChatMessage } from "@/components/ChatMessage";
import { ChatInput } from "@/components/ChatInput";

const STEP_PREFIX = "[STEP]";

export interface PipelineStep {
  label: string;
  detail: string;
}

function getApiUrl(): string {
  if (typeof window === "undefined") return process.env.NEXT_PUBLIC_API_URL || "http://localhost/api";
  return "/api";
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

export default function Home() {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<{ role: string; content: string }[]>([]);
  const [conversations, setConversations] = useState<{ id: string; title: string }[]>([]);
  const [loading, setLoading] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [responseSteps, setResponseSteps] = useState<PipelineStep[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });

  const createNewChat = async () => {
    try {
      const res = await fetch(`${getApiUrl()}/new-chat`, { method: "POST" });
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
    const res = await fetch(`${getApiUrl()}/history/${convId}`);
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

  const sendMessage = async (text: string) => {
    if (!conversationId || !text.trim()) return;

    const userMsg = { role: "user", content: text };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);
    setResponseSteps([]);

    try {
      const res = await fetch(`${getApiUrl()}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ conversation_id: conversationId, message: text }),
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
          const step = parseStepLine(line);
          if (step) {
            setResponseSteps((prev) => [...prev, step]);
          } else {
            fullContent += line + "\n";
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
        const step = parseStepLine(buffer);
        if (step) {
          setResponseSteps((prev) => [...prev, step]);
        } else {
          fullContent += buffer;
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
    }
  };

  return (
    <div className="flex h-screen bg-[var(--background)]">
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
              <div className="text-center text-muted py-16">
                <h2 className="text-xl font-semibold mb-2">How can I help you today?</h2>
                <p className="text-sm text-zinc-500 mb-4">I can find articles and mentions about monitored companies. Try asking:</p>
                <ul className="text-sm text-zinc-400 space-y-1 max-w-md mx-auto text-left list-disc list-inside">
                  <li>Give me the latest articles about Sahi</li>
                  <li>Show me recent mentions of Zerodha</li>
                  <li>Find articles about Upstox</li>
                  <li>Latest news on Groww</li>
                </ul>
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
                      <ol className="list-decimal list-inside space-y-1 text-sm text-zinc-400">
                        {responseSteps.map((s, idx) => (
                          <li key={idx}>
                            <span className="text-zinc-300">{s.label}</span>
                            {s.detail && <span className="text-zinc-500"> — {s.detail}</span>}
                          </li>
                        ))}
                      </ol>
                    </div>
                  )}
                  <ChatMessage key={messages.length - 1} role={last.role} content={last.content} />
                </>
              );
            })()}
            {loading && messages[messages.length - 1]?.role === "user" && (
              <ChatMessage role="assistant" content="..." />
            )}
            <div ref={messagesEndRef} />
          </div>
        </div>

        <div className="border-t border-zinc-800 p-4">
          <ChatInput onSend={sendMessage} disabled={loading} />
        </div>
      </main>
    </div>
  );
}
