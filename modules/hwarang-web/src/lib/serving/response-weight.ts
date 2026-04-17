/**
 * 에이전트 응답 가중치 시스템
 *
 * 여러 에이전트 응답 중 최적 선택, 또는 단일 응답의 신뢰도 계산.
 *
 * 종합 신뢰도 =
 *   모델 logprob (50%) +
 *   에이전트 평판 (20%) +
 *   전문화 일치도 (15%) +
 *   과거 유저 피드백 (15%)
 *
 * 활용:
 *   - 병렬 추론에서 최적 응답 선택
 *   - 응답에 신뢰도 뱃지 표시
 *   - 낮은 신뢰도 → 면책조항 자동 추가
 *   - 보상 차등 (높은 품질 = 더 많은 코인)
 */

// ─── 가중치 설정 ────────────────────────────────────────────

const WEIGHT_CONFIG = {
  modelLogprob: 0.50,        // 모델 자체 확신도
  agentReputation: 0.20,     // 에이전트 평판 점수
  specialization: 0.15,      // 도메인 전문화 일치도
  userFeedback: 0.15,        // 과거 유저 피드백 이력
};

// ─── 입력 타입 ──────────────────────────────────────────────

export interface AgentResponseMeta {
  agentId: string;
  response: string;

  // 모델 신뢰도 (vLLM logprob에서)
  avgLogprob?: number;         // 평균 log probability (-0 ~ -inf, 0에 가까울수록 확신)

  // 에이전트 정보
  reputation?: number;         // 0~1 (평판 시스템에서)
  tier?: string;               // "small" | "medium" | "large" | "flagship"

  // 전문화 정보
  specialization?: string;     // 에이전트의 전문 도메인
  requestDomain?: string;      // 이번 요청의 도메인

  // 과거 피드백
  thumbsUpRate?: number;       // 이 에이전트의 👍 비율 (0~1)
  totalFeedbacks?: number;     // 피드백 총 수 (적으면 신뢰도 낮음)
}

export interface ResponseWeight {
  agentId: string;
  totalScore: number;          // 0~1 (종합 가중치)

  // 개별 점수
  logprobScore: number;
  reputationScore: number;
  specializationScore: number;
  feedbackScore: number;

  // 판정
  confidenceLevel: "high" | "medium" | "low";
  shouldAddDisclaimer: boolean;  // 신뢰도 낮으면 면책조항 추가
  rewardMultiplier: number;      // 보상 배율 (품질 높으면 더 많은 코인)
}

// ─── 개별 점수 계산 ─────────────────────────────────────────

function calcLogprobScore(avgLogprob?: number): number {
  /**
   * logprob → 0~1 점수 변환.
   * logprob = 0: 완벽한 확신 → 1.0
   * logprob = -1: 보통 → 0.7
   * logprob = -3: 불확실 → 0.3
   * logprob = -5+: 매우 불확실 → 0.1
   */
  if (avgLogprob === undefined || avgLogprob === null) return 0.5; // 정보 없으면 중립

  // sigmoid 변환: 1 / (1 + e^(-logprob * 2))
  const score = 1 / (1 + Math.exp(avgLogprob * 2));
  return Math.max(0, Math.min(1, score));
}

function calcReputationScore(reputation?: number): number {
  /**
   * 에이전트 평판 → 점수.
   * 0.9+ (diamond): 1.0
   * 0.7~0.9 (gold/silver): 0.7~0.9
   * 0.4~0.7 (bronze): 0.4~0.7
   * <0.4: 0.2
   */
  if (reputation === undefined) return 0.5;
  return Math.max(0.1, Math.min(1.0, reputation));
}

function calcSpecializationScore(
  agentSpecialization?: string,
  requestDomain?: string,
): number {
  /**
   * 에이전트 전문화와 요청 도메인의 일치도.
   * 완전 일치: 1.0
   * 관련: 0.6
   * 불일치: 0.3
   * 정보 없음: 0.5
   */
  if (!agentSpecialization || !requestDomain) return 0.5;

  if (agentSpecialization === requestDomain) return 1.0;

  // 관련 도메인 매핑
  const related: Record<string, string[]> = {
    coding: ["general"],
    legal: ["tax"],
    tax: ["legal"],
    general: ["coding", "legal", "tax"],
  };

  if (related[agentSpecialization]?.includes(requestDomain)) return 0.6;

  return 0.3;
}

function calcFeedbackScore(thumbsUpRate?: number, totalFeedbacks?: number): number {
  /**
   * 과거 유저 피드백 기반 점수.
   * 피드백 많고 👍 높으면 → 높은 점수.
   * 피드백 적으면 → 중립 (데이터 부족).
   */
  if (thumbsUpRate === undefined || totalFeedbacks === undefined) return 0.5;

  // 피드백 수가 적으면 중립으로 회귀 (Bayesian smoothing)
  const minSamples = 20;
  const prior = 0.5;
  const smoothed = (thumbsUpRate * totalFeedbacks + prior * minSamples)
                   / (totalFeedbacks + minSamples);

  return Math.max(0.1, Math.min(1.0, smoothed));
}

