/**
 * 롤 권한 관리 API
 *
 * GET - 권한 매트릭스 조회
 * PUT - 권한 매트릭스 저장 (SUPER_ADMIN만)
 *
 * SystemSetting 테이블에 key="role_permissions"로 JSON 저장
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
  const auth = authenticate(request);
  if (!auth || (auth.role !== "ADMIN" && auth.role !== "SUPER_ADMIN")) {
    return Response.json({ error: "권한 없음" }, { status: 403 });
  }

  try {
    const setting = await prisma.systemSetting.findUnique({
      where: { key: "role_permissions" },
    });

    if (setting) {
      return Response.json({ permissions: JSON.parse(setting.value) });
    }

    return Response.json({ permissions: null });
  } catch (e: any) {
    return Response.json({ error: e.message }, { status: 500 });
  }
}

export async function PUT(request: NextRequest) {
  const auth = authenticate(request);
  if (!auth || auth.role !== "SUPER_ADMIN") {
    return Response.json({ error: "최고 관리자만 권한을 수정할 수 있습니다" }, { status: 403 });
  }

  try {
    const { permissions } = await request.json();

    if (!permissions) {
      return Response.json({ error: "권한 데이터가 없습니다" }, { status: 400 });
    }

    await prisma.systemSetting.upsert({
      where: { key: "role_permissions" },
      update: { value: JSON.stringify(permissions) },
      create: { key: "role_permissions", value: JSON.stringify(permissions) },
    });

    return Response.json({ success: true });
  } catch (e: any) {
    return Response.json({ error: e.message }, { status: 500 });
  }
}
