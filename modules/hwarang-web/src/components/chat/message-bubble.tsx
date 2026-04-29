"use client";

import type { ChatOption, Message } from "@/types/chat";
import { MarkdownRenderer } from "./markdown-renderer";
import { CodePreview, extractHtmlBlocks } from "./code-preview";
import { OptionCards } from "./option-cards";
import { useMemo } from "react";

interface MessageBubbleProps {
  message: Message;
  /**
   * 옵션 카드 클릭 시 같은 메시지에 답변 인라인으로 이어붙이기 위한 콜백.
   * 부모(ChatArea)에서 useChat.continueMessage 로 위임.
   */
  onOptionSelect?: (messageId: string, option: ChatOption) => Promise<void>;
}

/**
 * confidence (0~1) → 색상.
 *   0.8+ : 초록 / 0.5+ : 노랑 / 그 외 : 빨강
 * (lib/verification.ts 와 동일한 임계값을 사용. 클라이언트 컴포넌트에서 직접 정의해
 *  서버 코드 import 의존성을 피함)
 */
function getColorByConfidence(c: number | null | undefined): string {
  if (c == null) return "#64748b";
  if (c >= 0.8) return "#10b981";
  if (c >= 0.5) return "#ca8a04";
  return "#dc2626";
}

/**
 * 옵션 메시지의 content 를 인트로(서버가 보낸 "다음 N가지 중 선택..." 줄) 와
 * 옵션 클릭 후 인라인으로 이어붙은 답변 부분으로 분리.
 *
 * 서버 인트로 패턴: `다음 \d+가지 중 선택해 주세요:` (route.ts 참고)
 * 인트로 직후 첫 줄바꿈을 기준으로 split — 줄바꿈 없으면 전체가 인트로.
 */
function splitOptionIntroAndAnswer(content: string): {
  intro: string;
  answer: string;
} {
  if (!content) return { intro: "", answer: "" };
  // 인트로는 보통 첫 줄에 단독으로 옴.
  const m = content.match(/^(다음\s*\d+가지\s*중\s*선택해\s*주세요:?)/);
  if (m) {
    const intro = m[1];
    const rest = content.slice(intro.length).replace(/^[\s\n]+/, "");
    return { intro, answer: rest };
  }
  // 패턴이 안 맞으면 전체를 인트로로 취급 (안전한 폴백)
  return { intro: content, answer: "" };
}

