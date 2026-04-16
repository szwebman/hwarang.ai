/**
 * ACT - Adaptive Computation Time
 *
 * 질문 난이도에 따라 생각하는 시간 자동 조절.
 * 쉬운 질문 = 빠르게, 어려운 질문 = 깊이 있게.
 */

export type Difficulty = "trivial" | "simple" | "medium" | "hard" | "expert";

export interface ACTConfig {
  difficulty: Difficulty;
  maxTokens: number;
  useReasoning: boolean;
  useTTT: boolean;
  useCoRD: boolean;
  temperature: number;
}

/**
 * 질문 난이도 자동 감지
 */
export function assessDifficulty(userMessage: string): Difficulty {
  const len = userMessage.length;

  // 매우 짧거나 단순 인사
  if (len < 15 || /^(안녕|hi|hello|hey|ㅎㅇ)/i.test(userMessage)) {
    return "trivial";
  }

  // 전문 도메인 키워드
  const expertKeywords = [
    /민법|형법|상법|노동법|저작권법/,
    /양도세|종합소득세|법인세/,
    /판례|대법원|소송/,
    /수학적.*증명|알고리즘.*복잡도|시간.*공간.*복잡도/,
    /분산.*시스템|동시성.*제어|합의.*알고리즘/,
  ];
  if (expertKeywords.some((k) => k.test(userMessage))) {
    return "expert";
  }

  // 복잡한 추론 필요
  const hardKeywords = [
    /분석|비교|평가|증명|논리|추론/,
    /왜.*인가|어떻게.*될|가능성|전략/,
    /여러.*방법|장단점|trade.?off/i,
  ];
  if (hardKeywords.some((k) => k.test(userMessage))) {
    return "hard";
  }

  // 중간 난이도 (설명, 방법)
  if (/설명|방법|가이드|how.?to/i.test(userMessage)) {
    return "medium";
  }

  return "simple";
}

/**
 * 난이도에 따른 ACT 설정
 */
export function applyACT(userMessage: string): ACTConfig {
  const difficulty = assessDifficulty(userMessage);

  const configs: Record<Difficulty, ACTConfig> = {
    trivial: {
      difficulty: "trivial",
      maxTokens: 256,
      useReasoning: false,
      useTTT: false,
      useCoRD: false,
      temperature: 0.7,
    },
    simple: {
      difficulty: "simple",
      maxTokens: 1024,
      useReasoning: false,
      useTTT: false,
      useCoRD: false,
      temperature: 0.7,
    },
    medium: {
      difficulty: "medium",
      maxTokens: 2048,
      useReasoning: false,
      useTTT: true,
      useCoRD: false,
      temperature: 0.6,
    },
    hard: {
      difficulty: "hard",
      maxTokens: 4096,
      useReasoning: true,
      useTTT: true,
      useCoRD: false,
      temperature: 0.5,
    },
    expert: {
      difficulty: "expert",
      maxTokens: 8192,
      useReasoning: true,
      useTTT: true,
      useCoRD: true,
      temperature: 0.3,
    },
  };

  return configs[difficulty];
}
