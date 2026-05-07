"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { parseSSEStream } from "@/lib/stream-parser";
import { generateId } from "@/lib/utils";
import type { AttachedImage, Message } from "@/types/chat";
import { detectNegativePattern, sendImplicitFeedback } from "@/lib/feedback";

interface UseChatOptions {
  model?: string;
  apiUrl?: string;
  conversationId?: string | null;
  onConversationIdChange?: (id: string) => void;
  /** 안전 정책 — "loose" | "standard" | "strict". 백엔드 chat/route.ts 가 적용 (별도 작업). */
  safety?: string;
}

export interface ChatError {
  message: string;
  status?: number;
  code?: string;
}

export function useChat(options: UseChatOptions = {}) {
  const {
    model = "",
    apiUrl = "/api/chat",
    conversationId: externalCid,
    onConversationIdChange,
    safety = "standard",
  } = options;
  const [messages, setMessages] = useState<Message[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<ChatError | null>(null);
  const conversationIdRef = useRef<string | null>(externalCid ?? null);

  // 외부 conversationId 가 바뀌면 ref 동기화 (사이드바에서 다른 대화 클릭 등)
  useEffect(() => {
    conversationIdRef.current = externalCid ?? null;
  }, [externalCid]);

  const setConversationId = useCallback((id: string) => {
    if (conversationIdRef.current === id) return;
    conversationIdRef.current = id;
    onConversationIdChange?.(id);
  }, [onConversationIdChange]);

  const loadConversation = useCallback(async (id: string) => {
    try {
      const res = await fetch(`/api/conversations/${id}`);
      if (!res.ok) return;
      const { conversation } = await res.json();
      conversationIdRef.current = id;
      setMessages(
        (conversation?.messages || []).map((m: any) => ({
          id: m.id,
          role: m.role,
          content: m.content,
          images: m.images || [],
          createdAt: new Date(m.createdAt),
        }))
      );
      setError(null);
    } catch {}
  }, []);

  const sendMessage = useCallback(
    async (
      content: string,
      images?: AttachedImage[],
      opts?: { skipOptions?: boolean },
    ) => {
      setError(null);

      // HSEE Phase 1 — implicit feedback: 새 user 메시지가 부정 패턴이면
      // 직전 assistant 메시지에 negative 신호 (fire-and-forget).
      // setMessages 안에서 prev 를 읽으면 stale 이슈가 적고, hook 의존성도 줄어듦.
      if (detectNegativePattern(content)) {
        setMessages((prev) => {
          for (let i = prev.length - 1; i >= 0; i--) {
            if (prev[i].role === "assistant" && prev[i].content) {
              void sendImplicitFeedback({
                kind: "negative_followup",
                messageId: prev[i].id,
                userMessage: content,
              });
              break;
            }
          }
          return prev;
        });
      }

      // Add user message
      const userMessage: Message = {
        id: generateId(),
        role: "user",
        content,
        images: images && images.length > 0 ? images : undefined,
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
        // 첫 메시지면 클라이언트에서 UUID 생성 — 서버가 이 ID 로 conversation upsert.
        // 응답 헤더가 reverse proxy 에서 잘려도 ID 가 유지됨.
        if (!conversationIdRef.current) {
          const newId =
            typeof crypto !== "undefined" && crypto.randomUUID
              ? crypto.randomUUID()
              : `c_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
          setConversationId(newId);
        }

        const allMessages = [...messages, userMessage];
        const response = await fetch(apiUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            model,
            conversationId: conversationIdRef.current,
            messages: allMessages.map((m) => ({
              role: m.role,
              content: m.content,
              // VLM 라우팅용 — base64 data URL 만 보냄 (preview ObjectURL 은 클라이언트 전용)
              images: m.images?.map((i) => i.base64) || [],
            })),
            stream: true,
            // 옵션 카드 클릭 후 후속 메시지 — 옵션 모드 우회 (즉시 vLLM 호출).
            skipOptions: opts?.skipOptions ?? false,
            // 안전 모드 — backend chat/route.ts 가 안전 정책 적용 (loose/standard/strict)
            safety,
          }),
        });

        // 응답 헤더에서 conversationId 회수 (백업 — reverse proxy 가 살려 보내면)
        const cidHeader = response.headers.get("X-Conversation-Id");
        if (cidHeader) setConversationId(cidHeader);

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

        for await (const evt of parseSSEStream(response)) {
          if (evt.type === "content") {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? { ...m, content: m.content + evt.content }
                  : m
              )
            );
          } else if (evt.type === "meta") {
            // 서버가 응답 직후 첨부한 메타 (verification 출처 등)
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? { ...m, meta: { ...(m.meta || {}), ...evt.meta } }
                  : m
              )
            );
          }
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
    [messages, model, apiUrl, setConversationId, safety]
  );

  /**
   * 옵션 카드에서 하나를 선택했을 때 — 같은 assistant 메시지에 답변을 인라인으로 이어붙임.
   * - 새 user/assistant 메시지를 만들지 않음 (입력창도 비우지 않음).
   * - meta.options.selectedOptionId 를 셋해서 카드를 잠그고 ✓ 표시.
   * - 서버에는 continueOptionId/Title/Keywords 를 보내 옵션 모드를 우회.
   * - SSE content 델타는 같은 messageId 의 message.content 뒤에 누적.
   */
  const continueMessage = useCallback(
    async (
      messageId: string,
      optionId: string,
      optionTitle: string,
      optionKeywords: string[],
    ) => {
      setError(null);

      // 1. 카드 잠금 표시 (선택된 옵션 ID 기록) + 답변 시작 구분선이 보이도록 mark
      setMessages((prev) =>
        prev.map((m) => {
          if (m.id !== messageId) return m;
          if (!m.meta?.options) return m;
          return {
            ...m,
            meta: {
              ...m.meta,
              options: { ...m.meta.options, selectedOptionId: optionId },
            },
          };
        }),
      );

      setIsStreaming(true);

      try {
        // 첫 메시지가 옵션이었을 가능성도 있으므로 conversationId 보장
        if (!conversationIdRef.current) {
          const newId =
            typeof crypto !== "undefined" && crypto.randomUUID
              ? crypto.randomUUID()
              : `c_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
          setConversationId(newId);
        }

        // route.ts 가 lastUserMessage 를 기준으로 라우팅하므로 그대로 messages 전달.
        const response = await fetch(apiUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            model,
            conversationId: conversationIdRef.current,
            messages: messages.map((m) => ({
              role: m.role,
              content: m.content,
              images: m.images?.map((i) => i.base64) || [],
            })),
            stream: true,
            // 옵션 후속 — 서버는 옵션 감지 우회 + 선택 컨텍스트를 system prompt 로 주입.
            skipOptions: true,
            continueOptionId: optionId,
            continueOptionTitle: optionTitle,
            continueOptionKeywords: optionKeywords,
            continueMessageId: messageId,
            safety,
          }),
        });

        const cidHeader = response.headers.get("X-Conversation-Id");
        if (cidHeader) setConversationId(cidHeader);

        if (!response.ok) {
          let errorBody: { error?: string; message?: string; detail?: string; code?: string } = {};
          try {
            errorBody = await response.json();
          } catch {}
          const message =
            errorBody.error ||
            errorBody.message ||
            errorBody.detail ||
            `요청 실패 (${response.status})`;
          const e = new Error(message) as Error & { status?: number; code?: string };
          e.status = response.status;
          e.code = errorBody.code;
          throw e;
        }

        // 같은 messageId 에 content/meta 이어붙이기
        for await (const evt of parseSSEStream(response)) {
          if (evt.type === "content") {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === messageId ? { ...m, content: m.content + evt.content } : m,
              ),
            );
          } else if (evt.type === "meta") {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === messageId
                  ? {
                      ...m,
                      meta: {
                        ...(m.meta || {}),
                        ...evt.meta,
                        // selectedOptionId 보존 — 새로 들어온 meta.options 가 덮어쓰지 않도록
                        options: m.meta?.options
                          ? {
                              ...m.meta.options,
                              ...(evt.meta?.options || {}),
                              selectedOptionId:
                                m.meta.options.selectedOptionId ??
                                evt.meta?.options?.selectedOptionId,
                            }
                          : evt.meta?.options,
                      },
                    }
                  : m,
              ),
            );
          }
        }
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : "옵션 진행 중 오류";
        const status =
          err && typeof err === "object" && "status" in err
            ? (err as { status?: number }).status
            : undefined;
        const code =
          err && typeof err === "object" && "code" in err
            ? (err as { code?: string }).code
            : undefined;
        setError({ message: errorMessage, status, code });
        // 실패 시 카드 잠금 해제 — 사용자가 다시 시도할 수 있게
        setMessages((prev) =>
          prev.map((m) => {
            if (m.id !== messageId) return m;
            if (!m.meta?.options) return m;
            const { selectedOptionId: _drop, ...restOptions } = m.meta.options;
            return { ...m, meta: { ...m.meta, options: restOptions } };
          }),
        );
      } finally {
        setIsStreaming(false);
      }
    },
    [messages, model, apiUrl, setConversationId, safety],
  );

  const clearMessages = useCallback(() => {
    setMessages([]);
    setError(null);
    conversationIdRef.current = null;
  }, []);

  return {
    messages,
    sendMessage,
    continueMessage,
    isStreaming,
    error,
    clearMessages,
    loadConversation,
  };
}
