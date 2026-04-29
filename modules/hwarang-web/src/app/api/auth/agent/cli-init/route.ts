/**
 * CLI 다중 기기 로그인 — Device Authorization Flow (RFC 8628 패턴)
 *
 * POST /api/auth/agent/cli-init
 *
 * 인증: 불필요 (nonce 가 인증 매개체)
 *
 * Body: {
 *   deviceName?: string,
 *   deviceOs?: string,
 *   deviceArch?: string,
 *   deviceGpu?: string,
 *   deviceHostname?: string,
 *   deviceFingerprint?: string,
 * }
 *
 * Response: {
 *   nonce: string,
 *   login_url: string,    // 다른 기기 브라우저로 방문할 URL
 *   poll_url: string,     // CLI 가 폴링할 URL
 *   expires_in: 600,      // 초 단위
 *   interval: 3,          // 폴링 권장 간격 (초)
 * }
 *
 * 흐름:
 *   1) nonce 생성 (base64url 32 bytes)
 *   2) 같은 fingerprint 의 pending 요청이 있으면 expired 로 정리 (lazy cleanup)
 *   3) CliLoginRequest 생성 (expiresAt = now + 10분)
 *   4) login_url + poll_url 응답
 *
 * Rate limit: 같은 IP 가 1분에 5회 초과 시 429 (in-memory)
 */

import { NextRequest } from "next/server";
import { prisma } from "@/lib/db";
import crypto from "crypto";

// 간단한 in-memory rate limit (단일 인스턴스 가정)
// IP -> [timestamp, ...] (최근 60초 내)
const rateLimitMap = new Map<string, number[]>();
const RATE_LIMIT_WINDOW_MS = 60_000;
const RATE_LIMIT_MAX = 5;

function isRateLimited(ip: string): boolean {
  const now = Date.now();
  const windowStart = now - RATE_LIMIT_WINDOW_MS;
  const recent = (rateLimitMap.get(ip) || []).filter((t) => t > windowStart);
  if (recent.length >= RATE_LIMIT_MAX) {
    rateLimitMap.set(ip, recent);
    return true;
  }
  recent.push(now);
  rateLimitMap.set(ip, recent);
  return false;
}

function getClientIp(request: NextRequest): string {
  const xff = request.headers.get("x-forwarded-for");
  if (xff) return xff.split(",")[0].trim();
  const xri = request.headers.get("x-real-ip");
  if (xri) return xri.trim();
  return "unknown";
}

export async function POST(request: NextRequest) {
  // Rate limit
  const ip = getClientIp(request);
  if (isRateLimited(ip)) {
    return Response.json(
      { error: "요청이 너무 많습니다. 잠시 후 다시 시도하세요." },
      { status: 429 }
    );
  }

  const body = await request.json().catch(() => ({}));

  const deviceName: string | null = body.deviceName
    ? String(body.deviceName).slice(0, 200)
    : null;
  const deviceOs: string | null = body.deviceOs
    ? String(body.deviceOs).slice(0, 100)
    : null;
  const deviceArch: string | null = body.deviceArch
    ? String(body.deviceArch).slice(0, 50)
    : null;
  const deviceGpu: string | null = body.deviceGpu
    ? String(body.deviceGpu).slice(0, 200)
    : null;
  const deviceHostname: string | null = body.deviceHostname
    ? String(body.deviceHostname).slice(0, 200)
    : null;
  const deviceFingerprint: string | null = body.deviceFingerprint
    ? String(body.deviceFingerprint).slice(0, 200)
    : null;

  try {
    // 같은 fingerprint 의 pending 요청은 expired 로 정리 (lazy cleanup)
    if (deviceFingerprint) {
      await prisma.cliLoginRequest.updateMany({
        where: {
          deviceFingerprint,
          status: "pending",
        },
        data: { status: "expired" },
      });
    }

    // nonce 생성: 32 bytes base64url
    const nonce = crypto.randomBytes(32).toString("base64url");
    const now = new Date();
    const expiresAt = new Date(now.getTime() + 10 * 60 * 1000);

    await prisma.cliLoginRequest.create({
      data: {
        nonce,
        deviceName,
        deviceOs,
        deviceArch,
        deviceGpu,
        deviceHostname,
        deviceFingerprint,
        status: "pending",
        expiresAt,
      },
    });

    // 응답 URL 구성
    const baseUrl =
      process.env.NEXT_PUBLIC_APP_URL?.replace(/\/$/, "") ||
      "https://hwarang.ai";

    const loginParams = new URLSearchParams({
      nonce,
      cli: "1",
    });
    if (deviceOs) loginParams.set("os", deviceOs);
    if (deviceArch) loginParams.set("arch", deviceArch);
    if (deviceGpu) loginParams.set("gpu", deviceGpu);
    if (deviceHostname) loginParams.set("hostname", deviceHostname);
    if (deviceFingerprint) loginParams.set("fingerprint", deviceFingerprint);

    const login_url = `${baseUrl}/agent-login?${loginParams.toString()}`;
    const poll_url = `${baseUrl}/api/auth/agent/cli-poll?nonce=${encodeURIComponent(
      nonce
    )}`;

    return Response.json({
      nonce,
      login_url,
      poll_url,
      expires_in: 600,
      interval: 3,
    });
  } catch (error: any) {
    return Response.json(
      { error: error?.message || "CLI 로그인 초기화 실패" },
      { status: 500 }
    );
  }
}
