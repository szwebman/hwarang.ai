/**
 * API Keys CRUD
 * GET: 내 API 키 목록
 * POST: 새 키 생성
 * DELETE: 키 삭제
 */

import { NextRequest } from "next/server";
import { prisma } from "@/lib/db";
import crypto from "crypto";

// GET /api/api-keys
export async function GET(request: NextRequest) {
  const userId = request.headers.get("x-user-id") || "demo-user";

  try {
    const keys = await prisma.apiKey.findMany({
      where: { userId },
      orderBy: { createdAt: "desc" },
      select: {
        id: true, name: true, keyPrefix: true,
        isActive: true, lastUsedAt: true, createdAt: true,
        permissions: true, rateLimit: true,
      },
    });
    return Response.json(keys);
  } catch {
    return Response.json([]);
  }
}

// POST /api/api-keys
export async function POST(request: NextRequest) {
  const userId = request.headers.get("x-user-id") || "demo-user";
  const body = await request.json();

  // 키 생성
  const rawKey = `hk-${crypto.randomBytes(24).toString("hex")}`;
  const keyHash = crypto.createHash("sha256").update(rawKey).digest("hex");
  const keyPrefix = rawKey.slice(0, 12) + "...";

  try {
    const apiKey = await prisma.apiKey.create({
      data: {
        userId,
        name: body.name || "이름 없음",
        keyHash,
        keyPrefix,
        permissions: body.permissions || ["chat"],
        rateLimit: body.rateLimit || 60,
      },
    });

    // rawKey는 이 한 번만 반환 (DB에는 해시만 저장)
    return Response.json({
      ...apiKey,
      key: rawKey,  // ⚠️ 이것만 1회 노출
    }, { status: 201 });
  } catch (error: any) {
    return Response.json({ error: error.message }, { status: 500 });
  }
}

// DELETE /api/api-keys?id=xxx
export async function DELETE(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const id = searchParams.get("id");

  if (!id) {
    return Response.json({ error: "id required" }, { status: 400 });
  }

  try {
    await prisma.apiKey.delete({ where: { id } });
    return Response.json({ deleted: true });
  } catch (error: any) {
    return Response.json({ error: error.message }, { status: 500 });
  }
}
