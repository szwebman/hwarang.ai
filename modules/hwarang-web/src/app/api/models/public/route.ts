/**
 * 공개 AI 모델 목록 (일반 사용자용)
 *
 * GET /api/models/public
 *   인증된 사용자에게 활성·공개 모델 목록을 반환.
 *   admin API 와 분리해, 운영자 전용 vLLM 메타 노출 없이
 *   채팅 입력창의 모델 선택 드롭다운에서 사용한다.
 */

import { NextRequest } from "next/server";
import { auth } from "@/lib/auth";
import { prisma } from "@/lib/db";
import crypto from "crypto";

async function resolveUserId(request: NextRequest): Promise<string | null> {
  const authHeader = request.headers.get("authorization");
  if (authHeader?.startsWith("Bearer ")) {
    const rawKey = authHeader.slice(7).trim();
    if (rawKey) {
      const keyHash = crypto.createHash("sha256").update(rawKey).digest("hex");
      const apiKey = await prisma.apiKey.findFirst({
        where: { keyHash, isActive: true },
        select: { userId: true },
      });
      if (apiKey) return apiKey.userId;
    }
  }
  const session = await auth();
  return session?.user?.id || null;
}

export async function GET(request: NextRequest) {
  const userId = await resolveUserId(request);
  if (!userId) {
    return Response.json({ models: [] }, { status: 401 });
  }

  try {
    const models = await prisma.aIModel.findMany({
      where: { isActive: true, isPublic: true },
      select: {
        name: true,
        displayName: true,
        description: true,
        category: true,
        tier: true,
        isDefault: true,
      },
      orderBy: [{ isDefault: "desc" }, { sortOrder: "asc" }],
    });

    return Response.json({ models });
  } catch (e: any) {
    console.error("GET /api/models/public error:", e?.message);
    return Response.json({ models: [] }, { status: 500 });
  }
}
