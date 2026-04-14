"use client";

import type { Conversation } from "@/types/chat";
import { formatDate } from "@/lib/utils";

interface SidebarProps {
  conversations: Conversation[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNewChat: () => void;
  onClose: () => void;
}

export function Sidebar({
  conversations,
  activeId,
  onSelect,
  onNewChat,
  onClose,
}: SidebarProps) {
  return (
    <aside
      className="flex flex-col h-full border-r"
      style={{
        width: "var(--sidebar-width)",
        minWidth: "var(--sidebar-width)",
        borderColor: "var(--border)",
        background: "var(--sidebar-bg)",
      }}
    >
      {/* Header + New Chat */}
      <div className="p-3 space-y-2">
        <div className="flex items-center justify-between px-1">
          <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--muted-foreground)" }}>
            Conversations
          </span>
        </div>
        <button
          onClick={onNewChat}
          className="w-full flex items-center justify-center gap-2 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 hover:shadow-md active:scale-[0.98] gradient-bg text-white"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          New Chat
        </button>
      </div>

      {/* Conversation List */}
      <div className="flex-1 overflow-y-auto px-2 pb-2">
        {conversations.length === 0 ? (
          <div className="text-center py-12 px-4">
            <div className="w-12 h-12 rounded-2xl gradient-bg flex items-center justify-center mx-auto mb-3 opacity-60">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
              </svg>
            </div>
            <p className="text-sm font-medium" style={{ color: "var(--muted-foreground)" }}>
              No conversations yet
            </p>
            <p className="text-xs mt-1" style={{ color: "var(--muted-foreground)", opacity: 0.7 }}>
              Start a new chat to begin
            </p>
          </div>
        ) : (
          <div className="space-y-1">
            {conversations.map((conv) => (
              <button
                key={conv.id}
                onClick={() => onSelect(conv.id)}
                className={`w-full text-left px-3 py-2.5 rounded-xl text-sm transition-all duration-200 group ${
                  activeId === conv.id
                    ? "font-medium shadow-sm"
                    : "hover:bg-[var(--muted)]"
                }`}
                style={
                  activeId === conv.id
                    ? { background: "var(--accent)", color: "var(--accent-foreground)" }
                    : {}
                }
              >
                <div className="flex items-center gap-2">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="shrink-0 opacity-50">
                    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                  </svg>
                  <span className="truncate">{conv.title}</span>
                </div>
                <div
                  className="text-[11px] mt-1 pl-6"
                  style={{ color: "var(--muted-foreground)" }}
                >
                  {formatDate(conv.updatedAt)}
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Footer */}
      <div
        className="p-3 border-t"
        style={{ borderColor: "var(--border)" }}
      >
        <div className="flex items-center gap-2 px-1">
          <div className="w-6 h-6 rounded-full gradient-bg flex items-center justify-center">
            <span className="text-white text-[10px] font-bold">H</span>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-medium truncate">Hwarang AI</p>
            <p className="text-[10px]" style={{ color: "var(--muted-foreground)" }}>v0.1.0</p>
          </div>
        </div>
      </div>
    </aside>
  );
}
