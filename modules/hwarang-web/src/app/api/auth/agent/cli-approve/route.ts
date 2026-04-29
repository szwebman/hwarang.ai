/**
 * CLI 다중 기기 로그인 — 사용자 브라우저 승인 엔드포인트
 *
 * POST /api/auth/agent/cli-approve
 *
 * 인증: NextAuth 세션 (브라우저 쿠키) 필수
 *
 * Body: { nonce: string, deviceName?: string }
 *
 * 흐름:
 *   1) 세션 검증
 *   2) CliLoginRequest 조회 + 만료/이미 승인 검사
 *   3) ApiKey 신규 생성 (rawKey + sha256 keyHash)
 *   4) CliLoginRequest 업데이트:
 *        status="approved", apiKeyId, rawKey(1회), approvedByUserId
 *      → 트랜잭션으로 ApiKey 생성과 함께 처리
 *   5) 응답: { ok, device_id, device_name }
 *
 * 보안:
 *   - 동일 nonce 가 이미 승인 상태면 409 (재승인 방지)
 *   - rawKey 는 cli-poll 응답에서만 노출. 본 엔드포인트 응답에는 포함하지 않음.
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
  const userId: string = session.user.id;

  const body = await request.json().catch(() => ({}));
  const nonce: string | undefined = body.nonce ? String(body.nonce) : undefined;
  const customDeviceName: string | null = body.deviceName
    ? String(body.deviceName).trim().slice(0, 200)
    : null;

  if (!nonce) {
    return Response.json(
      { error: "nonce 파라미터가 필요합니다" },
      { status: 400 }
    );
  }

  const cliReq = await prisma.cliLoginRequest.findUnique({
    where: { nonce },
  });

  if (!cliReq) {
    return Response.json(
      { error: "유효하지 않은 nonce" },
      { status: 404 }
    );
  }

  const now = new Date();
  if (cliReq.expiresAt < now) {
    // lazy cleanup
    if (cliReq.status === "pending") {
      await prisma.cliLoginRequest
        .update({
          where: { id: cliReq.id },
          data: { status: "expired" },
        })
        .catch(() => {});
    }
    return Response.json(
      { error: "만료된 요청입니다. CLI 에서 다시 시도하세요." },
      { status: 410 }
    );
  }

  if (cliReq.status === "approved") {
    return Response.json(
      { error: "이미 승인된 요청입니다" },
      { status: 409 }
    );
  }

  if (cliReq.status === "denied" || cliReq.status === "expired") {
    return Response.json(
      { error: `요청 상태: ${cliReq.status}` },
      { status: 410 }
    );
  }

  // ApiKey 생성 + CliLoginRequest 업데이트 (트랜잭션)
  const deviceName: string =
    customDeviceName ||
    cliReq.deviceName ||
    cliReq.deviceHostname ||
    "CLI 기기";

  const rawKey = `hk-${crypto.randomBytes(24).toString("hex")}`;
  const keyHash = crypto.createHash("sha256").update(rawKey).digest("hex");
  const keyPrefix = rawKey.slice(0, 12) + "...";

  try {
    const result = await prisma.$transaction(async (tx) => {
      // 같은 fingerprint 의 기존 활성 키 비활성화 (재로그인 시나리오)
      if (cliReq.deviceFingerprint) {
        await tx.apiKey.updateMany({
          where: {
            userId: userId,
            deviceFingerprint: cliReq.deviceFingerprint,
            deviceKind: "agent_grid",
            isActive: true,
          },
          data: { isActive: false },
        });
      }

      const apiKey = await tx.apiKey.create({
        data: {
          userId: userId,
          name: deviceName,
          keyHash,
          keyPrefix,
          permissions: ["chat", "agent"],
          rateLimit: 240,
          deviceName,
          deviceOs: cliReq.deviceOs,
          deviceArch: cliReq.deviceArch,
          deviceGpu: cliReq.deviceGpu,
          deviceFingerprint: cliReq.deviceFingerprint,
          deviceKind: "agent_grid",
          lastSeenAt: new Date(),
        },
      });

      // 동시 승인 방지: status="pending" 인 행만 업데이트
      const updated = await tx.cliLoginRequest.updateMany({
        where: { id: cliReq.id, status: "pending" },
        data: {
          status: "approved",
          apiKeyId: apiKey.id,
          rawKey,
          approvedByUserId: userId,
        },
      });

      if (updated.count === 0) {
        throw new Error("RACE_ALREADY_PROCESSED");
      }

      return apiKey;
    });

    return Response.json({
      ok: true,
      device_id: result.id,
      device_name: result.deviceName,
    });
  } catch (error: any) {
    if (error?.message === "RACE_ALREADY_PROCESSED") {
      return Response.json(
        { error: "이미 처리된 요청입니다" },
        { status: 409 }
      );
    }
    return Response.json(
      { error: error?.message || "CLI 승인 실패" },
      { status: 500 }
    );
  }
}
