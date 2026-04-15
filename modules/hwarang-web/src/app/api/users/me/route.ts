/**
 * 현재 사용자 정보 API
 * GET /api/users/me - 내 정보 + 토큰 잔액 + 플랜
 */

import { auth } from "@/lib/auth";
import { prisma } from "@/lib/db";

export async function GET() {
  const session = await auth();

  if (!session?.user?.id) {
    return Response.json({ error: "로그인이 필요합니다" }, { status: 401 });
  }

  const userId = session.user.id;

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

    // 일일 리셋 체크
    if (user.tokenBalance) {
      const now = new Date();
      const resetAt = user.tokenBalance.dailyResetAt;
      if (!resetAt || now > resetAt) {
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
      image: user.image,
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
  } catch (e: any) {
    console.error("GET /api/users/me error:", e.message);
    return Response.json({ error: "서버 오류" }, { status: 500 });
  }
}
