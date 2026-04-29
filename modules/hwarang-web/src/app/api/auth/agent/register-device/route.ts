/**
 * Hwarang Grid 데스크탑 에이전트 — 기기 등록 + API 키 발급
 *
 * POST /api/auth/agent/register-device
 *
 * 인증: NextAuth 세션 (브라우저 쿠키)
 * Body: {
 *   deviceName?: string,
 *   deviceOs?: string,
 *   deviceArch?: string,
 *   deviceGpu?: string,
 *   deviceFingerprint?: string,
 *   reuseFingerprint?: boolean  // true 면 같은 fingerprint 의 기존 키 비활성화
 * }
 * Response: { key, deviceId, deviceName, keyPrefix, createdAt }
 *
 * 흐름:
 * 1. 세션 검증
 * 2. fingerprint 가 있고 reuseFingerprint=true 면 동일 user+fingerprint 의 기존 활성 키 비활성화
 * 3. rawKey = "hk-{48자 hex}" 생성 → SHA256 해시 저장
 * 4. ApiKey 레코드 생성 (deviceKind="agent_grid", permissions=["chat","agent"])
 * 5. rawKey 응답에 한 번만 노출
 */

import { NextRequest } from "next/server";
import { auth } from "@/lib/auth";
import { prisma } from "@/lib/db";
import crypto from "crypto";

export async function POST(request: NextRequest) {
  const session = await auth();

  if (!session?.user?.id) {
    return Response.json(
      { error: "로그인이 필요합니다" },
      { status: 401 }
    );
  }

  const body = await request.json().catch(() => ({}));

  const deviceName: string =
    (body.deviceName && String(body.deviceName).trim()) ||
    `Grid Agent - ${new Date().toLocaleDateString("ko-KR")}`;
  const deviceOs: string | null = body.deviceOs ? String(body.deviceOs) : null;
  const deviceArch: string | null = body.deviceArch
    ? String(body.deviceArch)
    : null;
  const deviceGpu: string | null = body.deviceGpu ? String(body.deviceGpu) : null;
  const deviceFingerprint: string | null = body.deviceFingerprint
    ? String(body.deviceFingerprint)
    : null;
  const reuseFingerprint: boolean = body.reuseFingerprint !== false;

  try {
    // 같은 fingerprint 의 기존 활성 키 비활성화 (재로그인 시나리오)
    if (deviceFingerprint && reuseFingerprint) {
      await prisma.apiKey.updateMany({
        where: {
          userId: session.user.id,
          deviceFingerprint,
          deviceKind: "agent_grid",
          isActive: true,
        },
        data: { isActive: false },
      });
    }

    // 신규 rawKey 생성
    const rawKey = `hk-${crypto.randomBytes(24).toString("hex")}`;
    const keyHash = crypto.createHash("sha256").update(rawKey).digest("hex");
    const keyPrefix = rawKey.slice(0, 12) + "...";

    const apiKey = await prisma.apiKey.create({
      data: {
        userId: session.user.id,
        name: deviceName,
        keyHash,
        keyPrefix,
        permissions: ["chat", "agent"],
        rateLimit: 240,
        deviceName,
        deviceOs,
        deviceArch,
        deviceGpu,
        deviceFingerprint,
        deviceKind: "agent_grid",
        lastSeenAt: new Date(),
      },
    });

    return Response.json({
      key: rawKey,
      deviceId: apiKey.id,
      deviceName: apiKey.deviceName,
      keyPrefix: apiKey.keyPrefix,
      createdAt: apiKey.createdAt,
    });
  } catch (error: any) {
    return Response.json(
      { error: error?.message || "기기 등록 실패" },
      { status: 500 }
    );
  }
}
