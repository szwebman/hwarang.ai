/**
 * HSEE Phase 1 — Implicit Feedback (web)
 *
 * 절대 명시 피드백 (👍/👎) 버튼을 추가하지 않는다.
 * 다음 신호만 수집해서 백엔드 ``POST /api/learning/feedback`` 으로 전달:
 *   - 코드 블록 복사     → 약 positive
 *   - 다음 user 메시지 부정 패턴 매칭 → negative + comment 첨부
 *
 * 모든 호출은 fire-and-forget. 실패해도 사용자 경험에 영향 X.
 */

export type ImplicitSignal =
  | { kind: "copy"; messageId: string }
  | { kind: "negative_followup"; messageId: string; userMessage: string }
  | { kind: "edit_distance"; messageId: string; distance: number };

/** 다음 user 메시지가 직전 응답에 대한 부정 신호인지 판정. */
const NEGATIVE_PATTERNS: RegExp[] = [
  /아니야/,
  /아니에요/,
  /아닙니다/,
  /다시\s*해/,
  /다시\s*해줘/,
  /잘못/,
  /틀렸/,
  /틀린/,
  /안돼/,
  /안되/,
  /안\s*맞/,
  /이상해/,
  /이상한/,
  /오류/,
  /엉터리/,
  /no[,!\.\s]/i,
  /wrong/i,
  /incorrect/i,
];

export function detectNegativePattern(text: string): boolean {
  if (!text) return false;
  const head = text.trim().slice(0, 200);
  if (!head) return false;
  return NEGATIVE_PATTERNS.some((re) => re.test(head));
}

/**
 * /api/learning/feedback 으로 전송 (Next.js → 백엔드 라우팅용 server-side proxy).
 * 클라이언트에서 직접 백엔드로 보내지 않고 Next.js 의 /api/feedback 라우트를
 * 재사용한다 — 그 라우트는 이미 fire-and-forget 으로 학습 백엔드에 전달함.
 *
 * 단, 명시 피드백 (rating != 0) 만 GRPO 보상이 지급되므로 implicit 신호는
 * 별도 엔드포인트(/api/feedback/implicit)를 사용해 토큰 보상 무관 처리.
 */
export async function sendImplicitFeedback(signal: ImplicitSignal): Promise<void> {
  try {
    await fetch("/api/feedback/implicit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(signal),
      keepalive: true, // 페이지 이탈 시에도 전송 보장
    });
  } catch {
    // ignore — 사용자 경험에 영향 주지 말 것
  }
}
