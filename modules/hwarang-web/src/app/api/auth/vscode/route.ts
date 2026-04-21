/**
 * VS Code 확장팩 API 키 발급
 *
 * POST /api/auth/vscode
 * - 로그인된 사용자에 대해 VS Code용 API 키 생성
 * - rawKey는 1회만 반환 (DB에는 해시만 저장)
 */

import { NextRequest } from "next/server";
import { auth } from "@/lib/auth";
import { prisma } from "@/lib/db";
import crypto from "crypto";

export async function POST(request: NextRequest) {
  const session = await auth();

  if (!session?.user?.id) {
    return Response.json({ error: "로그인이 필요합니다" }, { status: 401 });
  }

  const body = await request.json().catch(() => ({}));
  const name = body.name || `VS Code - ${new Date().toLocaleDateString("ko-KR")}`;

  const rawKey = `hk-${crypto.randomBytes(24).toString("hex")}`;
  const keyHash = crypto.createHash("sha256").update(rawKey).digest("hex");
  const keyPrefix = rawKey.slice(0, 12) + "...";

  try {
    await prisma.apiKey.create({
      data: {
        userId: session.user.id,
        name,
        keyHash,
        keyPrefix,
        permissions: ["chat", "tools"],
        rateLimit: 120,
      },
    });

    return Response.json({
      key: rawKey,
      keyPrefix,
      name,
    });
  } catch (error: any) {
    return Response.json(
      { error: error.message || "API 키 생성 실패" },
      { status: 500 }
    );
  }
}
