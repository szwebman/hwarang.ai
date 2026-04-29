"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ChatArea } from "@/components/chat/chat-area";
import { Sidebar } from "@/components/sidebar/sidebar";
import { Header } from "@/components/layout/header";
import { useConversations } from "@/hooks/use-conversations";

interface ChatPageProps {
  initialConversationId: string | null;
}

export function ChatPage({ initialConversationId }: ChatPageProps) {
  const router = useRouter();
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const { conversations, refresh } = useConversations();
  const [activeConversationId, setActiveConversationId] = useState<string | null>(
    initialConversationId
  );

  // URL 변경 → 내부 상태 동기화 (브라우저 뒤로가기 등)
  useEffect(() => {
    setActiveConversationId(initialConversationId);
  }, [initialConversationId]);

  // 사이드바에서 대화 선택 → URL 업데이트
  const handleSelect = useCallback(
    (id: string) => {
      setActiveConversationId(id);
      router.push(`/chat/${id}`);
    },
    [router]
  );

  // 새 대화 → / chat 으로
  const handleNewChat = useCallback(() => {
    setActiveConversationId(null);
    router.push("/chat");
  }, [router]);

  // ChatArea 가 새 대화 생성하면 URL 동기화
  const handleConversationIdChange = useCallback(
    (id: string) => {
      setActiveConversationId(id);
      // 새로 생성된 대화면 URL 업데이트 (기존 활성과 다를 때만)
      if (id !== initialConversationId) {
        router.replace(`/chat/${id}`);
      }
      refresh();
    },
    [router, initialConversationId, refresh]
  );

  // 새 메시지 전송 시 좌측 리스트 갱신
  useEffect(() => {
    const handler = () => refresh();
    if (typeof window !== "undefined") {
      window.addEventListener("hwarang:conversation-changed", handler);
      return () => window.removeEventListener("hwarang:conversation-changed", handler);
    }
  }, [refresh]);

  return (
    <div className="flex h-screen overflow-hidden" style={{ background: "var(--background)" }}>
      <div
        className="shrink-0 transition-all duration-300 ease-in-out overflow-hidden"
        style={{ width: sidebarOpen ? "var(--sidebar-width)" : "0px" }}
      >
        <Sidebar
          conversations={conversations}
          activeId={activeConversationId}
          onSelect={handleSelect}
          onNewChat={handleNewChat}
          onClose={() => setSidebarOpen(false)}
        />
      </div>

      <div className="flex flex-1 flex-col min-w-0">
        <Header
          sidebarOpen={sidebarOpen}
          onToggleSidebar={() => setSidebarOpen(!sidebarOpen)}
        />
        <ChatArea
          conversationId={activeConversationId}
          onConversationIdChange={handleConversationIdChange}
        />
      </div>
    </div>
  );
}
