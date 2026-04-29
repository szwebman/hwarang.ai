/**
 * Hwarang Grid 데스크탑 에이전트 — 등록 기기 목록
 *
 * GET /api/auth/agent/devices
 *
 * 인증: NextAuth 세션 OR Bearer token (ApiKey)
 * Response: [{ id, deviceName, deviceOs, deviceArch, deviceGpu,
 *               keyPrefix, lastSeenAt, isActive, createdAt, isCurrent }]
 *
 * - Bearer 인증으로 호출되면 해당 키의 기기는 isCurrent=true 로 표시
 * - agent_grid 만 노출 (vscode 등은 별도 페이지)
 */

import { NextRequest } from "next/server";
import { auth } from "@/lib/auth";
import { prisma } from "@/lib/db";
import crypto from "crypto";

async function resolveUserId(request: NextRequest): Promise<{
  userId: string | null;
  currentApiKeyId: string | null;
}> {
  // 1. Bearer token 우선 확인
  const authHeader = request.headers.get("authorization") || "";
  const bearer = authHeader.startsWith("Bearer ")
    ? authHeader.slice(7).trim()
    : null;

  if (bearer) {
    const keyHash = crypto.createHash("sha256").update(bearer).digest("hex");
    const apiKey = await prisma.apiKey.findUnique({
      where: { keyHash },
      select: { id: true, userId: true, isActive: true },
    });
    if (apiKey?.isActive) {
      return { userId: apiKey.userId, currentApiKeyId: apiKey.id };
    }
  }

  // 2. NextAuth 세션 fallback
  const session = await auth();
  if (session?.user?.id) {
    return { userId: session.user.id, currentApiKeyId: null };
  }

  return { userId: null, currentApiKeyId: null };
}

export async function GET(request: NextRequest) {
  const { userId, currentApiKeyId } = await resolveUserId(request);

  if (!userId) {
    return Response.json(
      { error: "인증이 필요합니다" },
      { status: 401 }
    );
  }

  const devices = await prisma.apiKey.findMany({
    where: {
      userId,
      deviceKind: "agent_grid",
    },
    orderBy: [{ isActive: "desc" }, { lastSeenAt: "desc" }, { createdAt: "desc" }],
    select: {
      id: true,
      deviceName: true,
      deviceOs: true,
      deviceArch: true,
      deviceGpu: true,
      deviceFingerprint: true,
      keyPrefix: true,
      lastSeenAt: true,
      isActive: true,
      createdAt: true,
    },
  });

  const result = devices.map((d) => ({
    ...d,
    isCurrent: currentApiKeyId === d.id,
  }));

  return Response.json({ devices: result });
}
