/**
 * Hwarang Grid 데스크탑 에이전트 — 하트비트
 *
 * POST /api/auth/agent/heartbeat
 *
 * 인증: Bearer token (ApiKey)
 * Body (선택): { gpu_usage, gpu_temp, status, version }
 * 동작: ApiKey.lastSeenAt = now()
 * Response: { ok: true, server_time }
 *
 * 데스크탑 에이전트가 1분마다 호출하여 "활성 기기" 표시 유지.
 */

import { NextRequest } from "next/server";
import { prisma } from "@/lib/db";
import crypto from "crypto";

export async function POST(request: NextRequest) {
  const authHeader = request.headers.get("authorization") || "";
  const bearer = authHeader.startsWith("Bearer ")
    ? authHeader.slice(7).trim()
    : null;

  if (!bearer) {
    return Response.json(
      { error: "Bearer token 이 필요합니다" },
      { status: 401 }
    );
  }

  const keyHash = crypto.createHash("sha256").update(bearer).digest("hex");
  const apiKey = await prisma.apiKey.findUnique({
    where: { keyHash },
    select: { id: true, isActive: true, expiresAt: true },
  });

  if (!apiKey || !apiKey.isActive) {
    return Response.json(
      { error: "유효하지 않은 키입니다" },
      { status: 401 }
    );
  }
  if (apiKey.expiresAt && apiKey.expiresAt < new Date()) {
    return Response.json(
      { error: "키가 만료되었습니다" },
      { status: 401 }
    );
  }

  // body 는 텔레메트리용 — 현재는 받기만 하고 폐기 (추후 GridTelemetry 모델로 확장)
  await request.json().catch(() => ({}));

  const now = new Date();
  await prisma.apiKey.update({
    where: { id: apiKey.id },
    data: { lastSeenAt: now, lastUsedAt: now },
  });

  return Response.json({
    ok: true,
    server_time: now.toISOString(),
  });
}