// ─── 종합 가중치 계산 ────────────────────────────────────────

export function calculateResponseWeight(meta: AgentResponseMeta): ResponseWeight {
  const logprobScore = calcLogprobScore(meta.avgLogprob);
  const reputationScore = calcReputationScore(meta.reputation);
  const specializationScore = calcSpecializationScore(meta.specialization, meta.requestDomain);
  const feedbackScore = calcFeedbackScore(meta.thumbsUpRate, meta.totalFeedbacks);

  // 가중 합산
  const totalScore =
    logprobScore * WEIGHT_CONFIG.modelLogprob +
    reputationScore * WEIGHT_CONFIG.agentReputation +
    specializationScore * WEIGHT_CONFIG.specialization +
    feedbackScore * WEIGHT_CONFIG.userFeedback;

  // 신뢰도 등급
  let confidenceLevel: ResponseWeight["confidenceLevel"];
  if (totalScore >= 0.75) confidenceLevel = "high";
  else if (totalScore >= 0.5) confidenceLevel = "medium";
  else confidenceLevel = "low";

  // 면책조항 필요 여부
  const shouldAddDisclaimer = totalScore < 0.5;

  // 보상 배율 (품질 높으면 더 많은 코인)
  let rewardMultiplier: number;
  if (totalScore >= 0.8) rewardMultiplier = 1.5;
  else if (totalScore >= 0.6) rewardMultiplier = 1.2;
  else if (totalScore >= 0.4) rewardMultiplier = 1.0;
  else rewardMultiplier = 0.7;

  return {
    agentId: meta.agentId,
    totalScore: Math.round(totalScore * 1000) / 1000,
    logprobScore: Math.round(logprobScore * 1000) / 1000,
    reputationScore: Math.round(reputationScore * 1000) / 1000,
    specializationScore: Math.round(specializationScore * 1000) / 1000,
    feedbackScore: Math.round(feedbackScore * 1000) / 1000,
    confidenceLevel,
    shouldAddDisclaimer,
    rewardMultiplier,
  };
}

// ─── 여러 응답 중 최적 선택 ──────────────────────────────────

export function selectBestResponse(
  responses: AgentResponseMeta[],
): {
  best: AgentResponseMeta;
  weight: ResponseWeight;
  allWeights: ResponseWeight[];
  reason: string;
} {
  if (responses.length === 0) {
    throw new Error("응답 없음");
  }

  if (responses.length === 1) {
    const w = calculateResponseWeight(responses[0]);
    return {
      best: responses[0],
      weight: w,
      allWeights: [w],
      reason: "단일 응답",
    };
  }

  const allWeights = responses.map((r) => calculateResponseWeight(r));

  // 최고 점수 응답 선택
  let bestIdx = 0;
  let bestScore = allWeights[0].totalScore;

  for (let i = 1; i < allWeights.length; i++) {
    if (allWeights[i].totalScore > bestScore) {
      bestScore = allWeights[i].totalScore;
      bestIdx = i;
    }
  }

  const bestWeight = allWeights[bestIdx];
  const secondBest = allWeights
    .filter((_, i) => i !== bestIdx)
    .sort((a, b) => b.totalScore - a.totalScore)[0];

  const margin = secondBest
    ? bestWeight.totalScore - secondBest.totalScore
    : 1;

  const reason = margin > 0.2
    ? `${bestWeight.agentId} 압도적 (${bestWeight.totalScore} vs ${secondBest?.totalScore})`
    : `${bestWeight.agentId} 근소 차이 (${bestWeight.totalScore} vs ${secondBest?.totalScore})`;

  return {
    best: responses[bestIdx],
    weight: bestWeight,
    allWeights,
    reason,
  };
}

// ─── 응답에 신뢰도 메타데이터 추가 ──────────────────────────

export function enrichResponseWithWeight(
  response: string,
  weight: ResponseWeight,
): string {
  let enriched = response;

  // 낮은 신뢰도 → 면책조항
  if (weight.shouldAddDisclaimer) {
    enriched += `\n\n---\n⚠️ 이 응답의 신뢰도가 낮습니다 (${(weight.totalScore * 100).toFixed(0)}%). 중요한 결정은 전문가와 상담하세요.`;
  }

  return enriched;
}

// ─── Chat API용 인터페이스 ──────────────────────────────────

export function buildResponseWeightMeta(weight: ResponseWeight): Record<string, any> {
  return {
    responseWeight: {
      totalScore: weight.totalScore,
      confidence: weight.confidenceLevel,
      breakdown: {
        modelConfidence: weight.logprobScore,
        agentReputation: weight.reputationScore,
        specialization: weight.specializationScore,
        userFeedback: weight.feedbackScore,
      },
      rewardMultiplier: weight.rewardMultiplier,
    },
  };
}
