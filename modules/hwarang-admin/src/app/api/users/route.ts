/**
 * Admin Users API
 * GET /api/admin/users - 유저 목록 (검색, 필터)
 * PUT /api/admin/users - 유저 수정 (플랜 변경, 차단 등)
 */

import { NextRequest } from "next/server";
import { prisma } from "@/lib/db";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const search = searchParams.get("search") || "";
  const plan = searchParams.get("plan") || "";
  const page = parseInt(searchParams.get("page") || "1");
  const limit = parseInt(searchParams.get("limit") || "50");

  try {
    const where: any = {};

    if (search) {
      where.OR = [
        { name: { contains: search, mode: "insensitive" } },
        { email: { contains: search, mode: "insensitive" } },
      ];
    }
    if (plan && plan !== "all") {
      where.plan = { name: plan };
    }

    const [users, total] = await Promise.all([
      prisma.user.findMany({
        where,
        include: {
          plan: { select: { name: true, displayName: true } },
          tokenBalance: { select: { balance: true, dailyUsed: true, totalUsed: true } },
          _count: { select: { apiKeys: true, usageRecords: true } },
        },
        orderBy: { createdAt: "desc" },
        skip: (page - 1) * limit,
        take: limit,
      }),
      prisma.user.count({ where }),
    ]);

    return Response.json({
      users,
      pagination: { page, limit, total, totalPages: Math.ceil(total / limit) },
    });
  } catch {
    return Response.json({ users: [], pagination: { page: 1, limit: 50, total: 0, totalPages: 0 } });
  }
}

export async function PUT(request: NextRequest) {
  try {
    const body = await request.json();
    const { id, ...data } = body;

    const user = await prisma.user.update({
      where: { id },
      data,
      include: { plan: true },
    });

    return Response.json(user);
  } catch (error: any) {
    return Response.json({ error: error.message }, { status: 500 });
  }
}
