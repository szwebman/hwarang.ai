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
