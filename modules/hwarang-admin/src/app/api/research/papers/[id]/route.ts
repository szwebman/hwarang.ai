/**
 * Research Paper 단건 + applications 프록시.
 *
 *   GET /api/research/papers/{id}
 *     → ${HWARANG_API_URL}/api/research/papers/{id}
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
  return {
    "Content-Type": "application/json",
    "x-user-id": userId,
    "x-user-role": role,
    "x-api-key": INTERNAL_KEY || `admin-${userId}`,
    Authorization: INTERNAL_KEY ? `Bearer ${INTERNAL_KEY}` : "",
  };
}

type Ctx = { params: Promise<{ id: string }> };

export async function GET(request: NextRequest, ctx: Ctx) {
  const guard = requireAdmin(request);
  if (!guard.ok) return Response.json({ error: guard.error }, { status: guard.status });
  const { id } = await ctx.params;
  try {
    const resp = await fetch(
      `${HWARANG_API_URL}/api/research/papers/${encodeURIComponent(id)}`,
      {
        method: "GET",
        headers: backendHeaders(guard.userId, guard.role),
        cache: "no-store",
      }
    );
    const text = await resp.text();
    try {
      return Response.json(JSON.parse(text), { status: resp.status });
    } catch {
      return new Response(text, { status: resp.status });
    }
  } catch (err: any) {
    return Response.json(
      { error: "백엔드 연결 실패", detail: err?.message || String(err) },
      { status: 502 }
    );
  }
}
