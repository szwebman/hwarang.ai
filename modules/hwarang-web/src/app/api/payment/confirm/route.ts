/**
 * 토스페이먼츠 결제 승인 API
 * POST /api/payment/confirm
 *
 * 토스 결제창에서 결제 완료 후 콜백으로 호출.
 * 서버에서 토스 API로 결제 승인 → DB 업데이트 → 토큰 지급.
 */

import { NextRequest } from "next/server";
import { prisma } from "@/lib/db";

const TOSS_SECRET_KEY = process.env.TOSS_SECRET_KEY || "";

export async function POST(request: NextRequest) {
  const { paymentKey, orderId, amount } = await request.json();

  if (!paymentKey || !orderId || !amount) {
    return Response.json({ error: "필수 파라미터 누락" }, { status: 400 });
  }

  // DB에서 결제 정보 조회
  const payment = await prisma.payment.findUnique({
    where: { pgOrderId: orderId },
  });

  if (!payment) {
    return Response.json({ error: "결제 정보 없음" }, { status: 404 });
  }

  if (payment.amount !== amount) {
    return Response.json({ error: "금액 불일치" }, { status: 400 });
  }

  // 토스 결제 승인 API 호출
  try {
    const authHeader = Buffer.from(`${TOSS_SECRET_KEY}:`).toString("base64");

    const tossResp = await fetch("https://api.tosspayments.com/v1/payments/confirm", {
      method: "POST",
      headers: {
        "Authorization": `Basic ${authHeader}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ paymentKey, orderId, amount }),
    });

    const tossData = await tossResp.json();

    if (!tossResp.ok) {
      await prisma.payment.update({
        where: { id: payment.id },
        data: { status: "FAILED" },
      });
      return Response.json({
        error: tossData.message || "결제 승인 실패",
      }, { status: 400 });
    }

    // 결제 성공 → DB 업데이트
    await prisma.payment.update({
      where: { id: payment.id },
      data: {
        status: "PAID",
        pgPaymentId: paymentKey,
        method: tossData.method,
        paidAt: new Date(),
      },
    });

    // 토큰 지급 (플랜 구독 또는 토큰 구매)
    if (payment.billingType === "monthly" && payment.planName) {
      // 플랜 구독 → 플랜 변경 + 토큰 리셋
      const plan = await prisma.plan.findUnique({ where: { name: payment.planName } });
      if (plan) {
        await prisma.user.update({
          where: { id: payment.userId },
          data: { planId: plan.id },
        });

        await prisma.tokenBalance.upsert({
          where: { userId: payment.userId },
          update: {
            balance: plan.tokensIncluded,
            dailyLimit: plan.dailyTokenLimit,
            dailyUsed: 0,
            totalCharged: { increment: plan.tokensIncluded },
          },
          create: {
            userId: payment.userId,
            balance: plan.tokensIncluded,
            dailyLimit: plan.dailyTokenLimit,
            totalCharged: plan.tokensIncluded,
          },
        });

        await prisma.tokenTransaction.create({
          data: {
            userId: payment.userId,
            type: "PLAN_CREDIT",
            amount: plan.tokensIncluded,
            balance: plan.tokensIncluded,
            description: `${plan.displayName} 플랜 구독 (${amount.toLocaleString()}원)`,
          },
        });
      }
    } else {
      // 토큰 직접 구매
      const tokenAmount = calculateTokensForAmount(amount);

      await prisma.tokenBalance.upsert({
        where: { userId: payment.userId },
        update: {
          balance: { increment: tokenAmount },
          totalCharged: { increment: tokenAmount },
        },
        create: {
          userId: payment.userId,
          balance: tokenAmount,
          totalCharged: tokenAmount,
        },
      });

      await prisma.tokenTransaction.create({
        data: {
          userId: payment.userId,
          type: "PURCHASE",
          amount: tokenAmount,
          balance: 0,
          description: `토큰 ${tokenAmount.toLocaleString()}개 구매 (${amount.toLocaleString()}원)`,
        },
      });
    }

    return Response.json({
      success: true,
      orderId,
      amount,
      method: tossData.method,
    });
  } catch (e: any) {
    return Response.json({ error: e.message }, { status: 500 });
  }
}

function calculateTokensForAmount(amountKRW: number): number {
  // 1원 = 10 토큰 (기본 환율)
  // 대량 구매 시 보너스
  const base = amountKRW * 10;
  if (amountKRW >= 100000) return Math.floor(base * 1.2);  // 10만원+ → 20% 보너스
  if (amountKRW >= 50000) return Math.floor(base * 1.1);   // 5만원+ → 10% 보너스
  return base;
}
