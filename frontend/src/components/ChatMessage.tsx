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
        className={`max-w-[85%] rounded-lg px-4 py-3 ${
          isUser ? "bg-zinc-700 text-white" : "bg-zinc-800/80 text-zinc-200"
        }`}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap">{content}</p>
        ) : (
          <div className="prose prose-invert prose-sm max-w-none prose-pre:bg-zinc-900 prose-pre:rounded-lg prose-pre:p-4 prose-code:bg-zinc-800 prose-code:px-1 prose-code:rounded">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {content}
            </ReactMarkdown>
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
