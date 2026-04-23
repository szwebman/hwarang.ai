/**
 * HLKM 관리자 API 프록시 (catch-all)
 *
 * hwarang-admin Next.js → Hwarang Backend(FastAPI) 프록시
 * - admin_token(Bearer) 검증 (ADMIN / SUPER_ADMIN)
 * - x-user-id / x-user-role 헤더 전달
 * - GET / POST / PUT / PATCH / DELETE 전부 지원
 *
 * 경로 매핑:
 *   /api/hlkm/stats/overview       → ${HWARANG_API_URL}/api/knowledge/stats/overview
 *   /api/hlkm/facts/pending        → ${HWARANG_API_URL}/api/knowledge/facts/pending
 *   /api/hlkm/admin/verify/run     → ${HWARANG_API_URL}/api/knowledge/admin/verify/run
 */

import { NextRequest } from "next/server";
import { verifyToken } from "@/lib/auth";

const HWARANG_API_URL = process.env.HWARANG_API_URL || "http://localhost:8000";

function requireAdmin(request: NextRequest) {
  const header = request.headers.get("authorization") || "";
  const token = header.startsWith("Bearer ") ? header.slice(7).trim() : "";
  if (!token) {
    return { ok: false as const, status: 401, error: "로그인이 필요합니다" };
  }
  const payload = verifyToken(token);
  if (!payload) {
    return { ok: false as const, status: 401, error: "유효하지 않은 토큰" };
  }
  if (payload.role !== "ADMIN" && payload.role !== "SUPER_ADMIN") {
    return { ok: false as const, status: 403, error: "관리자 권한이 필요합니다" };
  }
  return { ok: true as const, userId: payload.userId, role: payload.role };
}

function buildUrl(pathSegments: string[], search: string): string {
  const path = pathSegments.join("/");
  return `${HWARANG_API_URL}/api/knowledge/${path}${search || ""}`;
}

async function proxy(request: NextRequest, pathSegments: string[], method: string): Promise<Response> {
  const guard = requireAdmin(request);
  if (!guard.ok) {
    return Response.json({ error: guard.error }, { status: guard.status });
  }

  const url = new URL(request.url);
  const target = buildUrl(pathSegments, url.search);

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "x-user-id": guard.userId,
    "x-user-role": guard.role,
    // 백엔드 admin 엔드포인트용 X-API-Key 호환 (require_admin이 admin- prefix 체크)
    "x-api-key": `admin-${guard.userId}`,
  };

  const init: RequestInit = { method, headers, cache: "no-store" };

  if (method !== "GET" && method !== "HEAD") {
    try {
      const body = await request.text();
      if (body) init.body = body;
    } catch {}
  }

  try {
    const resp = await fetch(target, init);
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
      { error: "백엔드 연결 실패", detail: err?.message || String(err) },
      { status: 502 }
    );
  }
}

type RouteCtx = { params: Promise<{ path: string[] }> };

export async function GET(req: NextRequest, ctx: RouteCtx) {
  const { path } = await ctx.params;
  return proxy(req, path, "GET");
}

export async function POST(req: NextRequest, ctx: RouteCtx) {
  const { path } = await ctx.params;
  return proxy(req, path, "POST");
}

export async function PUT(req: NextRequest, ctx: RouteCtx) {
  const { path } = await ctx.params;
  return proxy(req, path, "PUT");
}

export async function PATCH(req: NextRequest, ctx: RouteCtx) {
  const { path } = await ctx.params;
  return proxy(req, path, "PATCH");
}

export async function DELETE(req: NextRequest, ctx: RouteCtx) {
  const { path } = await ctx.params;
  return proxy(req, path, "DELETE");
}
