/**
 * GRPO 피드백 수집 API
 * POST /api/feedback
 *
 * 유저가 AI 응답에 대해 피드백을 제출하면 토큰 보상 지급.
 */

import { NextRequest } from "next/server";
import { auth } from "@/lib/auth";
import { submitGRPOFeedback, type GRPOFeedback } from "@/lib/alignment/grpo";

export async function POST(request: NextRequest) {
  const session = await auth();
  if (!session?.user?.id) {
    return Response.json({ error: "로그인이 필요합니다" }, { status: 401 });
  }

  try {
    const body = await request.json();

    if (!body.messageId || !body.rating) {
      return Response.json({ error: "messageId와 rating 필수" }, { status: 400 });
    }

    const feedback: GRPOFeedback = {
      conversationId: body.conversationId || "",
      messageId: body.messageId,
      userId: session.user.id,
      rating: body.rating,
      stars: body.stars,
      reason: body.reason,
      betterResponse: body.betterResponse,
      categories: body.categories,
    };

    const result = await submitGRPOFeedback(feedback);

    // HSEE Phase 1: RLHFFeedback 풀에도 반영 (fire-and-forget)
    try {
      const HWARANG_API_URL = process.env.HWARANG_API_URL || "http://localhost:8000";
      const INTERNAL_KEY = process.env.HWARANG_INTERNAL_KEY || "";
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (INTERNAL_KEY) headers.Authorization = `Bearer ${INTERNAL_KEY}`;

      // GRPO rating: "good"|"bad"|"neutral" (lib/alignment/grpo) → -1/0/1 매핑
      let numericRating = 0;
      const r = String(body.rating).toLowerCase();
      if (["good", "positive", "up", "1"].includes(r)) numericRating = 1;
      else if (["bad", "negative", "down", "-1"].includes(r)) numericRating = -1;

      fetch(`${HWARANG_API_URL}/api/learning/feedback`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          message_id: body.messageId,
          user_id: session.user.id,
          rating: numericRating,
          comment: body.reason || body.betterResponse || null,
        }),
      }).catch(() => {});
    } catch {}

    return Response.json({
      success: true,
      feedbackId: result.feedbackId,
      rewards: result.rewards,
      message: `피드백 감사합니다! ${result.rewards.total} 토큰이 지급되었습니다.`,
    });
  } catch (e: any) {
    console.error("피드백 저장 실패:", e);
    return Response.json({ error: e.message || "서버 오류" }, { status: 500 });
  }
}
