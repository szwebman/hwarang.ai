/**
 * 레퍼럴/추천인 프로그램 API
 *
 * GET  /api/referral       - 내 추천 코드 + 통계
 * POST /api/referral       - 추천 코드 적용
 * GET  /api/referral/stats - 추천 통계
 *
 * 보상:
 *   추천한 사람: 5,000 토큰
 *   추천받은 사람: 3,000 토큰 (웰컴 보너스)
 */

import { NextRequest } from "next/server";
import { auth } from "@/lib/auth";
import { prisma } from "@/lib/db";
import crypto from "crypto";

export async function GET(request: NextRequest) {
  const session = await auth();
  if (!session?.user?.id) return Response.json({ error: "로그인 필요" }, { status: 401 });

  // 추천 코드 생성/조회
  let setting = await prisma.systemSetting.findUnique({
    where: { key: `referral_code_${session.user.id}` },
  });

  if (!setting) {
    const code = `HWR${crypto.randomBytes(4).toString("hex").toUpperCase()}`;
    setting = await prisma.systemSetting.create({
      data: { key: `referral_code_${session.user.id}`, value: code },
    });
  }

  // 추천 통계
  const referrals = await prisma.tokenTransaction.count({
    where: {
      userId: session.user.id,
      type: "REFERRAL",
    },
  });

  return Response.json({
    code: setting.value,
    shareUrl: `https://hwarang.ai/register?ref=${setting.value}`,
    totalReferrals: referrals,
    rewardPerReferral: 5000,
  });
}

export async function POST(request: NextRequest) {
  const session = await auth();
  if (!session?.user?.id) return Response.json({ error: "로그인 필요" }, { status: 401 });

  const { code } = await request.json();
  if (!code) return Response.json({ error: "추천 코드 필요" }, { status: 400 });

  // 추천 코드 소유자 찾기
  const settings = await prisma.systemSetting.findMany({
    where: { key: { startsWith: "referral_code_" }, value: code },
  });

  if (settings.length === 0) {
    return Response.json({ error: "유효하지 않은 추천 코드" }, { status: 404 });
  }

  const referrerId = settings[0].key.replace("referral_code_", "");

  // 자기 자신 추천 방지
  if (referrerId === session.user.id) {
    return Response.json({ error: "본인의 추천 코드는 사용 불가" }, { status: 400 });
  }

  // 이미 적용된 추천 체크
  const existing = await prisma.tokenTransaction.findFirst({
    where: { userId: session.user.id, type: "REFERRAL" },
  });
  if (existing) {
    return Response.json({ error: "이미 추천 코드를 적용했습니다" }, { status: 409 });
  }

  // 보상 지급 (추천인 5000, 피추천인 3000)
  await Promise.all([
    // 추천인 보상
    prisma.tokenBalance.update({
      where: { userId: referrerId },
      data: { balance: { increment: 5000 }, totalCharged: { increment: 5000 } },
    }),
    prisma.tokenTransaction.create({
      data: {
        userId: referrerId,
        type: "REFERRAL",
        amount: 5000,
        balance: 0,
        description: `추천 보상 (${session.user.email})`,
      },
    }),
    // 피추천인 보상
    prisma.tokenBalance.update({
      where: { userId: session.user.id },
      data: { balance: { increment: 3000 }, totalCharged: { increment: 3000 } },
    }),
    prisma.tokenTransaction.create({
      data: {
        userId: session.user.id,
        type: "REFERRAL",
        amount: 3000,
        balance: 0,
        description: `추천 코드 적용 보너스 (${code})`,
      },
    }),
  ]);

  return Response.json({ success: true, bonusTokens: 3000 });
}
