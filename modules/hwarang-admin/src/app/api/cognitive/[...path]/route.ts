/**
 * Cognitive Layer 관리자 API 프록시 (catch-all).
 *
 * hwarang-admin Next.js → Hwarang FastAPI 백엔드 프록시.
 *  • admin_token (Bearer) 검증 (ADMIN / SUPER_ADMIN)
 *  • 백엔드 보호 엔드포인트(`cycle`/`disable`/`enable`/`debate`/`consult-agents`)
 *    호출 시 HWARANG_INTERNAL_KEY 를 Bearer 로 부착
 *  • GET / POST 모두 지원
 *
 * 경로 매핑:
 *   /api/cognitive/health             → ${HWARANG_API_URL}/api/cognitive/health
 *   /api/cognitive/memories?...       → ${HWARANG_API_URL}/api/cognitive/memories?...
 *   /api/cognitive/cycle (POST)       → ${HWARANG_API_URL}/api/cognitive/cycle
 *   /api/cognitive/disable (POST)     → ${HWARANG_API_URL}/api/cognitive/disable
 *   /api/cognitive/enable (POST)      → ${HWARANG_API_URL}/api/cognitive/enable
 *   /api/cognitive/debate (POST)      → ${HWARANG_API_URL}/api/cognitive/debate
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

function backendHeaders(userId: string, role: string): Record<string, string> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "x-user-id": userId,
    "x-user-role": role,
  };
  if (INTERNAL_KEY) {
    headers["Authorization"] = `Bearer ${INTERNAL_KEY}`;
    headers["x-api-key"] = INTERNAL_KEY;
  }
  return headers;
}

async function proxy(
  request: NextRequest,
  pathSegments: string[],
  method: string,
): Promise<Response> {
  const guard = requireAdmin(request);
  if (!guard.ok) return Response.json({ error: guard.error }, { status: guard.status });

  const search = new URL(request.url).search;
  const subpath = pathSegments.join("/");
  const target = `${HWARANG_API_URL}/api/cognitive/${subpath}${search || ""}`;

  const init: RequestInit = {
    method,
    headers: backendHeaders(guard.userId, guard.role),
    cache: "no-store",
  };

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
      { status: 502 },
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
