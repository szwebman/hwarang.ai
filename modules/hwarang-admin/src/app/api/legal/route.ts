/**
 * 약관/방침 관리 API
 * GET  - 조회
 * PUT  - 수정 (SUPER_ADMIN만)
 *
 * SystemSetting에 key="legal_terms", "legal_privacy"로 저장
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
    const [terms, privacy] = await Promise.all([
      prisma.systemSetting.findUnique({ where: { key: "legal_terms" } }),
      prisma.systemSetting.findUnique({ where: { key: "legal_privacy" } }),
    ]);

    return Response.json({
      terms: terms?.value || "",
      privacy: privacy?.value || "",
    });
  } catch (e: any) {
    return Response.json({ error: e.message }, { status: 500 });
  }
}

export async function PUT(request: NextRequest) {
  const auth = authenticate(request);
  if (!auth || auth.role !== "SUPER_ADMIN") {
    return Response.json({ error: "최고 관리자만 수정할 수 있습니다" }, { status: 403 });
  }

  try {
    const { terms, privacy } = await request.json();

    if (terms !== undefined) {
      await prisma.systemSetting.upsert({
        where: { key: "legal_terms" },
        update: { value: terms },
        create: { key: "legal_terms", value: terms },
      });
    }

    if (privacy !== undefined) {
      await prisma.systemSetting.upsert({
        where: { key: "legal_privacy" },
        update: { value: privacy },
        create: { key: "legal_privacy", value: privacy },
      });
    }

    return Response.json({ success: true });
  } catch (e: any) {
    return Response.json({ error: e.message }, { status: 500 });
  }
}
