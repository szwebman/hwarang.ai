/**
 * GRPO - Grid-based RLHF
 *
 * 화랑 AI 고유 정렬 기법 #3 (가장 독창적!)
 *
 * Anthropic RLHF: 직원이 피드백 작성 (비싸고 느림, 서양 가치관)
 * 화랑 GRPO:    Grid 참여자가 피드백 + 토큰 보상 (지속적, 한국인 실사용자)
 *
 * 동작:
 *   1. 유저 응답에 👍/👎 버튼
 *   2. 상세 피드백 작성 시 추가 토큰 보상
 *   3. 피드백 DB에 축적
 *   4. 주기적으로 DPO 데이터로 변환
 *   5. LoRA 어댑터 업데이트 → 재배포
 */

import { PrismaClient } from "@prisma/client";

const prisma = new PrismaClient();

// ─── 피드백 타입 ────────────────────────────────────────────────

export type FeedbackRating = "thumbs_up" | "thumbs_down" | "star";

export interface GRPOFeedback {
  conversationId: string;
  messageId: string;
  userId: string;
  rating: FeedbackRating;
  stars?: number;                     // 1~5 (rating === "star"인 경우)
  reason?: string;                    // 왜 좋거나 나쁜지
  betterResponse?: string;             // 더 나은 답변 제안 (선택)
  categories?: FeedbackCategory[];    // 문제 카테고리
}

export type FeedbackCategory =
  | "inaccurate"        // 사실 오류
  | "hallucination"     // 환각 (없는 사실)
  | "chinese_mixed"     // 중국어 섞임
  | "rude"              // 무례함
  | "unhelpful"         // 도움 안 됨
  | "excellent"         // 훌륭함
  | "clear"             // 명확함
  | "insightful"        // 통찰력 있음
  | "code_bug"          // 코드 버그
  | "legal_wrong"       // 법률 오류
  | "tax_wrong";        // 세무 오류

// ─── 토큰 보상 계산 ────────────────────────────────────────────

export interface GRPORewards {
  baseReward: number;        // 기본 피드백 보상
  qualityBonus: number;      // 상세 피드백 보너스
  streakBonus: number;       // 연속 참여 보너스
  total: number;
}

export function calculateGRPORewards(
  feedback: GRPOFeedback,
  userStreak: number = 0
): GRPORewards {
  let base = 0;
  let quality = 0;

  // 기본 보상 (평가만 해도)
  if (feedback.rating) base += 10;  // 10 토큰

  // 상세 피드백 보너스
  if (feedback.reason && feedback.reason.length > 20) quality += 20;
  if (feedback.betterResponse && feedback.betterResponse.length > 50) quality += 50;
  if (feedback.categories && feedback.categories.length > 0) quality += 10;

  // 연속 참여 보너스 (최대 100토큰)
  const streak = Math.min(userStreak, 30);  // 30일 최대
  const streakBonus = streak * 3;  // 일당 3토큰

  return {
    baseReward: base,
    qualityBonus: quality,
    streakBonus,
    total: base + quality + streakBonus,
  };
}

// ─── 피드백 저장 + 보상 지급 ────────────────────────────────────

export async function submitGRPOFeedback(feedback: GRPOFeedback): Promise<{
  feedbackId: string;
  rewards: GRPORewards;
}> {
  // 1. 유저 streak 계산 (최근 24시간 내 피드백 횟수)
  const recentFeedbacks = await prisma.$queryRaw<Array<{ count: bigint }>>`
    SELECT COUNT(*) as count FROM "TokenTransaction"
    WHERE "userId" = ${feedback.userId}
      AND type = 'GRID_STREAK'
      AND "createdAt" >= NOW() - INTERVAL '30 days'
  `;
  const streak = Number(recentFeedbacks[0]?.count ?? 0);

  // 2. 보상 계산
  const rewards = calculateGRPORewards(feedback, streak);

  // 3. 피드백 저장 (ConversationFeedback 테이블)
  // 주: 이 테이블은 아직 스키마에 추가 안됨, GRPOFeedback 모델 필요
  //     현재는 TokenTransaction의 metadata에 저장
  const feedbackRecord = await prisma.tokenTransaction.create({
    data: {
      userId: feedback.userId,
      type: "GRID_REWARD",
      amount: rewards.total,
      balance: 0,  // 나중에 업데이트
      description: `피드백 보상: ${feedback.rating === "thumbs_up" ? "좋아요" : feedback.rating === "thumbs_down" ? "싫어요" : "별점"}`,
      metadata: {
        type: "grpo_feedback",
        conversationId: feedback.conversationId,
        messageId: feedback.messageId,
        rating: feedback.rating,
        stars: feedback.stars,
        reason: feedback.reason,
        betterResponse: feedback.betterResponse,
        categories: feedback.categories,
        rewards: rewards as any,
      } as any,
    },
  });

  // 4. 토큰 잔액 업데이트
  const balance = await prisma.tokenBalance.update({
    where: { userId: feedback.userId },
    data: {
      balance: { increment: rewards.total },
      totalCharged: { increment: rewards.total },
    },
  });

  // 잔액 기록 업데이트
  await prisma.tokenTransaction.update({
    where: { id: feedbackRecord.id },
    data: { balance: balance.balance },
  });

  return {
    feedbackId: feedbackRecord.id,
    rewards,
  };
}

