/**
 * 유저 상세 API
 * GET  /api/users/[id] - 상세 조회
 * PUT  /api/users/[id] - 수정 (isActive, role 등)
 */

import { NextRequest } from "next/server";
import { prisma } from "@/lib/db";
import { verifyToken } from "@/lib/auth";

function authenticate(request: NextRequest) {
  const authHeader = request.headers.get("authorization");
  const token = authHeader?.replace("Bearer ", "") || "";
  return verifyToken(token);
}

export async function GET(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const auth = authenticate(request);
  if (!auth || (auth.role !== "ADMIN" && auth.role !== "SUPER_ADMIN")) {
    return Response.json({ error: "권한 없음" }, { status: 403 });
  }

  const { id } = await params;

  try {
    const user = await prisma.user.findUnique({
      where: { id },
      include: {
        plan: { select: { id: true, name: true, displayName: true } },
        tokenBalance: {
          select: { balance: true, totalUsed: true, totalCharged: true, dailyUsed: true, dailyLimit: true },
        },
        apiKeys: {
          select: { id: true, name: true, keyPrefix: true, isActive: true, lastUsedAt: true, createdAt: true },
          orderBy: { createdAt: "desc" },
        },
        _count: { select: { usageRecords: true, conversations: true, payments: true } },
      },
    });

    if (!user) {
      return Response.json({ error: "유저를 찾을 수 없습니다" }, { status: 404 });
    }

    return Response.json(user);
  } catch (e: any) {
    return Response.json({ error: e.message }, { status: 500 });
  }
}

export async function PUT(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const auth = authenticate(request);
  if (!auth || (auth.role !== "ADMIN" && auth.role !== "SUPER_ADMIN")) {
    return Response.json({ error: "권한 없음" }, { status: 403 });
  }

  const { id } = await params;

  try {
    const body = await request.json();
    const data: any = {};

    if (body.isActive !== undefined) data.isActive = body.isActive;
    if (body.role) data.role = body.role;
    if (body.planId !== undefined) data.planId = body.planId || null;

    const user = await prisma.user.update({
      where: { id },
      data,
      include: { plan: true },
    });

    return Response.json(user);
  } catch (e: any) {
    return Response.json({ error: e.message }, { status: 500 });
  }
}
