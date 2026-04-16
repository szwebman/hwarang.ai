/**
 * Reasoning Scaling (o1 / DeepSeek-R1 style)
 *
 * 추론 전 "생각하는 시간"을 늘려 성능 향상.
 * 내부적으로 긴 CoT (Chain-of-Thought) → 최종 답만 출력.
 */

export interface ReasoningConfig {
  thinkingTokens: number;     // 내부 사고 최대 토큰 (기본 10000)
  finalTokens: number;        // 최종 답변 토큰 (기본 1000)
  showThinking: boolean;      // 사고 과정 노출 여부
}

const REASONING_PROMPT = `[Reasoning Mode - 깊이 생각하기]
당신은 깊이 있는 추론이 필요한 질문에 답변합니다.

[사고 과정]
<thinking>
여기에 단계별 사고 과정을 자유롭게 적으세요:
- 문제 분해
- 여러 접근법 고려
- 각 접근의 장단점
- 가능한 오류 체크
- 최종 결론 도출
</thinking>

[최종 답변]
<thinking> 태그 이후에 깔끔하게 최종 답변만 작성하세요.`;

export function applyReasoningScaling(
  config: Partial<ReasoningConfig> = {}
): { systemPrompt: string; maxTokens: number } {
  const full: ReasoningConfig = {
    thinkingTokens: config.thinkingTokens ?? 10000,
    finalTokens: config.finalTokens ?? 1000,
    showThinking: config.showThinking ?? false,
  };

  return {
    systemPrompt: REASONING_PROMPT,
    maxTokens: full.thinkingTokens + full.finalTokens,
  };
}

/**
 * 응답에서 <thinking> 블록 추출/제거
 */
export function extractThinking(response: string, showThinking: boolean = false): {
  thinking: string;
  answer: string;
} {
  const thinkingMatch = response.match(/<thinking>([\s\S]*?)<\/thinking>/);
  const thinking = thinkingMatch ? thinkingMatch[1].trim() : "";
  let answer = response.replace(/<thinking>[\s\S]*?<\/thinking>/g, "").trim();

  if (showThinking && thinking) {
    answer = `**🧠 사고 과정:**\n${thinking}\n\n---\n\n**답변:**\n${answer}`;
  }

  return { thinking, answer };
}

/**
 * 추론 모드가 필요한 질문인지 자동 감지
 */
export function needsDeepReasoning(userMessage: string): boolean {
  const triggers = [
    /계산(해|하)/,
    /분석(해|하)/,
    /비교(해|하)/,
    /증명(해|하)/,
    /추론(해|하)/,
    /단계별/,
    /왜.*인가/,
    /어떻게.*될까/,
    /가능성.*계산/,
  ];
  return triggers.some((t) => t.test(userMessage));
}
