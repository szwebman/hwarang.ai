/**
 * TTT - Test-Time Training
 *
 * 추론 시점에 모델이 일시적으로 자기 가중치를 업데이트.
 * MIT 2025 연구 기반.
 *
 * 우리 구현: TTT는 GPU 측 학습이 필요하므로,
 *   추론 시점 "컨텍스트 학습" 방식으로 근사:
 *   1. 질문에서 핵심 컨텍스트 추출
 *   2. 유사 예제 대량 주입 (few-shot)
 *   3. 관련 문서를 "학습" 형태로 반복 제공
 *   4. 결과: 해당 질문에 한해 정확도 급상승
 */

export interface TTTContext {
  userQuestion: string;
  similarExamples: Array<{ question: string; answer: string }>;
  relevantDocs: string[];
  ttSteps: number;  // 유사 사례 반복 횟수
}

// 도메인별 few-shot 예제 풀
const DOMAIN_EXAMPLES: Record<string, Array<{ q: string; a: string }>> = {
  legal: [
    { q: "전세 보증금을 못 돌려받으면?", a: "1단계 내용증명 → 2단계 임차권등기명령 → 3단계 지급명령 → 4단계 소송 순서로 진행합니다. 대한법률구조공단(132) 무료 상담 가능." },
    { q: "부당해고 대응 방법?", a: "해고일로부터 3개월 이내 지방노동위원회에 부당해고 구제신청. 무료이며 복직+임금 지급 판정 가능." },
  ],
  tax: [
    { q: "종합소득세 신고 기한?", a: "매년 5월 1일~31일. 홈택스에서 온라인 신고 가능. 지연 시 무신고 가산세 20%." },
    { q: "부가세 신고 기한?", a: "1기(1~6월) → 7월 25일, 2기(7~12월) → 다음해 1월 25일." },
  ],
  coding: [
    { q: "Python 리스트 중복 제거?", a: "`list(set(arr))` 또는 `dict.fromkeys(arr)` 사용. 순서 유지 필요하면 후자." },
  ],
};

export function applyTTT(
  userQuestion: string,
  domain: string,
  options: { steps?: number } = {}
): { systemPrompt: string; enrichedMessages: any[] } {
  const examples = DOMAIN_EXAMPLES[domain] || [];
  const steps = options.steps ?? 3;

  // 질문 키워드 추출
  const keywords = userQuestion
    .split(/\s+/)
    .filter((w) => w.length > 2)
    .slice(0, 5);

  // 관련 예제 선택 (키워드 매칭)
  const relevantExamples = examples.filter((ex) =>
    keywords.some((kw) => ex.q.includes(kw))
  );

  const systemPrompt = `\n\n[TTT - Test-Time Training]
아래 유사 사례들을 학습 데이터로 삼아 답변 품질을 향상시키세요.
각 예제는 ${steps}번 반복 학습된 것으로 간주하세요.`;

  // Few-shot 메시지 구성 (TTT 효과)
  const enrichedMessages: any[] = [];
  for (const ex of relevantExamples.slice(0, 3)) {
    for (let i = 0; i < steps; i++) {
      enrichedMessages.push(
        { role: "user", content: ex.q },
        { role: "assistant", content: ex.a }
      );
    }
  }

  return { systemPrompt, enrichedMessages };
}
