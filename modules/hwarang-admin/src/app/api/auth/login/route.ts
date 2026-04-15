/**
 * 관리자 로그인 API
 *
 * ADMIN 또는 SUPER_ADMIN 역할만 로그인 가능.
 * JWT 토큰 발급.
 */

import { NextRequest } from "next/server";
import { prisma } from "@/lib/db";
import crypto from "crypto";

function hashPassword(password: string): string {
  return crypto.createHash("sha256").update(password).digest("hex");
}

function generateToken(userId: string, role: string): string {
  const payload = JSON.stringify({ userId, role, exp: Date.now() + 24 * 60 * 60 * 1000 });
  const secret = process.env.ADMIN_SECRET || "hwarang-admin-secret";
  const sig = crypto.createHmac("sha256", secret).update(payload).digest("hex");
  return Buffer.from(payload).toString("base64") + "." + sig;
}

export async function POST(request: NextRequest) {
  const { email, password } = await request.json();

  if (!email || !password) {
    return Response.json({ error: "이메일과 비밀번호를 입력하세요" }, { status: 400 });
  }

  try {
    const user = await prisma.user.findUnique({ where: { email } });

    if (!user) {
      return Response.json({ error: "계정을 찾을 수 없습니다" }, { status: 401 });
    }

    // 역할 확인
    if (user.role !== "ADMIN" && user.role !== "SUPER_ADMIN") {
      return Response.json({ error: "관리자 권한이 없습니다" }, { status: 403 });
    }

    // 비밀번호 확인
    if (user.hashedPassword && user.hashedPassword !== hashPassword(password)) {
      return Response.json({ error: "비밀번호가 틀렸습니다" }, { status: 401 });
    }

    // 토큰 발급
    const token = generateToken(user.id, user.role);

    return Response.json({
      token,
      user: {
        id: user.id,
        name: user.name,
        email: user.email,
        role: user.role,
      },
    });
  } catch (e: any) {
    return Response.json({ error: e.message }, { status: 500 });
  }
}
