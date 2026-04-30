/**
 * Context Compactor — 긴 대화의 conversationHistory 자동 요약.
 *
 * 임계값:
 *  - 메시지 수: 30개 이상
 *  - 누적 문자 수: 30,000자 (~7~8K 토큰) 이상
 *
 * 압축 전략:
 *  1. 최근 10 메시지는 보존
 *  2. 이전 메시지를 LLM 으로 5~10줄 한국어 요약
 *  3. system 메시지 1개 + 최근 10개로 교체
 *
 * 압축 실패 시 원본 history 유지 (안전).
 */

import { ChatMessage, LLMClient } from "../providers/llm-client";

const MIN_MESSAGES_TO_COMPACT = 30;
const MIN_CHARS_TO_COMPACT = 30_000;
const PRESERVE_RECENT = 10;
const PER_MSG_PREVIEW_CHARS = 200;

export class ContextCompactor {
  /**
   * 압축이 필요한지 판단.
   * - 메시지 30개 미만 → false
   * - 누적 글자 30K 미만 → false
   */
  shouldCompact(history: ChatMessage[]): boolean {
    if (!history || history.length < MIN_MESSAGES_TO_COMPACT) return false;
    const totalChars = history.reduce(
      (sum, m) => sum + (m.content?.length || 0),
      0
    );
    return totalChars > MIN_CHARS_TO_COMPACT;
  }

  /**
   * 압축 수행.
   * - 마지막 PRESERVE_RECENT 개는 그대로 유지
   * - 그 이전은 LLM 호출로 요약
   * - 결과: [system 요약, ...최근 메시지]
   */
  async compact(
    history: ChatMessage[],
    llm: LLMClient
  ): Promise<ChatMessage[]> {
    if (!this.shouldCompact(history)) return history;

    const recent = history.slice(-PRESERVE_RECENT);
    const old = history.slice(0, -PRESERVE_RECENT);

    if (old.length === 0) return history;

    // 요약 프롬프트 — 너무 길면 LLM 호출 자체가 비싸지므로 each msg 200자로 trim
    const oldText = old
      .map((m) => {
        const role = m.role;
        const body = (m.content || "").slice(0, PER_MSG_PREVIEW_CHARS);
        return `${role}: ${body}`;
      })
      .join("\n");

    const summaryPrompt =
      "다음은 화랑 코드 어시스턴트와 사용자의 이전 대화 일부입니다.\n" +
      "핵심 결정사항 / 만든 파일 / 진행한 작업 / 미해결 항목을 5~10줄 한국어로 요약하세요.\n" +
      "코드/명령은 생략하고 사실만 압축합니다.\n\n" +
      oldText;

    let summary = "";
    try {
      const resp = await llm.chat([
        {
          role: "system",
          content:
            "당신은 대화 요약기입니다. 입력 대화의 핵심을 짧게 한국어로 정리합니다.",
        },
        { role: "user", content: summaryPrompt },
      ]);
      summary = (resp.content || "").trim();
    } catch (e) {
      console.warn("[ContextCompactor] 요약 LLM 호출 실패 — 원본 유지:", e);
      return history;
    }

    if (!summary) {
      // 요약 결과 비었으면 원본 유지 (안전)
      return history;
    }

    const compactedSystem: ChatMessage = {
      role: "system",
      content:
        `[이전 대화 요약 — ${old.length}개 메시지 압축]\n${summary}`,
    };

    return [compactedSystem, ...recent];
  }
}
