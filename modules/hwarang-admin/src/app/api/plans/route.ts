/**
 * 플랜 관리 API - 실제 DB
 */

import { NextRequest } from "next/server";
import { prisma } from "@/lib/db";

export async function GET() {
  try {
    const plans = await prisma.plan.findMany({
      include: { _count: { select: { users: true } } },
      orderBy: { priceMonthly: "asc" },
    });
    return Response.json(plans);
  } catch (e) {
    console.error("플랜 조회 실패:", e);
    return Response.json([]);
  }
}

export async function PUT(request: NextRequest) {
  try {
    const body = await request.json();
    const { id, ...data } = body;
    const plan = await prisma.plan.update({ where: { id }, data });
    return Response.json(plan);
  } catch (e: any) {
    return Response.json({ error: e.message }, { status: 500 });
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const plan = await prisma.plan.create({ data: body });
    return Response.json(plan, { status: 201 });
  } catch (e: any) {
    return Response.json({ error: e.message }, { status: 500 });
  }
}
