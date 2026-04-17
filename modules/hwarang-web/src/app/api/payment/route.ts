/**
 * 결제 API (토스페이먼츠 연동)
 *
 * POST /api/payment         - 결제 요청 (토큰 구매 / 플랜 구독)
 * POST /api/payment/confirm  - 결제 승인 (토스 콜백)
 * GET  /api/payment/history  - 결제 내역
 */

import { NextRequest } from "next/server";
import { auth } from "@/lib/auth";
import { prisma } from "@/lib/db";

const TOSS_SECRET_KEY = process.env.TOSS_SECRET_KEY || "";
const TOSS_API_URL = "https://api.tosspayments.com/v1/payments";

// ─── 결제 요청 생성 ─────────────────────────────────────────

export async function POST(request: NextRequest) {
  const session = await auth();
  if (!session?.user?.id) {
    return Response.json({ error: "로그인 필요" }, { status: 401 });
  }

  const body = await request.json();
  const { type, planName, tokenAmount, amount } = body;

  // 주문번호 생성
  const orderId = `HWR_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

  // DB에 결제 대기 기록
  const payment = await prisma.payment.create({
    data: {
      userId: session.user.id,
      amount: amount,
      status: "PENDING",
      pgProvider: "tosspayments",
      pgOrderId: orderId,
      planName: type === "subscription" ? planName : null,
      billingType: type === "subscription" ? "monthly" : "one-time",
      description: type === "subscription"
        ? `${planName} 플랜 구독`
        : `토큰 ${tokenAmount?.toLocaleString()}개 구매`,
    },
  });

  return Response.json({
    orderId,
    paymentId: payment.id,
    amount,
    orderName: payment.description,
    // 프론트에서 토스 SDK로 결제창 호출
  });
}

// ─── 결제 내역 ──────────────────────────────────────────────

export async function GET(request: NextRequest) {
  const session = await auth();
  if (!session?.user?.id) {
    return Response.json({ error: "로그인 필요" }, { status: 401 });
  }

  const payments = await prisma.payment.findMany({
    where: { userId: session.user.id },
    orderBy: { createdAt: "desc" },
    take: 50,
  });

  return Response.json(payments);
}
