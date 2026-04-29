/**
 * CLI 다중 기기 로그인 — 폴링 엔드포인트
 *
 * GET /api/auth/agent/cli-poll?nonce=XXX
 *
 * 인증: 불필요 (nonce 가 인증 매개체)
 *
 * 응답:
 *   - 200 { status: "pending" }                          → 아직 사용자 승인 전
 *   - 200 { status: "approved", api_key, device_id, ... }→ 승인 완료 (rawKey 1회 노출)
 *   - 404 { status: "not_found" }                        → nonce 없음
 *   - 410 { status: "expired" }                          → 10분 만료
 *   - 410 { status: "consumed" }                         → 이미 한번 polled 됨 (rawKey 소진)
 *   - 410 { status: "denied" }                           → 사용자 거부
 *
 * 보안:
 *   - rawKey 는 단 1회만 노출. 응답 직후 DB 의 rawKey 를 null 로 덮어씀.
 *   - 만료 시 lazy cleanup (status="expired" 업데이트).
 */

import { NextRequest } from "next/server";
import { prisma } from "@/lib/db";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const nonce = searchParams.get("nonce");

  if (!nonce) {
    return Response.json(
      { status: "invalid", error: "nonce 파라미터가 필요합니다" },
      { status: 400 }
    );
  }

  const req = await prisma.cliLoginRequest.findUnique({
    where: { nonce },
  });

  if (!req) {
    return Response.json({ status: "not_found" }, { status: 404 });
  }

  // 만료 검사 (lazy cleanup)
  const now = new Date();
  if (req.status === "pending" && req.expiresAt < now) {
    await prisma.cliLoginRequest
      .update({
        where: { id: req.id },
        data: { status: "expired" },
      })
      .catch(() => {});
    return Response.json({ status: "expired" }, { status: 410 });
  }

  if (req.status === "expired") {
    return Response.json({ status: "expired" }, { status: 410 });
  }

  if (req.status === "denied") {
    return Response.json({ status: "denied" }, { status: 410 });
  }

  if (req.status === "pending") {
    return Response.json({ status: "pending" });
  }

  if (req.status === "approved") {
    // rawKey 가 이미 소진되었는지 확인
    if (!req.rawKey) {
      return Response.json({ status: "consumed" }, { status: 410 });
    }

    // 같은 트랜잭션 의도: rawKey 를 null 로 덮어쓰며 1회 전달
    // (race condition 방지를 위해 rawKey 가 아직 있는 행만 업데이트)
    const consumed = await prisma.cliLoginRequest.updateMany({
      where: { id: req.id, rawKey: { not: null } },
      data: { rawKey: null },
    });

    if (consumed.count === 0) {
      // 동시 폴링이 먼저 가져갔다면 consumed 처리
      return Response.json({ status: "consumed" }, { status: 410 });
    }

    // 사용자 / API 키 메타 조회
    const apiKey = req.apiKeyId
      ? await prisma.apiKey.findUnique({
          where: { id: req.apiKeyId },
        })
      : null;

    const user = req.approvedByUserId
      ? await prisma.user.findUnique({
          where: { id: req.approvedByUserId },
          select: { id: true, email: true },
        })
      : null;

    // KYC / tier 는 ContributorProfile 에서 (없으면 기본값)
    const contributor = req.approvedByUserId
      ? await prisma.contributorProfile
          .findUnique({
            where: { userId: req.approvedByUserId },
            select: { kycVerified: true, tier: true },
          })
          .catch(() => null)
      : null;

    return Response.json({
      status: "approved",
      api_key: req.rawKey,
      device_id: apiKey?.id ?? null,
      device_name: apiKey?.deviceName ?? null,
      email: user?.email ?? null,
      kyc_verified: contributor?.kycVerified ?? false,
      tier: contributor?.tier ?? "BRONZE",
      user_id: user?.id ?? null,
    });
  }

  // 알 수 없는 상태
  return Response.json({ status: req.status });
}
