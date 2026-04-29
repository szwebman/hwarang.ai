/**
 * Bearer token 보유자(데스크탑 에이전트/VS Code/CLI) 신원 확인
 *
 * GET /api/auth/whoami
 *
 * 인증: Bearer token (ApiKey)
 * Response: {
 *   user_id, email, name, kyc_verified, tier,
 *   device_id, device_name, device_kind, last_seen_at
 * }
 *
 * 흐름:
 * 1. Authorization: Bearer hk-... 추출
 * 2. SHA256 해시로 ApiKey 조회 (isActive=true)
 * 3. lastUsedAt + lastSeenAt 갱신
 * 4. user 조인하여 반환
 */

import { NextRequest } from "next/server";
import { prisma } from "@/lib/db";
import crypto from "crypto";

export async function GET(request: NextRequest) {
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
    include: {
      user: {
        include: { plan: true },
      },
    },
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

  // 활동 시각 갱신 (best-effort)
  const now = new Date();
  prisma.apiKey
    .update({
      where: { id: apiKey.id },
      data: { lastUsedAt: now, lastSeenAt: now },
    })
    .catch(() => {});

  // KYC 여부는 ContributorProfile 에 기록되지만, 여기서는 User.emailVerified 를
  // 1차 신원으로 사용 (간이) — 추후 ContributorProfile.kycVerified 조회로 확장.
  const kycVerified = !!apiKey.user.emailVerified;
  const tier = apiKey.user.plan?.name || "free";

  return Response.json({
    user_id: apiKey.user.id,
    email: apiKey.user.email,
    name: apiKey.user.name,
    kyc_verified: kycVerified,
    tier,
    device_id: apiKey.id,
    device_name: apiKey.deviceName,
    device_kind: apiKey.deviceKind,
    device_os: apiKey.deviceOs,
    device_gpu: apiKey.deviceGpu,
    last_seen_at: now.toISOString(),
    permissions: apiKey.permissions,
    rate_limit: apiKey.rateLimit,
  });
}
