/**
 * HML - Hwarang Memory Ladder
 *
 * 화랑 독자 혁신 기법 #5
 *
 * 계단식 검색: 여러 단계로 RAG를 진행.
 *
 *   Step 1: 개념 검색 (큰 그림)
 *   Step 2: 구체 법령 검색
 *   Step 3: 유사 판례 검색
 *   Step 4: 반례 검색 (예외 사항)
 *   Step 5: 종합 합성
 *
 * 법률 조사 워크플로우 자동화.
 */

import { applyHRAG, type HRAGSource } from "../alignment/hrag";

export interface LadderStep {
  step: number;
  name: string;
  query: string;
  sources: HRAGSource[];
  insight: string;
}

export interface HMLResult {
  steps: LadderStep[];
  finalContext: string;
  totalSources: number;
}

/**
 * 질문에서 개념/구체/판례/반례 쿼리 생성
 */
function buildLadderQueries(userQuestion: string): {
  concept: string;
  specific: string;
  precedent: string;
  counter: string;
} {
  // 키워드 추출
  const legalKw = userQuestion.match(/(계약|해지|해제|손해|배상|상속|부동산|임대차|근로|해고|소송|저작권|특허)/)?.[0] || "";
  const taxKw = userQuestion.match(/(세금|소득세|부가세|양도세|법인세|연말정산)/)?.[0] || "";

  const domain = legalKw || taxKw || userQuestion.slice(0, 20);

  return {
    concept: `${domain} 개념 정의`,
    specific: `${domain} 관련 법령`,
    precedent: `${domain} 판례`,
    counter: `${domain} 예외 사항`,
  };
}

/**
 * 계단식 검색 실행
 */
export async function applyHML(
  userQuestion: string,
  vllmEndpoint: string,
  model: string
): Promise<HMLResult> {
  const queries = buildLadderQueries(userQuestion);
  const steps: LadderStep[] = [];

  // Step 1: 개념
  const concept = await applyHRAG(queries.concept);
  steps.push({
    step: 1,
    name: "개념 정의",
    query: queries.concept,
    sources: concept.sources,
    insight: concept.context || "개념 검색 결과 없음",
  });

  // Step 2: 구체 법령
  const specific = await applyHRAG(queries.specific);
  steps.push({
    step: 2,
    name: "관련 법령",
    query: queries.specific,
    sources: specific.sources,
    insight: specific.context || "법령 검색 결과 없음",
  });

  // Step 3: 판례
  const precedent = await applyHRAG(queries.precedent);
  steps.push({
    step: 3,
    name: "판례",
    query: queries.precedent,
    sources: precedent.sources,
    insight: precedent.context || "판례 검색 결과 없음",
  });

  // Step 4: 반례/예외
  const counter = await applyHRAG(queries.counter);
  steps.push({
    step: 4,
    name: "예외 사항",
    query: queries.counter,
    sources: counter.sources,
    insight: counter.context || "예외 검색 결과 없음",
  });

  // Step 5: 종합 컨텍스트
  let finalContext = `\n\n[HML - 계단식 조사 결과]\n`;
  for (const s of steps) {
    finalContext += `\n[Step ${s.step}. ${s.name}]\n`;
    if (s.sources.length > 0) {
      finalContext += s.sources
        .slice(0, 2)
        .map((src) => `  - ${src.title}: ${src.snippet}`)
        .join("\n");
    } else {
      finalContext += `  (관련 자료 없음)`;
    }
    finalContext += "\n";
  }

  finalContext += `\n\n[지침] 위 4단계 조사 결과를 종합하여 답변하세요.`;
  finalContext += `\n  - 개념 → 법령 → 판례 → 예외 순으로 논리적으로 설명`;
  finalContext += `\n  - 각 단계에서 찾은 근거를 명시적으로 인용`;

  const totalSources = steps.reduce((s, step) => s + step.sources.length, 0);

  return {
    steps,
    finalContext,
    totalSources,
  };
}

/**
 * HML이 필요한 질문인지 감지
 */
export function shouldUseHML(userMessage: string, domain: string): boolean {
  // 법률/세무 도메인 + 복잡한 질문
  if (!["legal", "tax"].includes(domain)) return false;

  // 복잡성 지표
  const complexIndicators = [
    /^(.{30,})/,                   // 30자 이상
    /(왜|어떻게|가능|경우|상황)/,    // 상황 질문
    /(분석|판단|해석)/,              // 분석 요구
  ];

  return complexIndicators.some((p) => p.test(userMessage));
}
