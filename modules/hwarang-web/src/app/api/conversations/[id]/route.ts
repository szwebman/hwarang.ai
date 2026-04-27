/**
 * Single conversation: load messages + delete.
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
        select: { userId: true },
      });
      if (apiKey) return apiKey.userId;
    }
  }
  const session = await auth();
  return session?.user?.id || null;
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const userId = await resolveUserId(request);
  if (!userId) {
    return Response.json({ error: "로그인이 필요합니다" }, { status: 401 });
  }

  const conversation = await prisma.conversation.findFirst({
    where: { id, userId },
    include: {
      messages: {
        orderBy: { createdAt: "asc" },
        select: { id: true, role: true, content: true, createdAt: true },
      },
    },
  });

  if (!conversation) {
    return Response.json({ error: "대화를 찾을 수 없습니다" }, { status: 404 });
  }

  return Response.json({ conversation });
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const userId = await resolveUserId(request);
  if (!userId) {
    return Response.json({ error: "로그인이 필요합니다" }, { status: 401 });
  }

  const result = await prisma.conversation.deleteMany({
    where: { id, userId },
  });
  if (result.count === 0) {
    return Response.json({ error: "대화를 찾을 수 없습니다" }, { status: 404 });
  }
  return Response.json({ deleted: true });
}
