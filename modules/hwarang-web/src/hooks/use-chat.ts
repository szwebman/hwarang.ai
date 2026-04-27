"use client";

import { useCallback, useState } from "react";
import { parseSSEStream } from "@/lib/stream-parser";
import { generateId } from "@/lib/utils";
import type { Message } from "@/types/chat";

interface UseChatOptions {
  model?: string;
  apiUrl?: string;
}

export interface ChatError {
  message: string;
  status?: number;
  code?: string;
}

export function useChat(options: UseChatOptions = {}) {
  const { model = "", apiUrl = "/api/chat" } = options;
  const [messages, setMessages] = useState<Message[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<ChatError | null>(null);

  const sendMessage = useCallback(
    async (content: string) => {
      setError(null);

      // Add user message
      const userMessage: Message = {
        id: generateId(),
        role: "user",
        content,
        createdAt: new Date(),
      };

      const assistantId = generateId();
      const assistantMessage: Message = {
        id: assistantId,
        role: "assistant",
        content: "",
        createdAt: new Date(),
      };

      setMessages((prev) => [...prev, userMessage, assistantMessage]);
      setIsStreaming(true);

      try {
        const allMessages = [...messages, userMessage];
        const response = await fetch(apiUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            model,
            messages: allMessages.map((m) => ({
              role: m.role,
              content: m.content,
            })),
            stream: true,
          }),
        });

        if (!response.ok) {
          // 백엔드 응답 본문에서 사용자용 메시지 추출
          let errorBody: { error?: string; message?: string; detail?: string; code?: string } = {};
          try {
            errorBody = await response.json();
          } catch {
            // JSON 파싱 실패 시 무시 (HTML/빈 응답 등)
          }

          // 상태 코드별 한국어 fallback 메시지
          const friendlyByStatus: Record<number, string> = {
            401: "로그인이 필요합니다. 다시 로그인해 주세요.",
            402: "토큰이 부족합니다. 대시보드에서 충전해 주세요.",
            403: "이 모델/기능은 현재 플랜에서 사용할 수 없습니다. 플랜 업그레이드가 필요합니다.",
            429: "오늘 토큰 한도를 모두 사용했습니다. 자정에 자동 리셋됩니다.",
            500: "서버 오류입니다. 잠시 후 다시 시도해 주세요.",
            502: "AI 서버에 일시적으로 연결할 수 없습니다.",
            503: "AI 모델이 잠시 응답하지 못합니다. 다른 모델로 시도해 보세요.",
            504: "응답 시간이 초과되었습니다. 더 짧은 메시지로 시도해 보세요.",
          };

          const message =
            errorBody.error ||
            errorBody.message ||
            errorBody.detail ||
            friendlyByStatus[response.status] ||
            `요청 실패 (${response.status})`;

          const e = new Error(message) as Error & { status?: number; code?: string };
          e.status = response.status;
          e.code = errorBody.code;
          throw e;
        }

        for await (const chunk of parseSSEStream(response)) {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? { ...m, content: m.content + chunk }
                : m
            )
          );
        }
      } catch (err) {
        const errorMessage =
          err instanceof Error ? err.message : "오류가 발생했습니다";
        const status =
          err && typeof err === "object" && "status" in err
            ? (err as { status?: number }).status
            : undefined;
        const code =
          err && typeof err === "object" && "code" in err
            ? (err as { code?: string }).code
            : undefined;
        setError({ message: errorMessage, status, code });
        // assistant 자리표시자 메시지 제거 (에러 배너로 대체)
        setMessages((prev) => prev.filter((m) => m.id !== assistantId));
      } finally {
        setIsStreaming(false);
      }
    },
    [messages, model, apiUrl]
  );

  const clearMessages = useCallback(() => {
    setMessages([]);
    setError(null);
  }, []);

  return { messages, sendMessage, isStreaming, error, clearMessages };
}