export function MessageBubble({ message, onOptionSelect }: MessageBubbleProps) {
  const isUser = message.role === "user";
  const verification = message.meta?.verification;
  const realtime = message.meta?.realtime;
  const vision = message.meta?.vision;
  const options = message.meta?.options;
  const chargedTokens = message.meta?.chargedTokens as number | undefined;
  const modelDisplay =
    (message.meta?.displayName as string | undefined) ||
    (message.meta?.model as string | undefined);
  const latencyMs = message.meta?.latencyMs as number | undefined;

  // HTML 코드 블록 감지 (어시스턴트 메시지만)
  const { text, htmlBlocks } = useMemo(() => {
    if (isUser) return { text: message.content, htmlBlocks: [] };
    return extractHtmlBlocks(message.content);
  }, [message.content, isUser]);

  return (
    <div className={`flex gap-3 py-4 ${isUser ? "justify-end" : ""}`}>
      {/* Assistant avatar */}
      {!isUser && (
        <div className="w-8 h-8 rounded-xl gradient-bg flex items-center justify-center text-xs font-bold text-white shrink-0 shadow-sm">
          H
        </div>
      )}

      {/* Message content */}
      <div
        className={`rounded-2xl px-4 py-3 shadow-sm ${
          isUser ? "max-w-[80%] rounded-br-lg" : "max-w-[85%] rounded-bl-lg"
        }`}
        style={{
          background: isUser ? "var(--message-user-bg)" : "var(--message-assistant-bg)",
          color: isUser ? "var(--message-user-fg)" : "var(--message-assistant-fg)",
        }}
      >
        {isUser ? (
          <>
            {/* 첨부 이미지 (VLM 분석 대상) */}
            {message.images && message.images.length > 0 && (
              <div className="flex flex-wrap gap-2 mb-2">
                {message.images.map((img, i) => (
                  <img
                    key={i}
                    src={img.preview || img.base64}
                    alt={img.name || `attached-${i}`}
                    className="h-32 max-w-full rounded-lg object-cover"
                    style={{ border: "1px solid var(--border)" }}
                  />
                ))}
              </div>
            )}
            {message.content && (
              <p className="text-sm whitespace-pre-wrap leading-relaxed">{message.content}</p>
            )}
          </>
        ) : (
          <>
            {/* 옵션 모드: 인트로("다음 N가지 중 선택...") → 카드 → 선택 후 구분선 + 답변 누적분.
                일반 모드: 본문 텍스트만. */}
            {options?.options && options.options.length >= 2 ? (
              <>
                {/* 인트로 + (선택 후) 답변을 한 번에 분리해서 렌더 */}
                {(() => {
                  const split = splitOptionIntroAndAnswer(text);
                  return (
                    <>
                      {/* 인트로 */}
                      {split.intro && (
                        <div className="text-sm prose prose-sm dark:prose-invert max-w-none">
                          <MarkdownRenderer content={split.intro} />
                        </div>
                      )}

                      {/* 카드 */}
                      <OptionCards
                        options={options.options}
                        deliverable={options.deliverable}
                        messageId={message.id}
                        selectedOptionId={options.selectedOptionId ?? null}
                        onSelect={async (opt, msgId) => {
                          if (onOptionSelect) {
                            await onOptionSelect(msgId, opt);
                          } else if (typeof window !== "undefined") {
                            window.dispatchEvent(
                              new CustomEvent("hwarang:option-selected", {
                                detail: { option: opt, original: message.content },
                              }),
                            );
                          }
                        }}
                      />

                      {/* 선택 후 답변 (이어붙은 부분) */}
                      {options.selectedOptionId && split.answer && (
                        <>
                          <div
                            className="mt-3 mb-1 text-[10px] tracking-wide"
                            style={{ color: "var(--muted-foreground)" }}
                          >
                            ─── ✨ 답변 ───
                          </div>
                          <div className="text-sm prose prose-sm dark:prose-invert max-w-none">
                            <MarkdownRenderer content={split.answer} />
                          </div>
                        </>
                      )}
                    </>
                  );
                })()}
              </>
            ) : (
              <div className="text-sm prose prose-sm dark:prose-invert max-w-none">
                <MarkdownRenderer content={text} />
              </div>
            )}

            {/* 토큰 사용량 / 모델 / 지연 시간 — 응답 메타 푸터 */}
            {(chargedTokens || modelDisplay || latencyMs) && (
              <div
                className="flex flex-wrap items-center gap-2 mt-2 text-[10px]"
                style={{ color: "var(--muted-foreground)" }}
              >
                {chargedTokens != null && (
                  <span title="이번 응답에서 차감된 화랑 토큰">
                    ⚡ {chargedTokens.toLocaleString()} 토큰
                  </span>
                )}
                {modelDisplay && <span>· {modelDisplay}</span>}
                {latencyMs != null && (
                  <span>· {(latencyMs / 1000).toFixed(1)}초</span>
                )}
              </div>
            )}

            {/* HTML 코드 미리보기 (Artifacts 스타일) */}
            {htmlBlocks.map((html, i) => (
              <CodePreview key={i} code={html} language="HTML" />
            ))}

            {/* VLM 이미지 분석 결과 (있으면 접힌 상태로 표시) */}
            {vision?.used && vision.description && (
              <details
                className="mt-3 pt-2.5 text-xs"
                style={{ borderTop: "1px solid var(--border)" }}
              >
                <summary className="cursor-pointer font-semibold flex items-center gap-1.5">
                  <span>🖼️ 이미지 분석 결과</span>
                  <span
                    className="text-[10px] px-1.5 py-0.5 rounded"
                    style={{ background: "var(--muted)", color: "var(--muted-foreground)" }}
                  >
                    {vision.image_count}장 · {vision.mode === "code" ? "코드 명세" : "일반"}
                  </span>
                </summary>
                <div
                  className="mt-2 p-2.5 rounded whitespace-pre-wrap text-[11px] leading-relaxed"
                  style={{ background: "var(--muted)", color: "var(--foreground)" }}
                >
                  {vision.description.length > 800
                    ? `${vision.description.slice(0, 800)}…`
                    : vision.description}
                </div>
              </details>
            )}

            {/* 실시간 웹 검색 결과 (Naver / Wikipedia) */}
            {realtime?.used && realtime.sources.length > 0 && (
              <div
                className="mt-3 pt-2.5"
                style={{ borderTop: "1px solid var(--border)" }}
              >
                <div className="text-xs font-semibold mb-1.5">
                  ⚡ 실시간 검색 결과
                </div>
                {realtime.sources.slice(0, 3).map((s, i) => (
                  <a
                    key={i}
                    href={s.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[11px] block px-2 py-1 mb-1 rounded hover:opacity-80 transition-opacity"
                    style={{ background: "var(--muted, rgba(148,163,184,0.12))" }}
                  >
                    <span className="font-medium">{s.title}</span>
                    <span
                      className="text-[10px] ml-1"
                      style={{ color: "var(--muted-foreground)" }}
                    >
                      {s.source} · 신뢰도 {s.trust}
                    </span>
                  </a>
                ))}
              </div>
            )}

            {/* 출처 검증 배지 (Trusted Sources cross-verifier) */}
            {verification && verification.claims.length > 0 && (
              <div
                className="mt-3 pt-2.5"
                style={{ borderTop: "1px solid var(--border)" }}
              >
                <div className="text-xs font-semibold mb-2 flex items-center gap-1.5">
                  <span>📚 출처 검증</span>
                  <span
                    style={{
                      color: getColorByConfidence(verification.overallConfidence),
                    }}
                  >
                    {(verification.overallConfidence * 100).toFixed(0)}%
                  </span>
                  <span
                    className="text-[10px] px-1.5 py-0.5 rounded"
                    style={{
                      background: `${getColorByConfidence(verification.overallConfidence)}22`,
                      color: getColorByConfidence(verification.overallConfidence),
                    }}
                  >
                    {verification.overallConfidence >= 0.8
                      ? "강한 일치"
                      : verification.overallConfidence >= 0.5
                      ? "부분 일치"
                      : "근거 부족"}
                  </span>
                </div>
                {verification.claims.map((c, i) => (
                  <div key={i} className="text-[11px] mb-2 last:mb-0">
                    <div
                      className="line-clamp-2 italic mb-1"
                      style={{ color: "var(--muted-foreground)" }}
                    >
                      &ldquo;{c.text.slice(0, 120)}{c.text.length > 120 ? "..." : ""}&rdquo;
                    </div>
                    {c.primarySources.length > 0 ? (
                      <div className="flex flex-wrap gap-1">
                        {c.primarySources.map((s, j) => (
                          <a
                            key={j}
                            href={s.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-[10px] px-1.5 py-0.5 rounded hover:opacity-80 transition-opacity"
                            style={{
                              background: "rgba(16, 185, 129, 0.15)",
                              color: "#10b981",
                            }}
                            title={`신뢰도 ${s.trust}`}
                          >
                            {s.name} ({s.trust})
                          </a>
                        ))}
                        {c.contradictionCount > 0 && (
                          <span
                            className="text-[10px] px-1.5 py-0.5 rounded"
                            style={{
                              background: "rgba(220, 38, 38, 0.12)",
                              color: "#dc2626",
                            }}
                          >
                            ⚠ 모순 {c.contradictionCount}건
                          </span>
                        )}
                      </div>
                    ) : (
                      <div
                        className="text-[10px]"
                        style={{ color: "var(--muted-foreground)" }}
                      >
                        1차 출처 미발견 ({c.sourceCount}개 보조 출처만 일치)
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>

      {/* User avatar */}
      {isUser && (
        <div
          className="w-8 h-8 rounded-xl flex items-center justify-center text-xs font-bold shrink-0 shadow-sm"
          style={{ background: "var(--accent)", color: "var(--accent-foreground)" }}
        >
          U
        </div>
      )}
    </div>
  );
}
