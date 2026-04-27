"use client";

import { useEffect, useState } from "react";
import { ChatArea } from "@/components/chat/chat-area";
import { Sidebar } from "@/components/sidebar/sidebar";
import { Header } from "@/components/layout/header";
import { useConversations } from "@/hooks/use-conversations";

export default function Home() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const { conversations, refresh } = useConversations();
  const [activeConversationId, setActiveConversationId] = useState<
    string | null
  >(null);

  const handleNewChat = () => {
    setActiveConversationId(null);
  };

  // 채팅 영역에서 새 메시지가 전송되면 좌측 리스트 갱신
  useEffect(() => {
    const handler = () => {
      refresh();
    };
    if (typeof window !== "undefined") {
      window.addEventListener("hwarang:conversation-changed", handler);
      return () =>
        window.removeEventListener("hwarang:conversation-changed", handler);
    }
  }, [refresh]);

  return (
    <div className="flex h-screen overflow-hidden" style={{ background: "var(--background)" }}>
      {/* Sidebar with slide animation */}
      <div
        className="shrink-0 transition-all duration-300 ease-in-out overflow-hidden"
        style={{ width: sidebarOpen ? "var(--sidebar-width)" : "0px" }}
      >
        <Sidebar
          conversations={conversations}
          activeId={activeConversationId}
          onSelect={setActiveConversationId}
          onNewChat={handleNewChat}
          onClose={() => setSidebarOpen(false)}
        />
      </div>

      {/* Main area */}
      <div className="flex flex-1 flex-col min-w-0">
        <Header
          sidebarOpen={sidebarOpen}
          onToggleSidebar={() => setSidebarOpen(!sidebarOpen)}
        />
        <ChatArea />
      </div>
    </div>
  );
}
