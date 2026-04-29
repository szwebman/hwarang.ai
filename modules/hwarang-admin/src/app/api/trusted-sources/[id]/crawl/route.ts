/**
 * Trusted Sources 즉시 크롤 트리거 프록시
 *
 *   POST /api/trusted-sources/{id}/crawl  → ${HWARANG_API_URL}/api/sources/{id}/crawl
 *
 * 응답: { crawled: number, ingested: number, errors: string[] }
 */

import { NextRequest } from "next/server";
import { verifyToken } from "@/lib/auth";

const HWARANG_API_URL = process.env.HWARANG_API_URL || "http://localhost:8000";
const INTERNAL_KEY = process.env.HWARANG_INTERNAL_KEY || "";

function requireAdmin(request: NextRequest) {
  const header = request.headers.get("authorization") || "";
  const token = header.startsWith("Bearer ") ? header.slice(7).trim() : "";
  if (!token) return { ok: false as const, status: 401, error: "로그인이 필요합니다" };
  const payload = verifyToken(token);
  if (!payload) return { ok: false as const, status: 401, error: "유효하지 않은 토큰" };
  if (payload.role !== "ADMIN" && payload.role !== "SUPER_ADMIN") {
    return { ok: false as const, status: 403, error: "관리자 권한이 필요합니다" };
  }
  return { ok: true as const, userId: payload.userId, role: payload.role };
}

type Ctx = { params: Promise<{ id: string }> };

export async function POST(request: NextRequest, ctx: Ctx) {
  const guard = requireAdmin(request);
  if (!guard.ok) return Response.json({ error: guard.error }, { status: guard.status });

  const { id } = await ctx.params;
  const body = await request.text().catch(() => "");
  const target = `${HWARANG_API_URL}/api/sources/${encodeURIComponent(id)}/crawl`;

  try {
    const resp = await fetch(target, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-user-id": guard.userId,
        "x-user-role": guard.role,
        "x-api-key": INTERNAL_KEY || `admin-${guard.userId}`,
      },
      body: body || undefined,
      // 크롤링은 시간이 걸릴 수 있음
      signal: AbortSignal.timeout(60_000),
    });
    const contentType = resp.headers.get("content-type") || "";
    const text = await resp.text();
    if (contentType.includes("application/json")) {
      try {
        return Response.json(JSON.parse(text), { status: resp.status });
      } catch {
        return new Response(text, { status: resp.status, headers: { "Content-Type": contentType } });
      }
    }
    return new Response(text, { status: resp.status, headers: { "Content-Type": contentType } });
  } catch (err: any) {
    return Response.json(
      { error: "크롤 트리거 실패", detail: err?.message || String(err) },
      { status: 502 }
    );
  }
}
