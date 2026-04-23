/**
 * HLKM 관리자 API 프록시 (catch-all)
 *
 * Next.js → Hwarang Backend API 프록시
 * - 세션 확인 (ADMIN role only)
 * - x-user-id 헤더 전달
 * - GET / POST / PUT / DELETE / PATCH 전부 지원
 *
 * 경로 매핑:
 *   /api/admin/hlkm/stats/overview  →  ${HWARANG_API_URL}/api/knowledge/stats/overview
 *   /api/admin/hlkm/facts/pending   →  ${HWARANG_API_URL}/api/knowledge/facts/pending
 *   /api/admin/hlkm/admin/verify/run → ${HWARANG_API_URL}/api/knowledge/admin/verify/run
 */

import { NextRequest } from "next/server";
import { auth } from "@/lib/auth";

const HWARANG_API_URL = process.env.HWARANG_API_URL || "http://localhost:8000";

async function requireAdmin() {
  const session = await auth();
  const role = (session?.user as any)?.role;
  const userId = session?.user?.id;
  if (!session || !userId) {
    return { ok: false, status: 401, error: "로그인이 필요합니다" };
  }
  if (role !== "ADMIN" && role !== "SUPER_ADMIN") {
    return { ok: false, status: 403, error: "관리자 권한이 필요합니다" };
  }
  return { ok: true, userId, email: session.user.email || "", role };
}

function buildUrl(pathSegments: string[], search: string): string {
  const path = pathSegments.join("/");
  return `${HWARANG_API_URL}/api/knowledge/${path}${search || ""}`;
}

async function proxy(
  request: NextRequest,
  pathSegments: string[],
  method: string
): Promise<Response> {
  const guard = await requireAdmin();
  if (!guard.ok) {
    return Response.json({ error: guard.error }, { status: guard.status });
  }

  const url = new URL(request.url);
  const target = buildUrl(pathSegments, url.search);

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "x-user-id": guard.userId!,
    "x-user-email": guard.email!,
    "x-user-role": guard.role!,
  };

  // 원본 Authorization 전달 (있으면)
  const origAuth = request.headers.get("authorization");
  if (origAuth) headers.Authorization = origAuth;

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
