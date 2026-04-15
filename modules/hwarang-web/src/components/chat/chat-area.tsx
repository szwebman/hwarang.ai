"use client";

import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useChat } from "@/hooks/use-chat";
import { useAutoScroll } from "@/hooks/use-scroll";
import { MessageBubble } from "./message-bubble";
import { MessageInput } from "./message-input";

export function ChatArea() {
  const { data: session, status } = useSession();
  const router = useRouter();
  const { messages, sendMessage, isStreaming, error } = useChat();
  const scrollRef = useAutoScroll(messages);

  // 로그인 안 되었으면 → 로그인 유도
  const handleSendWithAuth = (text: string) => {
    if (!session) {
      router.push("/login");
      return;
    }
    sendMessage(text);
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
                  <MessageBubble message={message} />
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
            <div className="flex items-center gap-2 text-sm px-4 py-3 rounded-xl mt-3 animate-fade-in"
              style={{ background: "color-mix(in srgb, var(--destructive) 10%, transparent)", color: "var(--destructive)" }}>
              {error}
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
          />
          <p className="text-[11px] text-center mt-2" style={{ color: "var(--muted-foreground)", opacity: 0.6 }}>
            화랑 AI는 실수할 수 있습니다. 중요한 정보는 확인하세요.
          </p>
        </div>
      </div>
    </div>
  );
}
