/**
 * 회원가입 API
 * POST /api/auth/register
 */

import { NextRequest } from "next/server";
import { prisma } from "@/lib/db";
import crypto from "crypto";

function hashPassword(password: string): string {
  return crypto.createHash("sha256").update(password).digest("hex");
}

export async function POST(request: NextRequest) {
  try {
    const { email, password, name } = await request.json();

    if (!email || !password) {
      return Response.json({ error: "이메일과 비밀번호를 입력하세요" }, { status: 400 });
    }

    if (password.length < 8) {
      return Response.json({ error: "비밀번호는 8자 이상이어야 합니다" }, { status: 400 });
    }

    // 이메일 중복 확인
    const existing = await prisma.user.findUnique({ where: { email } });
    if (existing) {
      return Response.json({ error: "이미 가입된 이메일입니다" }, { status: 409 });
    }

    // Free 플랜 찾기
    const freePlan = await prisma.plan.findUnique({ where: { name: "free" } });

    // 유저 생성
    const user = await prisma.user.create({
      data: {
        email,
        name: name || email.split("@")[0],
        hashedPassword: hashPassword(password),
        isActive: true,
        planId: freePlan?.id,
      },
    });

    // 토큰 잔액 초기화 (Free 플랜: 10M 토큰)
    await prisma.tokenBalance.create({
      data: {
        userId: user.id,
        balance: 10000000,
        dailyLimit: 1000000,
        totalCharged: 10000000,
      },
    });

    // 웰컴 토큰 거래 기록
    await prisma.tokenTransaction.create({
      data: {
        userId: user.id,
        type: "PLAN_CREDIT",
        amount: 10000,
        balance: 10000,
        description: "회원가입 웰컴 토큰 (Free 플랜)",
      },
    });

    return Response.json({
      success: true,
      user: {
        id: user.id,
        email: user.email,
        name: user.name,
      },
    }, { status: 201 });
  } catch (e: any) {
    console.error("회원가입 오류:", e);
    return Response.json({ error: "회원가입 중 오류가 발생했습니다" }, { status: 500 });
  }
}
