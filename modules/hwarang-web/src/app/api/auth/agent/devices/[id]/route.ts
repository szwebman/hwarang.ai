/**
 * Hwarang Grid 데스크탑 에이전트 — 기기 폐기 (soft delete)
 *
 * DELETE /api/auth/agent/devices/[id]
 *
 * 인증: NextAuth 세션 (자기 소유 기기만 폐기 가능)
 * 동작: ApiKey.isActive = false
 * Response: { ok: true, deviceId }
 */

import { NextRequest } from "next/server";
import { auth } from "@/lib/auth";
import { prisma } from "@/lib/db";

export async function DELETE(
  request: NextRequest,
  context: { params: Promise<{ id: string }> }
) {
  const session = await auth();
  if (!session?.user?.id) {
    return Response.json(
      { error: "로그인이 필요합니다" },
      { status: 401 }
    );
  }

  const { id } = await context.params;
  if (!id) {
    return Response.json({ error: "deviceId 누락" }, { status: 400 });
  }

  // 자기 소유 검증
  const existing = await prisma.apiKey.findUnique({
    where: { id },
    select: { id: true, userId: true, deviceKind: true },
  });

  if (!existing || existing.userId !== session.user.id) {
    return Response.json(
      { error: "기기를 찾을 수 없습니다" },
      { status: 404 }
    );
  }

  await prisma.apiKey.update({
    where: { id },
    data: { isActive: false },
  });

  return Response.json({ ok: true, deviceId: id });
}
