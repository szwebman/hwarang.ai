/**
 * 플랜 관리 API
 * GET    - 플랜 목록
 * POST   - 새 플랜
 * PUT    - 수정
 * DELETE - 삭제 (사용 중인 유저 있으면 거부)
 */

import { NextRequest } from "next/server";
import { prisma } from "@/lib/db";
import { verifyToken } from "@/lib/auth";

function authenticate(request: NextRequest) {
  const authHeader = request.headers.get("authorization");
  const token = authHeader?.replace("Bearer ", "") || "";
  return verifyToken(token);
}

export async function GET(request: NextRequest) {
  // GET은 토큰 있으면 관리자, 없으면 공개 플랜만 (유저 가격 페이지용)
  const auth = authenticate(request);
  const isAdmin = auth && (auth.role === "ADMIN" || auth.role === "SUPER_ADMIN");

  try {
    const plans = await prisma.plan.findMany({
      where: isAdmin ? {} : { isPublic: true, isActive: true },
      include: { _count: { select: { users: true } } },
      orderBy: { priceMonthly: "asc" },
    });
    return Response.json(plans);
  } catch (e) {
    console.error("플랜 조회 실패:", e);
    return Response.json([]);
  }
}

export async function POST(request: NextRequest) {
  const auth = authenticate(request);
  if (!auth || auth.role !== "SUPER_ADMIN") {
    return Response.json({ error: "최고 관리자만 추가 가능" }, { status: 403 });
  }

  try {
    const body = await request.json();
    // userCount 같은 계산 필드 제거
    delete body.userCount;
    delete body.id;

    const plan = await prisma.plan.create({ data: body });
    return Response.json(plan, { status: 201 });
  } catch (e: any) {
    return Response.json({ error: e.message }, { status: 500 });
  }
}

export async function PUT(request: NextRequest) {
  const auth = authenticate(request);
  if (!auth || auth.role !== "SUPER_ADMIN") {
    return Response.json({ error: "최고 관리자만 수정 가능" }, { status: 403 });
  }

  try {
    const body = await request.json();
    const { id, userCount, ...data } = body;
    const plan = await prisma.plan.update({ where: { id }, data });
    return Response.json(plan);
  } catch (e: any) {
    return Response.json({ error: e.message }, { status: 500 });
  }
}

export async function DELETE(request: NextRequest) {
  const auth = authenticate(request);
  if (!auth || auth.role !== "SUPER_ADMIN") {
    return Response.json({ error: "최고 관리자만 삭제 가능" }, { status: 403 });
  }

  try {
    const { id } = await request.json();
    if (!id) return Response.json({ error: "ID 필수" }, { status: 400 });

    // 사용 중인 유저 확인
    const userCount = await prisma.user.count({ where: { planId: id } });
    if (userCount > 0) {
      return Response.json({
        error: `${userCount}명의 유저가 사용 중입니다. 먼저 다른 플랜으로 이동시키세요.`
      }, { status: 409 });
    }

    await prisma.plan.delete({ where: { id } });
    return Response.json({ success: true });
  } catch (e: any) {
    return Response.json({ error: e.message }, { status: 500 });
  }
}
