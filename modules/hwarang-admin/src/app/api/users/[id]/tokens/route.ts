/**
 * 유저 토큰 수동 조정 API
 * POST /api/users/[id]/tokens
 */

import { NextRequest } from "next/server";
import { prisma } from "@/lib/db";
import { verifyToken } from "@/lib/auth";

function authenticate(request: NextRequest) {
  const authHeader = request.headers.get("authorization");
  const token = authHeader?.replace("Bearer ", "") || "";
  return verifyToken(token);
}

export async function POST(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const auth = authenticate(request);
  if (!auth || auth.role !== "SUPER_ADMIN") {
    return Response.json({ error: "최고 관리자만 토큰을 조정할 수 있습니다" }, { status: 403 });
  }

  const { id } = await params;

  try {
    const { amount, reason } = await request.json();

    if (!amount || typeof amount !== "number") {
      return Response.json({ error: "토큰 수를 입력하세요" }, { status: 400 });
    }

    // 토큰 잔액 업데이트
    const balance = await prisma.tokenBalance.upsert({
      where: { userId: id },
      update: {
        balance: { increment: amount },
        ...(amount > 0 ? { totalCharged: { increment: amount } } : { totalUsed: { increment: Math.abs(amount) } }),
      },
      create: {
        userId: id,
        balance: Math.max(0, amount),
        totalCharged: amount > 0 ? amount : 0,
        totalUsed: amount < 0 ? Math.abs(amount) : 0,
      },
    });

    // 거래 내역 기록
    await prisma.tokenTransaction.create({
      data: {
        userId: id,
        type: "ADMIN_ADJUST",
        amount,
        balance: balance.balance,
        description: reason || "관리자 수동 조정",
        metadata: { adjustedBy: auth.userId },
      },
    });

    return Response.json({ success: true, balance: balance.balance });
  } catch (e: any) {
    return Response.json({ error: e.message }, { status: 500 });
  }
}
