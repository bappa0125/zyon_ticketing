"use client";

interface ChatSidebarProps {
  conversations: { id: string; title: string }[];
  onNewChat: () => void;
  onSelectConversation: (id: string) => void;
  isOpen: boolean;
  onToggle: () => void;
}

export function ChatSidebar({
  conversations,
  onNewChat,
  onSelectConversation,
  isOpen,
  onToggle,
}: ChatSidebarProps) {
  return (
    <>
      <button
        onClick={onToggle}
        className="fixed left-4 top-4 z-50 p-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300 lg:hidden"
      >
        {isOpen ? "←" : "☰"}
      </button>

      <aside
        className={`fixed lg:relative inset-y-0 left-0 z-40 w-64 bg-zinc-950 border-r border-zinc-800 transform transition-transform lg:transform-none ${
          isOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex flex-col h-full">
          <div className="p-4 border-b border-zinc-800">
            <h1 className="font-semibold text-lg">Zyon Chat</h1>
            <button
              onClick={onNewChat}
              className="mt-3 w-full py-2 px-3 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-sm font-medium transition-colors"
            >
              + New Chat
            </button>
          </div>

          <div className="flex-1 overflow-y-auto py-2">
            {conversations.map((c) => (
              <button
                key={c.id}
                onClick={() => onSelectConversation(c.id)}
                className="w-full text-left px-4 py-2 text-sm text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200 truncate"
              >
                {c.title}
              </button>
            ))}
          </div>
        </div>
      </aside>

      {isOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-30 lg:hidden"
          onClick={onToggle}
        />
      )}
    </>
  );
}
