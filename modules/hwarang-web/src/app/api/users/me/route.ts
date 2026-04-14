/**
 * 현재 사용자 정보 API
 * GET /api/users/me - 내 정보 + 토큰 잔액 + 플랜
 */

import { NextRequest } from "next/server";
import { prisma } from "@/lib/db";

export async function GET(request: NextRequest) {
  // TODO: 실제 인증에서 userId 가져오기 (NextAuth)
  const userId = request.headers.get("x-user-id") || "demo-user";

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
      return Response.json({ error: "User not found" }, { status: 404 });
    }

    // 일일 리셋 체크
    if (user.tokenBalance) {
      const now = new Date();
      const resetAt = user.tokenBalance.dailyResetAt;
      if (!resetAt || now > resetAt) {
        // 자정 리셋
        await prisma.tokenBalance.update({
          where: { userId },
          data: {
            dailyUsed: 0,
            dailyResetAt: new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1),
          },
        });
        user.tokenBalance.dailyUsed = 0;
      }
    }

    return Response.json({
      id: user.id,
      name: user.name,
      email: user.email,
      role: user.role,
      plan: user.plan,
      tokens: user.tokenBalance ? {
        balance: user.tokenBalance.balance,
        dailyUsed: user.tokenBalance.dailyUsed,
        dailyLimit: user.tokenBalance.dailyLimit,
        totalUsed: user.tokenBalance.totalUsed,
      } : null,
      apiKeys: user.apiKeys,
      stats: {
        conversations: user._count.conversations,
        totalRequests: user._count.usageRecords,
      },
    });
  } catch (error) {
    // DB 연결 전 데모 데이터
    return Response.json(getDemoUser());
  }
}

function getDemoUser() {
  return {
    id: "demo-user",
    name: "데모 사용자",
    email: "demo@hwarang.ai",
    role: "USER",
    plan: { name: "pro", displayName: "Pro", tokensIncluded: 500000, dailyTokenLimit: 50000 },
    tokens: { balance: 342000, dailyUsed: 12000, dailyLimit: 50000, totalUsed: 158000 },
    apiKeys: [
      { id: "1", name: "Production", keyPrefix: "hk-prod-a1b2", lastUsedAt: "2026-04-13", createdAt: "2026-04-01" },
      { id: "2", name: "Development", keyPrefix: "hk-dev-c3d4", lastUsedAt: null, createdAt: "2026-04-05" },
    ],
    stats: { conversations: 45, totalRequests: 1230 },
  };
}