// ─── DPO 데이터 추출 (학습용) ──────────────────────────────────

export interface DPOPair {
  prompt: string;
  chosen: string;
  rejected: string;
  source: "grpo";
  metadata: Record<string, any>;
}

export async function extractDPOPairsFromGRPO(
  minFeedbackCount: number = 5,
  limit: number = 10000
): Promise<DPOPair[]> {
  // 👍 받은 응답들
  const positiveFeedbacks = await prisma.tokenTransaction.findMany({
    where: {
      type: "GRID_REWARD",
      metadata: { path: ["rating"], equals: "thumbs_up" },
    },
    orderBy: { createdAt: "desc" },
    take: limit,
  });

  // 👎 받은 응답들
  const negativeFeedbacks = await prisma.tokenTransaction.findMany({
    where: {
      type: "GRID_REWARD",
      metadata: { path: ["rating"], equals: "thumbs_down" },
    },
    orderBy: { createdAt: "desc" },
    take: limit,
  });

  // 같은 질문에 대한 좋은/나쁜 응답 쌍 만들기
  const pairs: DPOPair[] = [];

  // 간단한 방식: 나쁜 응답에 대해 개선된 응답(betterResponse)이 있으면 쌍으로
  for (const neg of negativeFeedbacks) {
    const meta = neg.metadata as any;
    if (meta?.betterResponse && meta?.conversationId) {
      // 원본 대화 조회
      const conv = await prisma.conversation.findUnique({
        where: { id: meta.conversationId },
        include: {
          messages: { orderBy: { createdAt: "asc" } },
        },
      });

      if (conv) {
        // 해당 메시지 위치 찾기
        const msgIdx = conv.messages.findIndex((m) => m.id === meta.messageId);
        if (msgIdx > 0) {
          const userMsg = conv.messages[msgIdx - 1];
          const aiMsg = conv.messages[msgIdx];

          if (userMsg.role === "user" && aiMsg.role === "assistant") {
            pairs.push({
              prompt: userMsg.content,
              chosen: meta.betterResponse,      // 유저가 제안한 더 나은 답
              rejected: aiMsg.content,           // 싫어요 받은 원래 답
              source: "grpo",
              metadata: {
                reason: meta.reason,
                categories: meta.categories,
                feedbackId: neg.id,
              },
            });
          }
        }
      }
    }
  }

  return pairs;
}

// ─── 피드백 통계 (어드민 대시보드용) ───────────────────────────

export async function getGRPOStats(): Promise<{
  totalFeedbacks: number;
  thumbsUp: number;
  thumbsDown: number;
  withBetterResponse: number;
  rewardsDistributed: number;
  topContributors: Array<{ userId: string; count: number; rewards: number }>;
}> {
  const all = await prisma.tokenTransaction.findMany({
    where: { type: "GRID_REWARD" },
  });

  let thumbsUp = 0;
  let thumbsDown = 0;
  let withBetter = 0;
  let rewardSum = 0;
  const contributorMap: Record<string, { count: number; rewards: number }> = {};

  for (const t of all) {
    const meta = t.metadata as any;
    if (!meta) continue;

    if (meta.rating === "thumbs_up") thumbsUp++;
    if (meta.rating === "thumbs_down") thumbsDown++;
    if (meta.betterResponse) withBetter++;

    rewardSum += t.amount;

    if (!contributorMap[t.userId]) {
      contributorMap[t.userId] = { count: 0, rewards: 0 };
    }
    contributorMap[t.userId].count++;
    contributorMap[t.userId].rewards += t.amount;
  }

  const topContributors = Object.entries(contributorMap)
    .map(([userId, data]) => ({ userId, ...data }))
    .sort((a, b) => b.rewards - a.rewards)
    .slice(0, 10);

  return {
    totalFeedbacks: all.length,
    thumbsUp,
    thumbsDown,
    withBetterResponse: withBetter,
    rewardsDistributed: rewardSum,
    topContributors,
  };
}
