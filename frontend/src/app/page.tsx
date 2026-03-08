"use client";

import { useState, useEffect, useRef } from "react";
import { ChatSidebar } from "@/components/ChatSidebar";
import { ChatMessage } from "@/components/ChatMessage";
import { ChatInput } from "@/components/ChatInput";

function getApiUrl(): string {
  if (typeof window === "undefined") return process.env.NEXT_PUBLIC_API_URL || "http://localhost/api";
  // Always use relative /api - Next.js rewrites proxy to backend when on port 3000
  return "/api";
}

export default function Home() {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<{ role: string; content: string }[]>([]);
  const [conversations, setConversations] = useState<{ id: string; title: string }[]>([]);
  const [loading, setLoading] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
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

      setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        fullContent += chunk;
        setLoading(false); // Unfreeze input as soon as first chunk arrives (stream may not close)
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          if (last.role === "assistant") {
            next[next.length - 1] = { ...last, content: fullContent };
          }
          return next;
        });
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
                <p className="text-sm text-zinc-500">Start a conversation by typing a message below.</p>
              </div>
            )}
            {messages.map((msg, i) => (
              <ChatMessage key={i} role={msg.role} content={msg.content} />
            ))}
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
