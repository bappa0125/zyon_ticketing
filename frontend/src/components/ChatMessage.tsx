"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface ChatMessageProps {
  role: string;
  content: string;
}

export function ChatMessage({ role, content }: ChatMessageProps) {
  const isUser = role === "user";

  return (
    <div className={`flex gap-4 py-4 ${isUser ? "justify-end" : ""}`}>
      {!isUser && (
        <div className="w-8 h-8 rounded-full bg-zinc-700 flex items-center justify-center text-sm shrink-0">
          AI
        </div>
      )}

      <div
        className={`min-w-0 max-w-[85%] overflow-hidden rounded-xl border transition-colors ${
          isUser
            ? "border-zinc-700 bg-zinc-800 px-4 py-3 text-white"
            : "border-zinc-700/80 bg-zinc-900/60 px-4 py-3 text-zinc-200 hover:border-zinc-600"
        }`}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap break-words">{content}</p>
        ) : (
          <div className="chat-message-content prose prose-invert prose-sm max-w-none break-words prose-pre:bg-zinc-900 prose-pre:rounded-lg prose-pre:p-4 prose-code:bg-zinc-800 prose-code:px-1 prose-code:rounded [&_a]:text-sky-400 [&_a]:hover:text-sky-300 [&_strong]:text-zinc-100 [&_hr]:border-zinc-600 [&_hr]:my-4 prose-p:text-zinc-300 prose-p:leading-relaxed prose-p:my-2">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
          </div>
        )}
      </div>

      {isUser && (
        <div className="w-8 h-8 rounded-full bg-zinc-600 flex items-center justify-center text-sm shrink-0">
          U
        </div>
      )}
    </div>
  );
}
