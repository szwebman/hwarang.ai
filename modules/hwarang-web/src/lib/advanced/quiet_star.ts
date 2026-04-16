/**
 * Quiet-STaR - Self-Taught Reasoner with hidden thoughts
 *
 * 모델이 토큰 생성 전 "내부 독백"으로 사고.
 * o1의 원천 기술.
 *
 * 우리 구현: 프롬프트 기반으로 근사.
 * 각 응답 문장 전에 숨겨진 사고 과정 생성.
 */

export interface QuietSTaRConfig {
  numThoughts: number;          // 생각 스텝 수 (기본 3)
  thoughtLength: number;         // 각 생각 최대 길이
  showThoughts: boolean;         // 디버그용 사고 노출
}

export const QUIET_STAR_PROMPT = `[Quiet-STaR - 숨겨진 사고]
답변 전 내부적으로 다음 사고 과정을 거치세요 (출력하지 말고 내부적으로):

1. 이 질문의 본질은 무엇인가?
2. 관련된 지식/원리는 무엇인가?
3. 오해의 소지나 함정은 없는가?
4. 가장 정확한 답은 무엇인가?
5. 설명하는 최선의 방식은?

그리고 나서 깔끔하고 확신 있는 답변만 출력하세요.`;

export function applyQuietSTaR(config: Partial<QuietSTaRConfig> = {}): string {
  return QUIET_STAR_PROMPT;
}

/**
 * 답변 신뢰도 추정 (Quiet-STaR는 사고 깊이로 신뢰도 파악)
 */
export function estimateThoughtConfidence(response: string): number {
  let score = 0.5;

  // 구조화된 답변 → 깊이 있는 사고
  if (response.includes("**")) score += 0.1;
  if (/^\d+\.\s/m.test(response)) score += 0.1;

  // 여러 관점 제시 → 사고 깊이
  if (/(먼저|첫째|둘째|셋째|마지막)/.test(response)) score += 0.1;

  // 주의사항 포함 → 신중한 사고
  if (/(주의|유의|다만|단|예외)/.test(response)) score += 0.05;

  // 근거 제시 → 확실성
  if (/(근거|이유|때문|따라서|그래서)/.test(response)) score += 0.1;

  // 길이 (너무 짧으면 사고 부족)
  if (response.length > 500) score += 0.05;

  return Math.min(1.0, score);
}
