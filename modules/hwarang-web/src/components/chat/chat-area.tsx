"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useChat } from "@/hooks/use-chat";
import { useAutoScroll } from "@/hooks/use-scroll";
import { MessageBubble } from "./message-bubble";
import { MessageInput } from "./message-input";
import type { AttachedImage } from "@/types/chat";

interface ChatAreaProps {
  conversationId?: string | null;
  onConversationIdChange?: (id: string) => void;
}

export function ChatArea({ conversationId, onConversationIdChange }: ChatAreaProps = {}) {
  const { data: session } = useSession();
  const router = useRouter();
  // 입력창 OptionBar 상태 — "" = Auto 라우팅
  const [selectedModel, setSelectedModel] = useState<string>("");
  const [safetyMode, setSafetyMode] = useState<string>("standard");
  const {
    messages,
    sendMessage,
    continueMessage,
    isStreaming,
    error,
    clearMessages,
    loadConversation,
  } = useChat({
    conversationId,
    onConversationIdChange,
    model: selectedModel,
    safety: safetyMode,
  });
  const scrollRef = useAutoScroll(messages);
  const lastAssistantContentRef = useRef<string>("");

  // 사이드바에서 다른 대화 클릭 시 메시지 로드, null 이면 빈 상태
  useEffect(() => {
    if (conversationId) {
      loadConversation(conversationId);
    } else {
      clearMessages();
    }
  }, [conversationId, loadConversation, clearMessages]);

  // assistant 응답이 끝날 때마다 OptionBar 의 사용량 즉시 갱신 트리거.
  // 30초 폴링과 별개로, 토큰 차감 직후의 잔액을 빠르게 반영.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const last = messages[messages.length - 1];
    if (!last || last.role !== "assistant") return;
    // 스트리밍이 끝나고 (isStreaming false) 컨텐츠가 확정된 시점에만 발사
    if (isStreaming) return;
    if (last.content === lastAssistantContentRef.current) return;
    if (!last.content) return;
    lastAssistantContentRef.current = last.content;
    window.dispatchEvent(new Event("hwarang:usage-changed"));
  }, [messages, isStreaming]);

  // [레거시 호환] 옵션 카드가 onOptionSelect prop 을 받지 못한 경우(다른 곳에서 직접 카드 렌더 등)
  // 만 fallback 으로 "{title} 스타일로 진행해줘" 자동 전송.
  // 신규 인라인 흐름(continueMessage)에서는 이 이벤트를 발사하지 않음.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail as
        | { option: { title: string; keywords: string[] } }
        | undefined;
      if (!detail?.option) return;
      const { option } = detail;
      const followup = `${option.title} 스타일로 진행해줘. (${option.keywords.join(", ")})`;
      sendMessage(followup, undefined, { skipOptions: true });
    };
    window.addEventListener("hwarang:option-selected", handler);
    return () => window.removeEventListener("hwarang:option-selected", handler);
  }, [sendMessage]);

  const handleSendWithAuth = async (
    text: string,
    _files?: File[],
    images?: AttachedImage[],
  ) => {
    if (!session) {
      router.push("/login");
      return;
    }
    await sendMessage(text, images);
    if (typeof window !== "undefined") {
      window.dispatchEvent(new Event("hwarang:conversation-changed"));
    }
  };

  return (
    <div className="flex flex-col flex-1 min-h-0">
      {/* 메시지 */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-4 py-6">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center min-h-[65vh] animate-fade-in">
              <div className="w-16 h-16 rounded-2xl gradient-bg flex items-center justify-center mb-6 shadow-lg">
                <span className="text-white text-2xl font-bold">H</span>
              </div>
              <h2 className="text-2xl font-bold mb-2">
                <span className="gradient-text">화랑 AI</span>
              </h2>
              <p className="text-sm mb-8" style={{ color: "var(--muted-foreground)" }}>
                {session ? "무엇을 도와드릴까요?" : "로그인하고 AI와 대화하세요"}
              </p>

              {/* 로그인 안내 (비로그인 시) */}
              {!session && (
                <button
                  onClick={() => router.push("/login")}
                  className="px-6 py-3 rounded-xl text-sm font-medium text-white gradient-bg hover:shadow-lg transition-all mb-8"
                >
                  로그인하고 시작하기
                </button>
              )}

              {/* 빠른 질문 (로그인 시) */}
              {session && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-lg">
                  {[
                    { icon: "💡", text: "파이썬으로 웹 크롤러 만들어줘" },
                    { icon: "📝", text: "Git 사용법을 알려줘" },
                    { icon: "🔍", text: "React와 Vue의 차이점은?" },
                    { icon: "🚀", text: "Docker 시작 가이드" },
                  ].map((prompt) => (
                    <button
                      key={prompt.text}
                      onClick={() => handleSendWithAuth(prompt.text)}
                      className="flex items-center gap-3 px-4 py-3 rounded-xl border text-sm text-left transition-all duration-200 hover:shadow-md hover:border-[var(--primary)] active:scale-[0.98]"
                      style={{ borderColor: "var(--border)", background: "var(--background)" }}
                    >
                      <span className="text-lg">{prompt.icon}</span>
                      <span style={{ color: "var(--foreground)" }}>{prompt.text}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-1">
              {messages.map((message, idx) => (
                <div key={message.id} className="animate-fade-in" style={{ animationDelay: `${Math.min(idx * 30, 200)}ms` }}>
                  <MessageBubble
                    message={message}
                    onOptionSelect={async (msgId, opt) => {
                      // Claude-style 인라인 — 같은 메시지에 답변 이어붙이기
                      await continueMessage(msgId, opt.id, opt.title, opt.keywords);
                    }}
                  />
                </div>
              ))}
            </div>
          )}

          {isStreaming && (
            <div className="flex items-center gap-3 py-3 pl-11 animate-fade-in">
              <div className="typing-indicator flex gap-1">
                <span></span><span></span><span></span>
              </div>
            </div>
          )}

          {error && (
            <div
              className="flex flex-wrap items-center gap-3 text-sm px-4 py-3 rounded-xl mt-3 animate-fade-in border"
              style={{
                background: "color-mix(in srgb, var(--destructive) 8%, transparent)",
                borderColor: "color-mix(in srgb, var(--destructive) 30%, transparent)",
                color: "var(--destructive)",
              }}
              role="alert"
            >
              <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                className="shrink-0"
              >
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
              <span className="flex-1 min-w-0">{error.message}</span>

              {/* 401 → 로그인 */}
              {error.status === 401 && (
                <Link
                  href="/login"
                  className="px-3 py-1.5 rounded-lg text-xs font-medium text-white gradient-bg hover:shadow-md transition-all"
                >
                  로그인
                </Link>
              )}

              {/* 402 → 토큰 충전 */}
              {error.status === 402 && (
                <Link
                  href="/pricing"
                  className="px-3 py-1.5 rounded-lg text-xs font-medium text-white gradient-bg hover:shadow-md transition-all"
                >
                  토큰 충전
                </Link>
              )}

              {/* 403 → 플랜 업그레이드 */}
              {error.status === 403 && (
                <Link
                  href="/pricing"
                  className="px-3 py-1.5 rounded-lg text-xs font-medium text-white gradient-bg hover:shadow-md transition-all"
                >
                  플랜 업그레이드
                </Link>
              )}

              {/* 429 → 토큰 추가 구매 + 대시보드 */}
              {error.status === 429 && (
                <>
                  <Link
                    href="/dashboard"
                    className="px-3 py-1.5 rounded-lg text-xs font-medium border hover:bg-[var(--muted)] transition-all"
                    style={{ borderColor: "var(--border)", color: "var(--foreground)" }}
                  >
                    사용량 보기
                  </Link>
                  <Link
                    href="/pricing"
                    className="px-3 py-1.5 rounded-lg text-xs font-medium text-white gradient-bg hover:shadow-md transition-all"
                  >
                    추가 구매
                  </Link>
                </>
              )}
            </div>
          )}
        </div>
      </div>

      {/* 입력 */}
      <div className="border-t glass" style={{ borderColor: "var(--border)", background: `color-mix(in srgb, var(--background) 85%, transparent)` }}>
        <div className="max-w-3xl mx-auto px-4 py-4">
          <MessageInput
            onSend={handleSendWithAuth}
            disabled={isStreaming}
            placeholder={session ? "메시지를 입력하세요..." : "로그인 후 이용 가능합니다"}
            selectedModel={selectedModel}
            setSelectedModel={setSelectedModel}
            safetyMode={safetyMode}
            setSafetyMode={setSafetyMode}
          />
          <p className="text-[11px] text-center mt-2" style={{ color: "var(--muted-foreground)", opacity: 0.6 }}>
            화랑 AI는 실수할 수 있습니다. 중요한 정보는 확인하세요.
          </p>
        </div>
      </div>
    </div>
  );
}
