/**
 * Vercel Cron — 일일/월간 토큰 리셋
 *
 * 등록: vercel.json 의 crons → "0 0 * * *" (매일 00:00 UTC)
 * 인증: 환경변수 CRON_SECRET 설정 시 Authorization: Bearer <secret> 필수
 *
 * 동작:
 *  1) 모든 TokenBalance.dailyUsed = 0, dailyResetAt = 다음 자정
 *  2) 매월 1일에는 추가로 balance = plan.tokensIncluded, monthlyUsed = 0,
 *     monthlyResetAt = 다음 달 1일
 */

import { NextRequest } from "next/server";
import { prisma } from "@/lib/db";

export async function GET(req: NextRequest) {
  // Vercel Cron 인증 (CRON_SECRET 설정 시)
  const cronSecret = process.env.CRON_SECRET;
  if (cronSecret) {
    const authHeader = req.headers.get("authorization");
    if (authHeader !== `Bearer ${cronSecret}`) {
      return Response.json({ error: "unauthorized" }, { status: 401 });
    }
  }

  const now = new Date();

  // 1) 일일 리셋 — 모든 사용자
  const tomorrow = new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate() + 1
  );
  const dailyResult = await prisma.tokenBalance.updateMany({
    data: {
      dailyUsed: 0,
      dailyResetAt: tomorrow,
    },
  });

  // 2) 월 리셋 — 매월 1일에만
  const isFirstOfMonth = now.getDate() === 1;
  let monthlyCount = 0;
  if (isFirstOfMonth) {
    const nextMonthFirst = new Date(now.getFullYear(), now.getMonth() + 1, 1);
    const balances = await prisma.tokenBalance.findMany({
      where: { monthlyReset: true },
      include: { user: { include: { plan: true } } },
    });
    for (const b of balances) {
      const planTokens = b.user.plan?.tokensIncluded ?? 50000000;
      await prisma.tokenBalance.update({
        where: { id: b.id },
        data: {
          balance: planTokens,
          monthlyUsed: 0,
          monthlyResetAt: nextMonthFirst,
          lastResetAt: now,
        },
      });
      monthlyCount++;
    }
  }

  return Response.json({
    success: true,
    daily: dailyResult.count,
    monthly: monthlyCount,
    isFirstOfMonth,
    timestamp: now.toISOString(),
  });
}
