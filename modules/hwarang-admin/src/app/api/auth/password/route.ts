/**
 * 비밀번호 변경 API
 * PUT /api/auth/password
 */

import { NextRequest } from "next/server";
import { prisma } from "@/lib/db";
import { verifyToken } from "@/lib/auth";
import crypto from "crypto";

function hashPassword(password: string): string {
  return crypto.createHash("sha256").update(password).digest("hex");
}

export async function PUT(request: NextRequest) {
  const authHeader = request.headers.get("authorization");
  const token = authHeader?.replace("Bearer ", "") || "";
  const auth = verifyToken(token);

  if (!auth) {
    return Response.json({ error: "인증 필요" }, { status: 401 });
  }

  try {
    const { currentPassword, newPassword } = await request.json();

    if (!currentPassword || !newPassword) {
      return Response.json({ error: "현재 비밀번호와 새 비밀번호를 입력하세요" }, { status: 400 });
    }

    if (newPassword.length < 6) {
      return Response.json({ error: "새 비밀번호는 6자 이상이어야 합니다" }, { status: 400 });
    }

    const user = await prisma.user.findUnique({ where: { id: auth.userId } });

    if (!user) {
      return Response.json({ error: "유저를 찾을 수 없습니다" }, { status: 404 });
    }

    // 현재 비밀번호 확인
    if (user.hashedPassword !== hashPassword(currentPassword)) {
      return Response.json({ error: "현재 비밀번호가 틀렸습니다" }, { status: 401 });
    }

    // 새 비밀번호 저장
    await prisma.user.update({
      where: { id: auth.userId },
      data: { hashedPassword: hashPassword(newPassword) },
    });

    return Response.json({ success: true });
  } catch (e: any) {
    return Response.json({ error: e.message }, { status: 500 });
  }
}
