/**
 * 약관/방침 공개 API (인증 불필요)
 * GET /api/legal?type=terms|privacy
 */

import { NextRequest } from "next/server";
import { PrismaClient } from "@prisma/client";

const prisma = new PrismaClient();

export async function GET(request: NextRequest) {
  const type = new URL(request.url).searchParams.get("type") || "terms";
  const key = type === "privacy" ? "legal_privacy" : "legal_terms";

  try {
    const setting = await prisma.systemSetting.findUnique({ where: { key } });
    return Response.json({ content: setting?.value || "" });
  } catch {
    return Response.json({ content: "" });
  }
}
