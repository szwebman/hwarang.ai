/**
 * 현재 사용자 정보 API
 * GET /api/users/me - 내 정보 + 토큰 잔액 + 플랜
 *
 * 인증 방법 (둘 중 하나):
 * 1. NextAuth 세션 쿠키 (웹 브라우저)
 * 2. Bearer API 키 헤더: Authorization: Bearer hk-xxx (VS Code 확장팩 등)
 */

import { NextRequest } from "next/server";
import { auth } from "@/lib/auth";
import { prisma } from "@/lib/db";
import crypto from "crypto";

async function resolveUserId(request: NextRequest): Promise<string | null> {
  // 1. Bearer API 키 확인
  const authHeader = request.headers.get("authorization");
  if (authHeader?.startsWith("Bearer ")) {
    const rawKey = authHeader.slice(7).trim();
    if (rawKey) {
      const keyHash = crypto.createHash("sha256").update(rawKey).digest("hex");
      const apiKey = await prisma.apiKey.findFirst({
        where: { keyHash, isActive: true },
        select: { userId: true, id: true },
      });
      if (apiKey) {
        // 사용 기록 업데이트 (비동기, fire-and-forget)
        prisma.apiKey
          .update({ where: { id: apiKey.id }, data: { lastUsedAt: new Date() } })
          .catch(() => {});
        return apiKey.userId;
      }
    }
  }

  // 2. NextAuth 세션
  const session = await auth();
  return session?.user?.id || null;
}

export async function GET(request: NextRequest) {
  const userId = await resolveUserId(request);

  if (!userId) {
    return Response.json({ error: "로그인이 필요합니다" }, { status: 401 });
  }

  try {
    const user = await prisma.user.findUnique({
      where: { id: userId },
      include: {
        plan: true,
        tokenBalance: true,
        apiKeys: {
          where: { isActive: true },
          select: { id: true, name: true, keyPrefix: true, lastUsedAt: true, createdAt: true },
        },
        _count: { select: { conversations: true, usageRecords: true } },
      },
    });

    if (!user) {
      return Response.json({ error: "유저를 찾을 수 없습니다" }, { status: 404 });
    }

    // 일일 / 월간 lazy 리셋 체크
    if (user.tokenBalance) {
      const now = new Date();
      const updates: Record<string, unknown> = {};

      // 일일 리셋
      const dailyResetAt = user.tokenBalance.dailyResetAt;
      if (!dailyResetAt || now > dailyResetAt) {
        updates.dailyUsed = 0;
        updates.dailyResetAt = new Date(
          now.getFullYear(),
          now.getMonth(),
          now.getDate() + 1
        );
        user.tokenBalance.dailyUsed = 0;
      }

      // 월간 리셋 — monthlyResetAt 지났으면 plan.tokensIncluded 로 잔액 리필
      const monthlyResetAt = (user.tokenBalance as { monthlyResetAt?: Date | null }).monthlyResetAt;
      if (
        user.tokenBalance.monthlyReset &&
        (!monthlyResetAt || now > monthlyResetAt)
      ) {
        const planTokens = user.plan?.tokensIncluded ?? 50000000;
        updates.balance = planTokens;
        updates.monthlyUsed = 0;
        updates.monthlyResetAt = new Date(
          now.getFullYear(),
          now.getMonth() + 1,
          1
        );
        updates.lastResetAt = now;
        user.tokenBalance.balance = planTokens;
      }

      if (Object.keys(updates).length > 0) {
        await prisma.tokenBalance.update({
          where: { userId },
          data: updates,
        });
      }
    }

    return Response.json({
      id: user.id,
      name: user.name,
      email: user.email,
      image: user.image,
      role: user.role,
      plan: user.plan,
      tokens: user.tokenBalance
        ? {
            balance: user.tokenBalance.balance,
            dailyUsed: user.tokenBalance.dailyUsed,
            dailyLimit: user.tokenBalance.dailyLimit,
            totalUsed: user.tokenBalance.totalUsed,
          }
        : null,
      apiKeys: user.apiKeys,
      stats: {
        conversations: user._count.conversations,
        totalRequests: user._count.usageRecords,
      },
    });
  } catch (e: any) {
    console.error("GET /api/users/me error:", e.message);
    return Response.json({ error: "서버 오류" }, { status: 500 });
  }
}
