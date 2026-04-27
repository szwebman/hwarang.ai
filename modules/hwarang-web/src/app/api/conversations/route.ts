/**
 * Conversations API routes.
 * CRUD operations for chat conversations (Prisma + per-user filter).
 *
 * 인증:
 *  - NextAuth 세션 쿠키 (웹)
 *  - Authorization: Bearer hk-xxx (API 키)
 */

import { NextRequest } from "next/server";
import { auth } from "@/lib/auth";
import { prisma } from "@/lib/db";
import crypto from "crypto";

async function resolveUserId(request: NextRequest): Promise<string | null> {
  const authHeader = request.headers.get("authorization");
  if (authHeader?.startsWith("Bearer ")) {
    const rawKey = authHeader.slice(7).trim();
    if (rawKey) {
      const keyHash = crypto.createHash("sha256").update(rawKey).digest("hex");
      const apiKey = await prisma.apiKey.findFirst({
        where: { keyHash, isActive: true },
        select: { userId: true, id: true },
      });
      if (apiKey) {
        prisma.apiKey
          .update({ where: { id: apiKey.id }, data: { lastUsedAt: new Date() } })
          .catch(() => {});
        return apiKey.userId;
      }
    }
  }

  const session = await auth();
  return session?.user?.id || null;
}

export async function GET(request: NextRequest) {
  const userId = await resolveUserId(request);
  if (!userId) {
    return Response.json({ error: "로그인이 필요합니다" }, { status: 401 });
  }

  try {
    const list = await prisma.conversation.findMany({
      where: { userId },
      orderBy: { updatedAt: "desc" },
      select: {
        id: true,
        title: true,
        model: true,
        domain: true,
        createdAt: true,
        updatedAt: true,
      },
    });
    return Response.json({ conversations: list });
  } catch (e: any) {
    console.error("GET /api/conversations error:", e?.message);
    return Response.json({ error: "서버 오류" }, { status: 500 });
  }
}

export async function POST(request: NextRequest) {
  const userId = await resolveUserId(request);
  if (!userId) {
    return Response.json({ error: "로그인이 필요합니다" }, { status: 401 });
  }

  try {
    const body = await request.json().catch(() => ({}));
    const conversation = await prisma.conversation.create({
      data: {
        userId,
        title: body.title || "새 대화",
        model: body.model || "hwarang-code-7b",
        domain: body.domain ?? null,
      },
      select: {
        id: true,
        title: true,
        model: true,
        domain: true,
        createdAt: true,
        updatedAt: true,
      },
    });
    return Response.json(conversation, { status: 201 });
  } catch (e: any) {
    console.error("POST /api/conversations error:", e?.message);
    return Response.json({ error: "서버 오류" }, { status: 500 });
  }
}

export async function DELETE(request: NextRequest) {
  const userId = await resolveUserId(request);
  if (!userId) {
    return Response.json({ error: "로그인이 필요합니다" }, { status: 401 });
  }

  const { searchParams } = new URL(request.url);
  const id = searchParams.get("id");
  if (!id) {
    return Response.json({ error: "id 파라미터가 필요합니다" }, { status: 400 });
  }

  try {
    // 본인 대화만 삭제 (다른 사람 대화 삭제 방지)
    const result = await prisma.conversation.deleteMany({
      where: { id, userId },
    });
    if (result.count === 0) {
      return Response.json({ error: "대화를 찾을 수 없습니다" }, { status: 404 });
    }
    return Response.json({ deleted: true });
  } catch (e: any) {
    console.error("DELETE /api/conversations error:", e?.message);
    return Response.json({ error: "서버 오류" }, { status: 500 });
  }
}
